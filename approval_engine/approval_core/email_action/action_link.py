# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Emailed approval links: issue, validate, retire.

Each link is a random 256-bit token backed by one `Approval Action Token` record
that stores only its SHA-256 hash. A link is usable only while all of these hold:
status Active, not past `expires_on`, the document still a draft in the exact state
the link was issued for, and the approver still an enabled user. Any workflow move
on the document supersedes every open link for it (`supersede_links`), so the first
approver to act wins and older emails go dead. Validating a raw link is
`approval_link.ApprovalLink`.
"""

import hashlib
import secrets

import frappe
from frappe.utils import add_to_date, get_url, now_datetime

TOKEN_DOCTYPE = "Approval Action Token"
LINK_ROUTE = "/approval_action"
DEFAULT_VALIDITY_HOURS = 72
TOKEN_BYTES = 32

STATUS_ACTIVE = "Active"
STATUS_USED = "Used"
STATUS_SUPERSEDED = "Superseded"
STATUS_EXPIRED = "Expired"

INVALID_LINK_MESSAGE = "This approval link is invalid."


def issue_link(doc, user, tier):
	"""
	Create a fresh single-use link for `user` to act on `doc` in its current state.

	Parameters:
	    doc (Document, required): The governed document awaiting action.
	    user (str, required): Approver the link belongs to.
	    tier (int, required): Approver tier the user acts as.

	Returns:
	    str: Absolute URL of the approval page carrying the raw token.
	"""
	raw_token = secrets.token_urlsafe(TOKEN_BYTES)
	frappe.get_doc(
		{
			"doctype": TOKEN_DOCTYPE,
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"user": user,
			"tier": tier,
			"workflow_state": doc.get("workflow_state"),
			"status": STATUS_ACTIVE,
			"expires_on": add_to_date(now_datetime(), hours=link_validity_hours()),
			"token_hash": hash_secret(raw_token),
		}
	).insert(ignore_permissions=True)
	return get_url(f"{LINK_ROUTE}?token={raw_token}")


def supersede_links(doctype, name):
	"""
	Retire every still-active link for a document (it moved state, so they're stale).

	Parameters:
	    doctype (str, required): Target document's DocType.
	    name (str, required): Target document's name.

	Returns:
	    None
	"""
	frappe.db.set_value(
		TOKEN_DOCTYPE,
		{"reference_doctype": doctype, "reference_name": name, "status": STATUS_ACTIVE},
		"status",
		STATUS_SUPERSEDED,
		update_modified=False,
	)


def expire_stale_links():
	"""
	Flag active links whose validity window has passed (housekeeping for the list view).

	Validation never relies on this: `ApprovalLink.from_raw` checks `expires_on` itself.

	Returns:
	    None
	"""
	frappe.db.set_value(
		TOKEN_DOCTYPE,
		{"status": STATUS_ACTIVE, "expires_on": ["<", now_datetime()]},
		"status",
		STATUS_EXPIRED,
		update_modified=False,
	)


def hash_secret(value):
	"""
	One-way hash used for link tokens and OTPs; raw secrets are never stored.

	Parameters:
	    value (str, required): Secret to hash.

	Returns:
	    str: Hex SHA-256 digest.
	"""
	return hashlib.sha256(value.encode()).hexdigest()


def link_validity_hours():
	"""
	Configured link lifetime from Approval Settings (0/blank falls back to 72 hours).

	Returns:
	    int: Validity window in hours.
	"""
	hours = frappe.db.get_single_value("Approval Settings", "email_link_validity_hours")
	return int(hours or DEFAULT_VALIDITY_HOURS)
