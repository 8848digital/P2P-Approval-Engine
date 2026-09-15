"""Procure-to-Pay Management dashboard controller (restricted access).

Identical dashboard to page/procure_to_pay, built on the same shared
customization/procure_to_pay/dashboard_data.py -- the only differences are:

  1. Access is gated by Payments Compliance Settings.allowed_roles (see
     _check_permission), unlike the open page/procure_to_pay.
  2. An "Update Account Closing" button is shown to users whose roles
     intersect Payments Compliance Settings.period_closing_allowed_roles
     (see can_view_period_closing) -- a separate, independently configured
     gate from the dashboard's own allowed_roles. It opens a popup asking
     for a date and, on confirm, sets that date as Company.accounts_frozen_till_date
     on every Company (see update_accounts_frozen_till_date).
"""

import frappe
from frappe import _

from p2p_customization.settlement.customization.procure_to_pay.dashboard_data import (
	_get_settings,
	_check_permission,
	build_dashboard_payload,
	build_debug_raw_counts,
	build_debug_line_items,
	build_error_logs,
)


@frappe.whitelist()
def get_dashboard_data(company=None, from_date=None, to_date=None, for_user=None):
	settings = _get_settings()
	_check_permission(settings)
	# No "User" filter selected -> company-wide aggregate (scope_user=None).
	# A specific user selected -> that user's personal view, same rule
	# whether it's the viewer themselves or someone else they're
	# inspecting -- see build_dashboard_payload's scope_user docs.
	return build_dashboard_payload(settings, company, from_date, to_date, scope_user=for_user or None)


@frappe.whitelist()
def check_access():
	settings = _get_settings()
	_check_permission(settings)
	return {"ok": 1}


@frappe.whitelist()
def debug_raw_counts(doctype=None, company=None, from_date=None, to_date=None):
	settings = _get_settings()
	_check_permission(settings)
	return build_debug_raw_counts(settings, doctype, company, from_date, to_date)


@frappe.whitelist()
def debug_line_items(doctype=None, company=None, from_date=None, to_date=None, limit=200):
	settings = _get_settings()
	_check_permission(settings)
	return build_debug_line_items(settings, doctype, company, from_date, to_date, limit)


@frappe.whitelist()
def get_error_logs(doctype=None, from_date=None, to_date=None, limit=100):
	settings = _get_settings()
	_check_permission(settings)
	return build_error_logs(doctype, from_date, to_date, limit)


def _period_closing_allowed_roles(settings):
	return {row.role for row in (settings.get("period_closing_allowed_roles") or []) if row.role}


def _check_period_closing_permission(settings):
	# Fail-closed, same convention as _check_permission: an empty role list
	# blocks everyone, not just users whose roles don't match.
	allowed_roles = _period_closing_allowed_roles(settings)
	if not allowed_roles or not (allowed_roles & set(frappe.get_roles())):
		frappe.throw(
			_("You are not permitted to update Account Closing."),
			frappe.PermissionError,
		)


@frappe.whitelist()
def can_view_period_closing():
	"""Non-throwing check for the client to decide whether to show the
	"Update Account Closing" button. Fail-closed: an empty role list hides
	the button for everyone, same convention as _check_permission's
	unconfigured-allowed_roles fail-closed default."""
	settings = _get_settings()
	permitted = bool(_period_closing_allowed_roles(settings) & set(frappe.get_roles()))
	return {"permitted": permitted}


@frappe.whitelist()
def update_accounts_frozen_till_date(accounts_frozen_till_date):
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
			failed.append({
				"company": company,
				# A clean, single message for the user (what frappe.throw()
				# actually said, HTML tags like frappe.bold() stripped) --
				# NOT the raw traceback, which is developer-facing noise
				# (file paths, line numbers) that means nothing to whoever
				# clicked "Update Account Closing". The full traceback is
				# still captured above in the Error Log for follow-up.
				"error": frappe.utils.strip_html(str(e)) or _("An unexpected error occurred."),
				"error_log": error_log.name if error_log else None,
			})

	return {
		"accounts_frozen_till_date": accounts_frozen_till_date,
		"total": len(companies),
		"updated": updated,
		"failed": failed,
	}
