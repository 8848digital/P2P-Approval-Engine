# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Validation logic behind the Approval Settings controller."""

from frappe import _, throw

from approval_engine.approval_core.email_action.action_link import DEFAULT_VALIDITY_HOURS

MAX_VALIDITY_HOURS = 720  # 30 days: long enough for any approval, short enough to stay meaningful


def validate_link_validity(doc):
	"""
	Keep the emailed-link lifetime within a sane range.

	Blank falls back to the default (the value is stored, so the form shows what is
	actually used); anything beyond 30 days is refused, since a link that outlives the
	document it approves defeats the expiry.

	Parameters:
	    doc (Document, required): The Approval Settings single being saved.

	Returns:
	    None
	"""
	if not doc.email_link_validity_hours:
		doc.email_link_validity_hours = DEFAULT_VALIDITY_HOURS
		return

	if not 1 <= doc.email_link_validity_hours <= MAX_VALIDITY_HOURS:
		throw(_("Email Link Validity must be between 1 and {0} hours.").format(MAX_VALIDITY_HOURS))
