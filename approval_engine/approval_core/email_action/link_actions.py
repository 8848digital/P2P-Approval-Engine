# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""What the guest approval page can do with a link: view it, request an OTP, act.

Plain business logic behind `www/approval_action.py` (view) and
`api/v1/email_action.py` (request OTP / submit). Everything here is keyed by the
raw link token and returns only visitor-safe data — never the approver's user ID
or full email address.
"""

import re

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow
from frappe.utils import flt, fmt_money, format_time, formatdate, get_fullname

from approval_engine.approval_core.email_action.approval_link import ApprovalLink
from approval_engine.approval_core.email_action.errors import ApprovalLinkError
from approval_engine.approval_core.email_action.otp import OTP_VALIDITY_MINUTES, LinkOtp
from approval_engine.approval_core.email_action.session import acting_as
from approval_engine.approval_core.generator import amount_field_for
from approval_engine.approval_core.remarks import action_needs_reason, clean_remarks, stash_remarks

# Party / date fields shown on the page, first match wins (covers PO, PI, Payment Entry).
PARTY_FIELDS = ("supplier_name", "supplier", "party_name", "party", "customer_name")
DATE_FIELDS = ("posting_date", "transaction_date", "schedule_date")

ACTION_SAVEPOINT = "approval_link_action"

# Frappe's permission message names the DocType, e.g.
# "User <strong>x</strong> does not have doctype access via role permission for document <strong>Supplier</strong>"
MISSING_DOCTYPE_PATTERN = re.compile(r"for document <strong>(.+?)</strong>")


def get_link_summary(raw_token):
	"""
	Everything the approval page shows for a link, or the reason it can't be used.

	Parameters:
	    raw_token (str, required): Token from the emailed link.

	Returns:
	    dict: `{"valid": False, "message": str}` or
	    `{"valid": True, "document": {...}, "actions": [...], "reason_required_for": [...],
	    "approver_name": str, "sent_to": str, "otp_validity_minutes": int,
	    "modified_since_sent": bool, "expires_on": str}`.
	"""
	try:
		link = ApprovalLink.from_raw(raw_token)
	except ApprovalLinkError as error:
		return {"valid": False, "message": str(error)}

	actions = link.allowed_actions()
	return {
		"valid": True,
		"document": __document_summary(link.reference_doc),
		"actions": actions,
		"reason_required_for": [action for action in actions if action_needs_reason(action)],
		"approver_name": get_fullname(link.user),
		"sent_to": __mask_email(link.approver_email),
		"otp_validity_minutes": OTP_VALIDITY_MINUTES,
		"modified_since_sent": link.is_document_modified_since_sent(),
		"expires_on": __format_expiry(link.record.expires_on),
	}


def request_otp(raw_token, action):
	"""
	Email a fresh verification code for `action` to the link's approver.

	Parameters:
	    raw_token (str, required): Token from the emailed link.
	    action (str, required): Workflow action the code will authorise.

	Returns:
	    dict: `{"sent_to": masked email, "validity_minutes": int}`.
	"""
	link = ApprovalLink.from_raw(raw_token)
	link.ensure_action_allowed(action)
	LinkOtp(link).send(action)
	return {"sent_to": __mask_email(link.approver_email), "validity_minutes": OTP_VALIDITY_MINUTES}


def perform_action(raw_token, action, otp, remarks=None):
	"""
	Verify the OTP and apply the workflow action as the link's approver.

	A wrong OTP returns `{"applied": False}` (instead of raising) so the failed attempt
	is committed. Any failure after the OTP check raises and rolls everything back,
	including the OTP consumption, so the approver can simply retry.

	Parameters:
	    raw_token (str, required): Token from the emailed link.
	    action (str, required): Workflow action to apply.
	    otp (str, required): Verification code from the OTP email.
	    remarks (str, optional): Approver's remarks; mandatory for Reject.

	Returns:
	    dict: `{"applied": True, "workflow_state": str}` or
	    `{"applied": False, "attempts_left": int}`.

	Raises:
	    ApprovalLinkError: Link/OTP unusable, or the approver's account lacks a permission
	        the document's save needs (e.g. read on Supplier — approvers need their
	        business role, see SETUP.md); the message names what is missing.
	"""
	link = ApprovalLink.from_raw(raw_token)
	link.ensure_action_allowed(action)
	remarks = clean_remarks(remarks)
	if action_needs_reason(action) and not remarks:
		raise ApprovalLinkError(_("Please enter a reason for rejecting this document."))

	# A wrong OTP returns early *without* rolling back, so the failed attempt is kept.
	frappe.db.savepoint(ACTION_SAVEPOINT)
	otp_check = LinkOtp(link)
	if not otp_check.verify(action, otp):
		return {"applied": False, "attempts_left": otp_check.attempts_left()}

	doc = link.reference_doc
	try:
		with acting_as(link.user):
			stash_remarks(doc.doctype, doc.name, action, remarks, via_email_link=True, user=link.user)
			doc = apply_workflow(doc, action)
	except frappe.PermissionError:
		# Reported as a normal (committed) response, so undo the OTP use and any partial
		# write first: once an admin grants the missing role, the same code still works.
		frappe.db.rollback(save_point=ACTION_SAVEPOINT)
		raise ApprovalLinkError(__missing_access_message()) from None

	link.mark_used(action)
	return {"applied": True, "workflow_state": _(doc.get("workflow_state"))}


def __missing_access_message():
	"""
	Explain which access the approver's account lacks, from Frappe's permission message.

	Naming the DocType is safe here: the visitor has already passed the OTP check. Falls
	back to a generic sentence when Frappe's message can't be read.

	Returns:
	    str: Visitor-facing message.
	"""
	messages = [frappe.parse_json(entry).get("message") or "" for entry in frappe.local.message_log]
	frappe.local.message_log = []
	match = next(filter(None, (MISSING_DOCTYPE_PATTERN.search(m) for m in reversed(messages))), None)
	if match:
		return _(
			"Your ERP account is missing access to {0}, which is needed to complete this "
			"approval. Please ask your ERP administrator to assign the business role for this "
			"document (for example Purchase User or Accounts User)."
		).format(match.group(1))
	return _(
		"Your ERP account is missing a permission needed to complete this approval. "
		"Please contact your ERP administrator."
	)


def __document_summary(doc):
	"""
	Visitor-safe summary of the governed document for the approval page.

	Parameters:
	    doc (Document, required): The governed document.

	Returns:
	    dict: doctype, name, company, department, party, date, amount, workflow_state.
	"""
	amount = flt(doc.get(amount_field_for(doc.doctype)))
	return {
		"doctype": _(doc.doctype),
		"name": doc.name,
		"company": doc.get("company"),
		"department": doc.get("department"),
		"party": __first_value(doc, PARTY_FIELDS),
		"date": frappe.format(__first_value(doc, DATE_FIELDS), {"fieldtype": "Date"}),
		"amount": fmt_money(amount, currency=doc.get("currency")),
		"workflow_state": _(doc.get("workflow_state")),
	}


def __format_expiry(expires_on):
	"""
	Link expiry for display, in the system date format and without seconds.

	Parameters:
	    expires_on (datetime, required): The link's expiry.

	Returns:
	    str: e.g. "25-09-2026 16:37".
	"""
	return f"{formatdate(expires_on)} {format_time(expires_on, 'HH:mm')}"


def __first_value(doc, fieldnames):
	"""
	First non-empty value among `fieldnames` on `doc`.

	Parameters:
	    doc (Document, required): Document to read.
	    fieldnames (tuple[str], required): Candidate fieldnames, in priority order.

	Returns:
	    Any: The value, or None.
	"""
	return next((doc.get(field) for field in fieldnames if doc.get(field)), None)


def __mask_email(email):
	"""
	Partially hide an email for display, e.g. "dhaval@8848digital.com" -> "d****l@8848digital.com".

	Parameters:
	    email (str, optional): Address to mask.

	Returns:
	    str: Masked address ("" when no email).
	"""
	if not email or "@" not in email:
		return ""
	local, domain = email.split("@", 1)
	if len(local) <= 2:
		return f"{local[0]}***@{domain}"
	return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"
