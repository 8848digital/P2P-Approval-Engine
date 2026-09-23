# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
import frappe

from approval_engine.approval_core.email_action.action_link import DEFAULT_VALIDITY_HOURS


def execute():
	"""
	Write the default email-link validity into Approval Settings on existing sites.

	A DocType field default only applies to newly created documents, and Approval
	Settings is a Single whose record predates the field — so it read 0 and the code
	silently fell back to the default. Storing it makes the configured value visible
	and auditable in the form.

	Returns:
	        None
	"""
	if not frappe.db.get_single_value("Approval Settings", "email_link_validity_hours"):
		frappe.db.set_single_value(
			"Approval Settings", "email_link_validity_hours", DEFAULT_VALIDITY_HOURS
		)
