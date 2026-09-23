# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for the open Procure to Pay dashboard
(page `procure-to-pay`). Always scoped to the logged-in user; no Payments
Compliance allowed-roles gate (that is the management dashboard's job).

Thin wrappers only -- the logic lives in
settlement/customization/procure_to_pay/dashboard_data.py.
"""

import frappe

from approval_engine.settlement.customization.procure_to_pay.dashboard_data import (
	_get_settings,
	build_dashboard_payload,
	build_debug_line_items,
	build_debug_raw_counts,
	build_error_logs,
)


@frappe.whitelist(methods=["GET", "POST"])
def get_dashboard_data(
	company: str | None = None, from_date: str | None = None, to_date: str | None = None
):
	"""
	Chart data for the logged-in user's own BRN / PO / PI / Payment Order
	approval status and MSME ageing.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.procure_to_pay.get_dashboard_data`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - company (str, optional): Company to scope the data to
	        - from_date (str, optional): Start of the date range (YYYY-MM-DD)
	        - to_date (str, optional): End of the date range (YYYY-MM-DD)
	**Response:** Dashboard payload (dict) in the standard envelope's `data`.
	"""
	settings = _get_settings()
	return build_dashboard_payload(
		settings, company, from_date, to_date, scope_user=frappe.session.user
	)


@frappe.whitelist(methods=["GET", "POST"])
def check_access():
	"""
	Always allowed: the open dashboard has no role gate beyond the Page's
	own roles. Kept so both dashboards share the same client flow.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.procure_to_pay.check_access`
	**HTTP Method:** GET, POST
	**Parameters:**
	        None
	**Response:** {"ok": 1} in the standard envelope's `data`.
	"""
	return {"ok": 1}


@frappe.whitelist(methods=["GET", "POST"])
def debug_raw_counts(
	doctype: str | None = None,
	company: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
):
	"""
	Debug tool: the user's own documents grouped by workflow state and
	docstatus, showing how each maps to a dashboard bucket.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.procure_to_pay.debug_raw_counts`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - doctype (str, required): One of BRN, Purchase Order, Purchase Invoice, Payment Order
	        - company (str, optional): Company to scope the data to
	        - from_date (str, optional): Start of the date range (YYYY-MM-DD)
	        - to_date (str, optional): End of the date range (YYYY-MM-DD)
	**Response:** Grouped counts (dict) in the standard envelope's `data`.
	"""
	settings = _get_settings()
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
	Debug tool: the user's own documents line by line with the bucket each
	one resolves to.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.procure_to_pay.debug_line_items`
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
	(enforced in build_error_logs).

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.procure_to_pay.get_error_logs`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - doctype (str, optional): Only logs mentioning this DocType
	        - from_date (str, optional): Start of the date range (YYYY-MM-DD)
	        - to_date (str, optional): End of the date range (YYYY-MM-DD)
	        - limit (int, optional): Maximum rows, default 100
	**Response:** Log rows (dict) in the standard envelope's `data`.
	"""
	return build_error_logs(doctype, from_date, to_date, limit)
