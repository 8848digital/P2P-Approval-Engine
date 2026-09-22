# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Builds and submits Supplier Quotation records from extracted BRN vendor
rows. Called from supplier_quotation.py's create_supplier_quotation_from_file.
"""

import frappe

from approval_engine.settlement.doc_events.supplier_quotation_parsing import (
	parse_qty_and_duration,
	resolve_supplier,
	to_float,
)


def create_quotation_for_vendor(data, vendor, file_id):
	"""Builds and submits a single Supplier Quotation for one comparison
	table row. `data` holds the fields shared across every quotation
	created from this BRN (company, cost_center, dates, ...); `vendor`
	holds this row's own name/description/qty/rate/amount/onboarded flag."""

	onboarded_flag = (vendor.get("onboarded") or "").upper()
	is_existing_vendor = 1 if onboarded_flag.startswith("Y") else 0
	is_new_vendor = 0 if is_existing_vendor else 1

	supplier_name = vendor.get("name", "")
	supplier_code = ""
	new_vendor = ""

	if is_existing_vendor and supplier_name:
		supplier_code = resolve_supplier(supplier_name)
	else:
		new_vendor = supplier_name

	# "Qty/Users" and "Periodicity (Months)" both live in the same
	# qty_period cell, in one of two wordings depending on the PDF
	# template - see parse_qty_and_duration for both formats handled.
	qty, _raw_uom, duration_months = parse_qty_and_duration(vendor.get("qty_period", ""))

	# ------------------------------------------------------------------
	# Get Company Billing Address
	# ------------------------------------------------------------------
	billing_address = frappe.db.get_value(
		"Dynamic Link",
		{
			"link_doctype": "Company",
			"link_name": data.get("company"),
			"parenttype": "Address",
		},
		"parent",
	)

	# ------------------------------------------------------------------
	# Create Supplier Quotation
	# ------------------------------------------------------------------
	doc = frappe.get_doc(
		{
			"doctype": "Supplier Quotation",
			"company": data.get("company"),
			"billing_address": billing_address,
			# Existing Vendor
			"supplier": supplier_code if is_existing_vendor else "",
			"supplier_name": supplier_name if is_existing_vendor else "",
			# Vendor Flags
			"is_existing_vendor": is_existing_vendor,
			"is_new_vendor": is_new_vendor,
			# Vendor Details
			"existing_vendor": supplier_code if is_existing_vendor else "",
			"new_vendor": new_vendor,
			# Other Fields
			"transaction_date": data.get("transaction_date"),
			"valid_till": data.get("valid_till"),
			"cost_center": data.get("cost_center"),
			"currency": data.get("currency"),
			"duration_of_service_months": duration_months,
			"service_start_date": data.get("service_start_date") or frappe.utils.today(),
			"msa_agreement": data.get("msa_agreement"),
			"custom_vendor_email": data.get("vendor_email"),
			# GST
			"gst_category": "Unregistered" if is_new_vendor else "",
		}
	)

	description = vendor.get("description", "")

	# BRN items don't carry a real item_code - route them all to one
	# shared placeholder Item rather than guessing/creating a new Item
	# per free-text description.
	item_code = _get_or_create_placeholder_item()

	doc.append(
		"items",
		{
			"item_code": item_code,
			"description": description,
			"hsn_sac": "",
			"qty": qty,
			"uom": PLACEHOLDER_ITEM_UOM,
			"rate": to_float(vendor.get("rate")),
			"amount": to_float(vendor.get("amount")),
		},
	)

	# ignore_mandatory=True per requirement - BRN does not carry every
	# mandatory field (e.g. item_code), so validation is relaxed here.
	doc.insert(ignore_permissions=True, ignore_mandatory=True)

	# ------------------------------------------------------------------
	# Attach Uploaded PDF (same source file, shared across every
	# quotation created from it)
	# ------------------------------------------------------------------
	_attach_pdf_to_doc(file_id, doc)

	# ignore_mandatory has to be set again for submit, insert() does not
	# carry the flag forward into the submit validation cycle.
	doc.flags.ignore_mandatory = True
	doc.submit()

	return {
		"name": doc.name,
		"supplier_name": supplier_name,
		"is_existing_vendor": is_existing_vendor,
		"is_new_vendor": is_new_vendor,
		"docstatus": "Draft",
	}


def _attach_pdf_to_doc(file_id, doc):
	"""Attaches the uploaded BRN to a Supplier Quotation. Since several
	quotations can come from the same upload, the first quotation gets
	the original File record re-pointed to it; every quotation after
	that gets its own File record pointing at the same physical file,
	since one File can only be attached to one document at a time."""
	if not file_id:
		return

	try:
		source_file = frappe.get_doc("File", file_id)
	except frappe.DoesNotExistError:
		frappe.log_error(title="Supplier Quotation Attachment", message=f"File not found: {file_id}")
		return

	if not source_file.attached_to_name:
		source_file.attached_to_doctype = "Supplier Quotation"
		source_file.attached_to_name = doc.name
		source_file.save(ignore_permissions=True)
	else:
		copy_file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": source_file.file_name,
				"file_url": source_file.file_url,
				"is_private": source_file.is_private,
				"attached_to_doctype": "Supplier Quotation",
				"attached_to_name": doc.name,
			}
		)
		copy_file.insert(ignore_permissions=True)


# Common BRN wording -> a UOM that's actually likely to exist in the system.
# "units"/"user"/"license" etc are how business users phrase quantities in
# the PDF, but they usually aren't real UOM records - extend this as needed.
_UOM_ALIASES = {
	"unit": "Nos",
	"units": "Nos",
	"user": "Nos",
	"users": "Nos",
	"license": "Nos",
	"licenses": "Nos",
}


def _normalize_uom(raw_uom):
	if not raw_uom:
		return "Nos"

	key = raw_uom.strip().lower()
	candidate = _UOM_ALIASES.get(key, raw_uom.strip().title())

	if frappe.db.exists("UOM", candidate):
		return candidate
	if frappe.db.exists("UOM", "Nos"):
		return "Nos"
	return candidate  # let Frappe's own validation surface the missing UOM


PLACEHOLDER_ITEM_NAME = "Item Customize as per Description"
PLACEHOLDER_ITEM_UOM = "EA"
PLACEHOLDER_ITEM_DESCRIPTION = (
	"standard item supplier quotation to be updated by user in brn as per description provided"
)


def _get_or_create_placeholder_item():
	"""Whenever a BRN item has no real item_code, everything routes to this
	one shared placeholder Item rather than guessing/creating a new Item
	per free-text description - business users then update the row with
	the correct real Item afterwards."""
	existing = frappe.db.get_value("Item", {"item_name": PLACEHOLDER_ITEM_NAME}, "name")
	if existing:
		return existing

	item_group = (
		"Services"
		if frappe.db.exists("Item Group", "Services")
		else (frappe.db.get_value("Item Group", {}, "name") or "All Item Groups")
	)

	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": PLACEHOLDER_ITEM_NAME,
			"item_name": PLACEHOLDER_ITEM_NAME,
			"description": PLACEHOLDER_ITEM_DESCRIPTION,
			"item_group": item_group,
			"stock_uom": PLACEHOLDER_ITEM_UOM,
			"is_stock_item": 0,
			"gst_hsn_code": "00000000",
		}
	)
	item.insert(ignore_permissions=True, ignore_mandatory=True)
	return item.name
