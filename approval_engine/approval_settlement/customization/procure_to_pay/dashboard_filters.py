# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Settings, access check and common query filters for the Procure to Pay dashboard.
"""

import frappe
from frappe import _

from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_config import (
	DOCTYPE_DATE_FIELD,
	_log,
)


def _get_settings():
	_log("PCD: _get_settings", "Fetching Payments Compliance Settings single doc")
	settings = frappe.get_single("Payments Compliance Settings")
	mapping_rows = settings.get("workflow_state_mapping") or []
	allowed_roles = [row.role for row in (settings.get("allowed_roles") or [])]
	_log(
		"PCD: settings loaded",
		f"allowed_roles={allowed_roles!r}\n"
		f"chart_types: brn={settings.brn_chart_type!r} payment_order={settings.payment_order_chart_type!r} "
		f"purchase_order={settings.purchase_order_chart_type!r} purchase_invoice={settings.purchase_invoice_chart_type!r} "
		f"msme={settings.msme_chart_type!r}\n"
		f"auto_refresh_seconds={settings.auto_refresh_seconds!r}\n"
		f"workflow_state_mapping rows={len(mapping_rows)}",
	)
	return settings


def _check_permission(settings):
	# Fail-closed by design: an empty Allowed Roles list blocks everyone,
	# not just users whose roles don't match. Callers decide whether to
	# invoke this at all -- see module docstring.
	allowed_roles = {row.role for row in (settings.get("allowed_roles") or []) if row.role}
	user_roles = set(frappe.get_roles())
	_log(
		"PCD: _check_permission",
		f"allowed_roles={allowed_roles!r}\nuser={frappe.session.user}\nuser_roles={user_roles}",
	)
	if not allowed_roles or not (allowed_roles & user_roles):
		_log(
			"PCD: PERMISSION DENIED",
			f"user={frappe.session.user} has none of allowed_roles={allowed_roles!r}.",
		)
		frappe.throw(
			_("You are not permitted to view the Payments Compliance Dashboard."),
			frappe.PermissionError,
		)


def _has_field(doctype, fieldname):
	return frappe.get_meta(doctype).has_field(fieldname)


def _get_count(row):
	return row.get("count", row.get("COUNT(`name`)", 0)) or 0


def _date_range_filter(from_date, to_date, fieldname="creation"):
	if from_date and to_date:
		result = {fieldname: ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]}
	elif from_date:
		result = {fieldname: [">=", f"{from_date} 00:00:00"]}
	elif to_date:
		result = {fieldname: ["<=", f"{to_date} 23:59:59"]}
	else:
		result = {}
	_log("PCD: _date_range_filter", f"from_date={from_date!r} to_date={to_date!r} -> {result}")
	return result


def _base_filters(doctype, company, from_date, to_date, extra=None, date_field=None):
	"""Company + date-range filters shared by both the count query and the
	click-through filter for every bucket of this doctype."""
	filters = {}
	if company and _has_field(doctype, "company"):
		filters["company"] = company
	filters.update(
		_date_range_filter(
			from_date, to_date, fieldname=date_field or DOCTYPE_DATE_FIELD.get(doctype, "creation")
		)
	)
	if extra:
		filters.update(extra)
	return filters
