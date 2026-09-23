# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for Supplier customization (status mail, approval
mail, Nature of Service search).

Thin wrappers only -- the actual logic lives in
settlement/customization/supplier/utils.py and
settlement/customization/supplier/query.py.
"""

import frappe

from approval_engine.settlement.customization.supplier.query import get_nature_of_service_options
from approval_engine.settlement.customization.supplier.utils import (
	_send_supplier_status_mail,
	approval_mail,
)


@frappe.whitelist(methods=["POST"])
def send_supplier_message(supplier: str, reason: str, action: str):
	"""
	Notify a supplier by email of a Reject/Comment workflow action, and log
	the reason as a comment on the Supplier document.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.supplier.send_supplier_message`
	**HTTP Method:** POST
	**Parameters:**
	        - supplier (str, required): The Supplier document name
	        - reason (str, required): The reason/comment text
	        - action (str, required): The workflow action ("Reject" or any other, treated as "Comment")
	**Response:** `"sent"` or `"no_email"`, serialized as JSON.
	"""
	return _send_supplier_status_mail(supplier, reason, action)


@frappe.whitelist(methods=["POST"])
def send_approval_mail(supplier_name: str, email_id: str):
	"""
	Notify a supplier by email that their registration has been approved.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.supplier.send_approval_mail`
	**HTTP Method:** POST
	**Parameters:**
	        - supplier_name (str, required): The supplier's display name (used in the email body)
	        - email_id (str, required): The recipient email address
	**Response:** `"sent"` or `"no_email"`, serialized as JSON.
	"""
	return approval_mail(supplier_name, email_id)


@frappe.whitelist(methods=["GET", "POST"])
@frappe.validate_and_sanitize_search_inputs
def get_nature_of_service_query(
	doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict
):
	"""
	Returns all matching TDS Reference records (no pagination) so the
	Nature of Service Table MultiSelect on Supplier is not capped at
	the default page length of 20.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.supplier.get_nature_of_service_query`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - doctype (str, required): The Link/MultiSelect target doctype (standard search-query arg)
	        - txt (str, required): The text typed into the search box
	        - searchfield (str, required): The field being searched (standard search-query arg)
	        - start (int, required): Pagination offset (standard search-query arg, unused here)
	        - page_len (int, required): Page size (standard search-query arg, unused here)
	        - filters (dict, required): Additional filters (standard search-query arg, unused here)
	**Response:** List of (name, section_as_per_it_act_1961, tds_rate) tuples, serialized as JSON.
	"""
	return get_nature_of_service_options(txt)
