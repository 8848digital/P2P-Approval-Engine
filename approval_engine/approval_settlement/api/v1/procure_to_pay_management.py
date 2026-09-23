# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for the Procure to Pay Management dashboard
(page `procure-to-pay-management`). Every call is gated by Payments
Compliance Settings > Allowed Roles; period closing has its own role list.

Thin wrappers only -- the logic lives in
approval_settlement/customization/procure_to_pay/dashboard_data.py and period_closing.py.
"""

import frappe

from approval_engine.approval_settlement.customization.procure_to_pay.dashboard_data import (
	_check_permission,
	_get_settings,
	build_dashboard_payload,
	build_debug_line_items,
	build_debug_raw_counts,
	build_error_logs,
)
from approval_engine.approval_settlement.customization.procure_to_pay.period_closing import (
	can_view_period_closing as _can_view_period_closing,
)
from approval_engine.approval_settlement.customization.procure_to_pay.period_closing import (
	update_accounts_frozen_till_date as _update_accounts_frozen_till_date,
)


@frappe.whitelist(methods=["GET", "POST"])
def get_dashboard_data(
	company: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	for_user: str | None = None,
):
	"""
	Company-wide dashboard data, or one user's personal view when for_user
	is given.

	**Endpoint:** `/api/method/approval_engine.approval_settlement.api.v1.procure_to_pay_management.get_dashboard_data`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - company (str, optional): Company to scope the data to
	        - from_date (str, optional): Start of the date range (YYYY-MM-DD)
	        - to_date (str, optional): End of the date range (YYYY-MM-DD)
	        - for_user (str, optional): Show this user's personal view instead of the company-wide one
	**Response:** Dashboard payload (dict) in the standard envelope's `data`.
	"""
	settings = _get_settings()
	_check_permission(settings)
	return build_dashboard_payload(settings, company, from_date, to_date, scope_user=for_user or None)


@frappe.whitelist(methods=["GET", "POST"])
def check_access():
	"""
	Raise PermissionError unless the user has an Allowed Role; the page
	calls this before loading.

	**Endpoint:** `/api/method/approval_engine.approval_settlement.api.v1.procure_to_pay_management.check_access`
	**HTTP Method:** GET, POST
	**Parameters:**
	        None
	**Response:** {"ok": 1} in the standard envelope's `data`.
	"""
	settings = _get_settings()
	_check_permission(settings)
	return {"ok": 1}


@frappe.whitelist(methods=["GET", "POST"])
def debug_raw_counts(
	doctype: str | None = None,
	company: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
):
	"""
	Debug tool: documents grouped by workflow state and docstatus, showing
	how each maps to a dashboard bucket.

	**Endpoint:** `/api/method/approval_engine.approval_settlement.api.v1.procure_to_pay_management.debug_raw_counts`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - doctype (str, required): One of BRN, Purchase Order, Purchase Invoice, Payment Order
	        - company (str, optional): Company to scope the data to
	        - from_date (str, optional): Start of the date range (YYYY-MM-DD)
	        - to_date (str, optional): End of the date range (YYYY-MM-DD)
	**Response:** Grouped counts (dict) in the standard envelope's `data`.
	"""
	settings = _get_settings()
	_check_permission(settings)
	return build_debug_raw_counts(settings, doctype, company, from_date, to_date)


@frappe.whitelist(methods=["GET", "POST"])
def debug_line_items(
	doctype: str | None = None,
	company: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	limit: int = 200,
):
	"""
	Debug tool: documents line by line with the bucket each one resolves
	to.

	**Endpoint:** `/api/method/approval_engine.approval_settlement.api.v1.procure_to_pay_management.debug_line_items`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - doctype (str, required): One of BRN, Purchase Order, Purchase Invoice, Payment Order
	        - company (str, optional): Company to scope the data to
	        - from_date (str, optional): Start of the date range (YYYY-MM-DD)
	        - to_date (str, optional): End of the date range (YYYY-MM-DD)
	        - limit (int, optional): Maximum rows, default 200
	**Response:** Rows (dict) in the standard envelope's `data`.
	"""
	settings = _get_settings()
	_check_permission(settings)
	return build_debug_line_items(settings, doctype, company, from_date, to_date, limit)


@frappe.whitelist(methods=["GET", "POST"])
def get_error_logs(
	doctype: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	limit: int = 100,
):
	"""
	Error Log viewer for the dashboard's DocTypes. System Manager only
	(enforced in build_error_logs), on top of the Allowed Roles gate.

	**Endpoint:** `/api/method/approval_engine.approval_settlement.api.v1.procure_to_pay_management.get_error_logs`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - doctype (str, optional): Only logs mentioning this DocType
	        - from_date (str, optional): Start of the date range (YYYY-MM-DD)
	        - to_date (str, optional): End of the date range (YYYY-MM-DD)
	        - limit (int, optional): Maximum rows, default 100
	**Response:** Log rows (dict) in the standard envelope's `data`.
	"""
	settings = _get_settings()
	_check_permission(settings)
	return build_error_logs(doctype, from_date, to_date, limit)


@frappe.whitelist(methods=["GET", "POST"])
def can_view_period_closing():
	"""
	Whether to show the "Update Account Closing" button: True only for
	users with a Period Closing Allowed Role. Never throws.

	**Endpoint:** `/api/method/approval_engine.approval_settlement.api.v1.procure_to_pay_management.can_view_period_closing`
	**HTTP Method:** GET, POST
	**Parameters:**
	        None
	**Response:** {"permitted": bool} in the standard envelope's `data`.
	"""
	return _can_view_period_closing()


@frappe.whitelist(methods=["POST"])
def update_accounts_frozen_till_date(accounts_frozen_till_date: str):
	"""
	Set Company.accounts_frozen_till_date on every Company. Gated by Period
	Closing Allowed Roles; one company's failure doesn't block the rest.

	**Endpoint:** `/api/method/approval_engine.approval_settlement.api.v1.procure_to_pay_management.update_accounts_frozen_till_date`
	**HTTP Method:** POST
	**Parameters:**
	        - accounts_frozen_till_date (str, required): The new frozen-till date (YYYY-MM-DD)
	**Response:** {"accounts_frozen_till_date", "total", "updated": [...], "failed": [{"company", "error", "error_log"}]} in the standard envelope's `data`.
	"""
	return _update_accounts_frozen_till_date(accounts_frozen_till_date)
