# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Period closing for the Procure to Pay Management dashboard: whether the
user may run "Update Account Closing", and setting
Company.accounts_frozen_till_date on every Company. Exposed via
approval_settlement/api/v1/procure_to_pay_management.py.
"""

import frappe
from frappe import _

from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_data import (
	_get_settings,
)


def _period_closing_allowed_roles(settings):
	"""Roles from Payments Compliance Settings > Period Closing Allowed Roles.

	Parameters:
	        settings (Document, required): Payments Compliance Settings.

	Returns:
	        set[str]: The configured role names.
	"""
	return {row.role for row in (settings.get("period_closing_allowed_roles") or []) if row.role}


def _check_period_closing_permission(settings):
	"""Raise PermissionError unless the user has a Period Closing Allowed Role.

	Parameters:
	        settings (Document, required): Payments Compliance Settings.

	Returns:
	        None
	"""
	# Fail-closed, same convention as _check_permission: an empty role list
	# blocks everyone, not just users whose roles don't match.
	allowed_roles = _period_closing_allowed_roles(settings)
	if not allowed_roles or not (allowed_roles & set(frappe.get_roles())):
		frappe.throw(
			_("You are not permitted to update Account Closing."),
			frappe.PermissionError,
		)


def can_view_period_closing():
	"""Non-throwing check for the client to decide whether to show the
	"Update Account Closing" button. Fail-closed: an empty role list hides
	the button for everyone, same convention as _check_permission's
	unconfigured-allowed_roles fail-closed default."""
	settings = _get_settings()
	permitted = bool(_period_closing_allowed_roles(settings) & set(frappe.get_roles()))
	return {"permitted": permitted}


def update_accounts_frozen_till_date(accounts_frozen_till_date: str):
	"""Set Company.accounts_frozen_till_date to `accounts_frozen_till_date`
	on every Company. Gated independently from the dashboard's own
	allowed_roles -- see _check_period_closing_permission / Payments
	Compliance Settings > Period Closing Allowed Roles.

	Goes through frappe.get_doc(...).save() per company (not a bulk
	db.set_value) so Company.validate_pending_reposts() still runs -- it
	throws if there's a pending Repost Item Valuation before the new date,
	which is exactly the guardrail this date is supposed to respect. One
	company's failure doesn't block the rest; failures are reported back
	so the caller can see exactly which companies still need attention.
	"""
	settings = _get_settings()
	_check_period_closing_permission(settings)

	if not accounts_frozen_till_date:
		frappe.throw(_("Please select a date."))

	companies = frappe.get_all("Company", pluck="name")
	updated = []
	failed = []

	# Commit after every successful save (not once at the end) so that a
	# later company's failure -> frappe.db.rollback() only undoes ITS OWN
	# uncommitted change, not every company already saved in this loop.
	for company in companies:
		try:
			doc = frappe.get_doc("Company", company)
			doc.accounts_frozen_till_date = accounts_frozen_till_date
			doc.save()
			frappe.db.commit()
			updated.append(company)
		except Exception as e:
			frappe.db.rollback()
			error_log = frappe.log_error(
				title=f"Account Closing update failed for {company}"[:140],
				message=frappe.get_traceback(),
				reference_doctype="Company",
				reference_name=company,
			)
			failed.append(
				{
					"company": company,
					# A clean, single message for the user (what frappe.throw()
					# actually said, HTML tags like frappe.bold() stripped) --
					# NOT the raw traceback, which is developer-facing noise
					# (file paths, line numbers) that means nothing to whoever
					# clicked "Update Account Closing". The full traceback is
					# still captured above in the Error Log for follow-up.
					"error": frappe.utils.strip_html(str(e)) or _("An unexpected error occurred."),
					"error_log": error_log.name if error_log else None,
				}
			)

	return {
		"accounts_frozen_till_date": accounts_frozen_till_date,
		"total": len(companies),
		"updated": updated,
		"failed": failed,
	}
