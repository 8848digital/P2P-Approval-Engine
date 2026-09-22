"""Procure-to-Pay dashboard controller (open access).

Thin wrapper around customization/procure_to_pay/dashboard_data.py -- see
that module for the actual bucketing/query logic, which is shared with
page/procure_to_pay_management (the same dashboard, gated by Payments
Compliance Settings' allowed_roles, plus the Update Account Closing action).

Deliberately does NOT call dashboard_data._check_permission(): this page has
no Payments Compliance Settings allowed_roles gate -- any user who can reach
the page (Page.roles = "All") can view it. The restricted variant lives at
page/procure_to_pay_management.
"""

import frappe

from p2p_customization.settlement.customization.procure_to_pay.dashboard_data import (
	_get_settings,
	build_dashboard_payload,
	build_debug_line_items,
	build_debug_raw_counts,
	build_error_logs,
)


@frappe.whitelist()
def get_dashboard_data(company: str | None = None, from_date: str | None = None, to_date: str | None = None):
	settings = _get_settings()
	# Always personal, forced to the logged-in user -- this open dashboard
	# has no company-wide/aggregate mode (that's the management dashboard's
	# default; see procure_to_pay_management.py).
	return build_dashboard_payload(settings, company, from_date, to_date, scope_user=frappe.session.user)


@frappe.whitelist()
def check_access():
	return {"ok": 1}


@frappe.whitelist()
def debug_raw_counts(
	doctype: str | None = None,
	company: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
):
	settings = _get_settings()
	return build_debug_raw_counts(settings, doctype, company, from_date, to_date)


@frappe.whitelist()
def debug_line_items(
	doctype: str | None = None,
	company: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	limit: int = 200,
):
	settings = _get_settings()
	return build_debug_line_items(settings, doctype, company, from_date, to_date, limit)


@frappe.whitelist()
def get_error_logs(
	doctype: str | None = None, from_date: str | None = None, to_date: str | None = None, limit: int = 100
):
	return build_error_logs(doctype, from_date, to_date, limit)
