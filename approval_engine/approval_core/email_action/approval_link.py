# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Validate an emailed approval link and act through it.

Split out of action_link.py (which issues and retires links) to keep both
files under the line-count cap.
"""

from functools import cached_property

import frappe
from frappe import _
from frappe.model.workflow import get_transitions
from frappe.utils import get_datetime, now_datetime

from approval_engine.approval_core.email_action.action_link import (
	INVALID_LINK_MESSAGE,
	STATUS_ACTIVE,
	STATUS_USED,
	TOKEN_DOCTYPE,
	hash_secret,
)
from approval_engine.approval_core.email_action.errors import ApprovalLinkError
from approval_engine.approval_core.email_action.session import acting_as


class ApprovalLink:
	"""A validated, currently usable emailed link, plus what its approver may do with it."""

	def __init__(self, record):
		"""
		Wrap an already-validated token record. Use `from_raw` to build one from a URL token.

		Parameters:
		    record (Document, required): The `Approval Action Token` record.

		Returns:
		    None
		"""
		self.record = record

	@classmethod
	def from_raw(cls, raw_token):
		"""
		Resolve the raw token from a URL and verify that the link is still usable.

		Parameters:
		    raw_token (str, required): Token from the emailed link.

		Returns:
		    ApprovalLink: The usable link.

		Raises:
		    ApprovalLinkError: With a visitor-safe reason when it can't be used.
		"""
		name = frappe.db.get_value(TOKEN_DOCTYPE, {"token_hash": hash_secret(raw_token or "")})
		if not raw_token or not name:
			raise ApprovalLinkError(_(INVALID_LINK_MESSAGE))

		link = cls(frappe.get_doc(TOKEN_DOCTYPE, name))
		link.ensure_usable()
		return link

	@property
	def user(self):
		"""
		Approver this link belongs to.

		Returns:
		    str: User ID.
		"""
		return self.record.user

	@cached_property
	def approver_email(self):
		"""
		The approver's registered email address (where the OTP is sent).

		Returns:
		    str: Email address from the User record.
		"""
		return frappe.db.get_value("User", self.user, "email")

	@cached_property
	def reference_doc(self):
		"""
		The governed document this link acts on (loaded once per request).

		Returns:
		    Document: The target document.
		"""
		return frappe.get_doc(self.record.reference_doctype, self.record.reference_name)

	def ensure_usable(self):
		"""
		Raise unless the link is active, unexpired, for an enabled user, on an unchanged doc.

		Returns:
		    None
		"""
		if self.record.status == STATUS_USED:
			raise ApprovalLinkError(_("This approval link has already been used."))
		if self.record.status != STATUS_ACTIVE:
			raise ApprovalLinkError(
				_("This approval link is no longer valid — the document has already been actioned.")
			)
		if get_datetime(self.record.expires_on) < now_datetime():
			raise ApprovalLinkError(_("This approval link has expired."))
		if not frappe.db.get_value("User", self.user, "enabled"):
			raise ApprovalLinkError(_(INVALID_LINK_MESSAGE))
		self.__ensure_document_unchanged()

	def allowed_actions(self):
		"""
		Workflow actions the approver can take right now, evaluated exactly as in Desk.

		Returns:
		    list[str]: Distinct action names in workflow order (e.g. ["Approve", "Reject"]).
		"""
		with acting_as(self.user):
			transitions = get_transitions(self.reference_doc)
		return list(dict.fromkeys(transition.action for transition in transitions))

	def ensure_action_allowed(self, action):
		"""
		Raise unless `action` is currently available to this approver.

		Parameters:
		    action (str, required): Requested workflow action.

		Returns:
		    None
		"""
		if action not in self.allowed_actions():
			raise ApprovalLinkError(_("This action is not available for you on this document."))

	def is_document_modified_since_sent(self):
		"""
		Whether the document was edited after this link was emailed (the PDF may be stale).

		Returns:
		    bool: True when the document's `modified` is newer than the link.
		"""
		return get_datetime(self.reference_doc.modified) > get_datetime(self.record.creation)

	def mark_used(self, action):
		"""
		Close the link after a successful action, recording what was done and from where.

		Parameters:
		    action (str, required): The workflow action applied.

		Returns:
		    None
		"""
		self.record.db_set(
			{
				"status": STATUS_USED,
				"used_action": action,
				"used_on": now_datetime(),
				"used_ip": frappe.local.request_ip,
			}
		)

	def __ensure_document_unchanged(self):
		"""
		Raise if the document was deleted, submitted/cancelled or moved to another state.

		Returns:
		    None
		"""
		record = self.record
		state = frappe.db.get_value(
			record.reference_doctype,
			record.reference_name,
			["docstatus", "workflow_state"],
			as_dict=True,
		)
		if not state:
			raise ApprovalLinkError(_(INVALID_LINK_MESSAGE))
		if state.docstatus != 0 or state.workflow_state != record.workflow_state:
			raise ApprovalLinkError(
				_("This approval link is no longer valid — the document is now {0}.").format(
					_(state.workflow_state or "closed")
				)
			)
