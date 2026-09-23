# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import base64

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import add_days, add_months, cint, getdate


def calculate_brn_expiry_date(date, months):
	"""
	Compute a BRN's service expiry date from its start date + duration.

	Parameters:
		date (str, required): The service start date.
		months (int, required): Duration of service, in months.

	Returns:
		date: date + months, anchored to the day before date (matches the
			existing "expires the day before the anniversary" convention).
	"""
	return add_months(getdate(add_days(date, -1)), cint(months))


@frappe.whitelist()
def decode_email(encoded_email: str) -> str:
	"""
	Decode an email address encoded by vendor_email_encoding.encode_email().

	**Endpoint:** `/api/method/approval_engine.settlement.doctype.brn.utils.decode_email`
	**HTTP Method:** GET, POST
	**Parameters:**
		- encoded_email (str, required): The base64url-encoded "local@domain" string
	**Response:** The decoded email address (str), serialized as JSON.
	"""
	encoded_local, encoded_domain = encoded_email.split("@")
	decoded_local = decode_string_part(encoded_local)
	decoded_domain = decode_string_part(encoded_domain)
	return f"{decoded_local}@{decoded_domain}"


def decode_string_part(encoded_part: str) -> str:
	"""Base64url-decode one part encoded by vendor_email_encoding.encode_string_part()."""
	padding = "=" * (4 - len(encoded_part) % 4)
	encoded_part += padding
	return base64.urlsafe_b64decode(encoded_part.encode()).decode()


def create_po_from_brn(source_name, vendor=None):
	"""
	Map a submitted BRN into an unsaved Purchase Order.

	Parameters:
		source_name (str, required): The BRN document name to map from.
		vendor (str, optional): An existing_vendor from the BRN's
			Comparision table to set as the PO's supplier.

	Returns:
		Document: The mapped (unsaved) Purchase Order.
	"""
	doc = get_mapped_doc(
		"BRN",
		source_name,
		{
			"BRN": {
				"doctype": "Purchase Order",
				"postprocess": lambda source, target, source_parent=None: set_supplier(
					source, target, vendor
				),
			},
			"BRN Item": {
				"doctype": "Purchase Order Item",
				"field_map": {"rate": "rate", "expense_gl": "expense_account"},
			},
		},
	)

	return doc


def _create_pi_from_brn(source_name, vendor=None):
	"""
	Map a submitted BRN into an unsaved Purchase Invoice.

	Parameters:
		source_name (str, required): The BRN document name to map from.
		vendor (str, optional): An existing_vendor from the BRN's
			Comparision table to set as the PI's supplier.

	Returns:
		Document: The mapped (unsaved) Purchase Invoice.
	"""
	doc = get_mapped_doc(
		"BRN",
		source_name,
		{
			"BRN": {
				"doctype": "Purchase Invoice",
				"postprocess": lambda source, target, source_parent=None: set_supplier(
					source, target, vendor
				),
			},
			"BRN Item": {
				"doctype": "Purchase Invoice Item",
				"field_map": {"rate": "rate", "expense_gl": "expense_account"},
			},
		},
	)

	return doc


def get_comparison_vendor_rows(brn_name):
	"""Comparision rows on this BRN that have an existing_vendor set --
	the candidates for the Create Purchase Order/Invoice flow. Not
	filtered on Preferred: that flag is for the new-vendor onboarding
	flow only (see add_onboard_vendor_button in brn.js), unrelated to
	which existing vendor a PO/PI gets created against."""
	return frappe.get_all(
		"BRN Comparision",
		filters={"parent": brn_name, "parenttype": "BRN", "existing_vendor": ["!=", ""]},
		fields=["existing_vendor"],
	)


def set_supplier(source, target, vendor=None) -> None:
	"""
	get_mapped_doc postprocess: set target.supplier from vendor, after
	checking it's actually one of the BRN's Comparision-table vendors.

	Parameters:
		source (Document, required): The source BRN document.
		target (Document, required): The mapped Purchase Order/Invoice.
		vendor (str, optional): An existing_vendor to set as the supplier;
			leaves target.supplier unset if not given.

	Returns:
		None
	"""
	if not vendor:
		target.supplier = None
		return

	valid_vendors = {row.existing_vendor for row in get_comparison_vendor_rows(source.name)}
	if vendor not in valid_vendors:
		frappe.throw(
			_("{0} is not one of the vendors listed in this BRN's Comparision table.").format(vendor)
		)

	target.supplier = vendor
