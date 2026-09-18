"""Whitelisted entrypoints for Supplier Quotation / BRN creation and PDF
import. Business logic lives in the sibling supplier_quotation_creation.py,
supplier_quotation_extraction.py and supplier_quotation_parsing.py modules -
kept as thin wrappers here so the dotted method paths below stay stable
(client scripts call them by exact path).
"""

import frappe
from frappe import _

from p2p_customization.settlement.doc_events.supplier_quotation_creation import (
	create_quotation_for_vendor,
)
from p2p_customization.settlement.doc_events.supplier_quotation_extraction import (
	extract_tables,
	extract_text,
	parse_brn_data,
)


@frappe.whitelist()
def create_brn(supplier_quotation: str):
	"""
	Create a BRN record from a Supplier Quotation.
	"""
	supplier_quotation = frappe.get_doc("Supplier Quotation", supplier_quotation)
	existing_brn_name = frappe.db.exists(
		"BRN", {"quotation_requisition_id": supplier_quotation.custom_requisition_no}
	)

	if not existing_brn_name:
		brn = frappe.get_doc(
			{
				"doctype": "BRN",
				"company": supplier_quotation.company,
				"transaction_date": supplier_quotation.transaction_date,
				"duration_of_service_months": supplier_quotation.duration_of_service_months,
				"service_start_date": supplier_quotation.service_start_date,
				"is_new_vendor": supplier_quotation.is_new_vendor,
				"quotation_requisition_id": supplier_quotation.custom_requisition_no,
				"is_existing_vendor": supplier_quotation.is_existing_vendor,
				"existing_vendor": supplier_quotation.supplier,
				"msa_agreement": supplier_quotation.msa_agreement,
				"new_vendor": supplier_quotation.new_vendor,
				"supplier_quotation": supplier_quotation.name,
				"single": 1,
			}
		)

		brn.append(
			"comparision",
			{
				"is_new_vendor": supplier_quotation.is_new_vendor,
				"is_existing_vendor": supplier_quotation.is_existing_vendor,
				"vendor_name": supplier_quotation.new_vendor
				if supplier_quotation.new_vendor
				else supplier_quotation.supplier_name,
				"existing_vendor": supplier_quotation.supplier,
				"preferred": 1 if supplier_quotation.workflow_state == "Selected" else 0,
			},
		)

		brn.insert(ignore_mandatory=True)
		frappe.db.set_value(
			"Supplier Quotation", supplier_quotation.name, "custom_brn", brn.name, update_modified=False
		)
		return {"name": brn.name, "is_new": True}

	brn = frappe.get_doc("BRN", existing_brn_name)
	if brn.docstatus == 0:
		if brn.single == 1:
			brn.single = 0
		brn.multi = 1
		brn.append(
			"comparision",
			{
				"is_new_vendor": supplier_quotation.is_new_vendor,
				"is_existing_vendor": supplier_quotation.is_existing_vendor,
				"vendor_name": supplier_quotation.new_vendor
				if supplier_quotation.new_vendor
				else supplier_quotation.supplier_name,
				"existing_vendor": supplier_quotation.supplier,
				"preferred": 1 if supplier_quotation.workflow_state == "Selected" else 0,
			},
		)
	brn.flags.ignore_mandatory = True
	brn.save()
	frappe.db.set_value(
		"Supplier Quotation", supplier_quotation.name, "custom_brn", brn.name, update_modified=False
	)
	return {"name": brn.name, "is_new": False}


# =====================================================================
# CREATE SUPPLIER QUOTATION
# =====================================================================


@frappe.whitelist()
def create_supplier_quotation_from_file(file_id: str):
	"""One BRN can propose several vendors in its comparison table
	(existing + new). We create one Supplier Quotation per vendor row,
	not just the preferred one, so every proposal is captured."""
	try:
		data = extract_supplier_quotation_pdf(file_id)

		frappe.log_error(title="SQ Extraction Debug", message=frappe.as_json(data))

		vendors = data.get("vendors") or []
		if not vendors:
			frappe.throw(
				_(
					"No vendors could be extracted from the PDF. "
					"Run debug_raw_tables to inspect the extracted table layout."
				)
			)

		results = []
		for vendor in vendors:
			results.append(create_quotation_for_vendor(data, vendor, file_id))

		frappe.db.commit()

		return {
			"status": "success",
			"quotations": results,
			"extracted_data": data,
		}

	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Supplier Quotation PDF Import")
		frappe.throw(_("Unable to create Supplier Quotation. Please check the Error Log for details."))


# =====================================================================
# EXTRACTION
# =====================================================================


@frappe.whitelist()
def extract_supplier_quotation_pdf(file_id: str):
	try:
		if not frappe.db.exists("File", file_id):
			frappe.throw(_("Invalid File"))

		file_doc = frappe.get_doc("File", file_id)
		file_path = file_doc.get_full_path()

		if not file_path.lower().endswith(".pdf"):
			frappe.throw(_("Only PDF files are allowed."))

		tables = extract_tables(file_path)
		return parse_brn_data(tables)

	except Exception:
		frappe.log_error(frappe.get_traceback(), "Supplier Quotation PDF Extraction")
		frappe.throw(_("Unable to extract PDF. Check Error Log for details."))


@frappe.whitelist()
def debug_raw_text(file_id: str):
	"""Kept for backward compatibility / quick sanity checks."""
	file_doc = frappe.get_doc("File", file_id)
	file_path = file_doc.get_full_path()
	return {"raw_text": extract_text(file_path)}


@frappe.whitelist()
def debug_raw_tables(file_id: str):
	"""The BRN layout is table-driven, so this is the more useful debug
	endpoint now - it shows exactly what pdfplumber's table detector sees."""
	file_doc = frappe.get_doc("File", file_id)
	file_path = file_doc.get_full_path()
	return {"tables": extract_tables(file_path)}
