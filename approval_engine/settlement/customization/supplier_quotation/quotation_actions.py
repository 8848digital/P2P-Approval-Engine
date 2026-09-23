# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Supplier Quotation / BRN creation and PDF import. Exposed to the client
through settlement/api/v1/supplier_quotation.py. Extraction/parsing helpers
live in the sibling supplier_quotation_creation.py,
supplier_quotation_extraction.py and supplier_quotation_parsing.py modules.
"""

import frappe
from frappe import _

from approval_engine.settlement.customization.supplier_quotation.supplier_quotation_creation import (
	create_quotation_for_vendor,
)
from approval_engine.settlement.customization.supplier_quotation.supplier_quotation_extraction import (
	extract_tables,
	parse_brn_data,
)

# Multi/RPT BRNs need at least this many Comparision rows (see brn/doc_events.py).
MULTI_MIN_COMPARISION_ROWS = 3


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
				"quotation_requisition_id": supplier_quotation.custom_requisition_no,
				"supplier_quotation": supplier_quotation.name,
				"single": 1,
			}
		)
		brn.append(
			"comparision", _comparision_row_from_quotation(supplier_quotation, default_preferred=True)
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
		_add_quotation_row(brn, _comparision_row_from_quotation(supplier_quotation))
		_top_up_comparision_rows(brn, MULTI_MIN_COMPARISION_ROWS)
	brn.flags.ignore_mandatory = True
	brn.save()
	frappe.db.set_value(
		"Supplier Quotation", supplier_quotation.name, "custom_brn", brn.name, update_modified=False
	)
	return {"name": brn.name, "is_new": False}


def _add_quotation_row(brn, row_data: dict) -> None:
	"""
	Put a quotation's vendor into the first empty Comparision row (one left
	by _top_up_comparision_rows), or append a new row if none is empty.

	Parameters:
	        brn (Document, required): The draft BRN being updated.
	        row_data (dict, required): Row values from _comparision_row_from_quotation.

	Returns:
	        None
	"""
	empty_row = next(
		(row for row in brn.comparision if not (row.existing_vendor or row.vendor_name)), None
	)
	if empty_row is not None:
		empty_row.update(row_data)
		return

	brn.append("comparision", row_data)


def _top_up_comparision_rows(brn, min_rows: int) -> None:
	"""
	Append empty Comparision rows until the BRN has at least `min_rows`.
	create_brn() switches a BRN to Multi on its second quotation, but Multi
	needs 3 rows to save -- the blank rows let the draft save so the user
	can fill in the remaining vendors.

	Parameters:
	        brn (Document, required): The draft BRN being updated.
	        min_rows (int, required): Minimum number of Comparision rows.

	Returns:
	        None
	"""
	for _row_index in range(min_rows - len(brn.comparision)):
		brn.append("comparision", {})


def _comparision_row_from_quotation(supplier_quotation, default_preferred: bool = False) -> dict:
	"""Build a BRN Comparision row from a Supplier Quotation. BRN itself no
	longer carries vendor/MSA fields at the top level -- those moved onto
	this child table -- so this is the single place create_brn() maps a
	quotation's vendor/MSA data onto a row, for both the new-BRN and
	append-to-existing-BRN paths above.

	workflow_state is only a real attribute once a Workflow is configured
	for Supplier Quotation on this site; doc.get() returns None instead of
	raising when it isn't, so absent that workflow a row is only marked
	Preferred via default_preferred instead.

	Parameters:
	        supplier_quotation (Document, required): The Supplier Quotation
	                being converted into a BRN Comparision row.
	        default_preferred (bool, optional): True for the sole row of a
	                brand-new single-vendor BRN, where BRN's own "exactly one
	                Preferred row" rule leaves no other reasonable default --
	                there is no second vendor to compare against yet. False (the
	                default) for a row being added to a Multi/RPT BRN alongside
	                others, where Preferred should only follow a real workflow
	                decision, not every new row appended.

	Returns:
	        dict: A BRN Comparision row, ready to pass to Document.append().
	"""
	preferred = default_preferred or supplier_quotation.get("workflow_state") == "Selected"
	return {
		"is_new_vendor": supplier_quotation.is_new_vendor,
		"is_existing_vendor": supplier_quotation.is_existing_vendor,
		"vendor_name": supplier_quotation.new_vendor or supplier_quotation.supplier_name,
		"existing_vendor": supplier_quotation.supplier,
		"msa_agreement": supplier_quotation.msa_agreement,
		"preferred": 1 if preferred else 0,
	}


# =====================================================================
# CREATE SUPPLIER QUOTATION
# =====================================================================


def create_supplier_quotation_from_file(file_id: str):
	"""One BRN can propose several vendors in its comparison table
	(existing + new). We create one Supplier Quotation per vendor row,
	not just the preferred one, so every proposal is captured."""
	try:
		data = extract_supplier_quotation_pdf(file_id)

		frappe.log_error(title="SQ Extraction Debug", message=frappe.as_json(data))

		vendors = data.get("vendors") or []
		if not vendors:
			frappe.throw(_("No vendors could be extracted from the PDF. " "Check the PDF's table layout."))

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


def extract_supplier_quotation_pdf(file_id: str):
	"""
	Extract BRN/vendor data from an uploaded proposal PDF.

	Parameters:
	        file_id (str, required): The File document name of the uploaded PDF.

	Returns:
	        dict: Parsed proposal data, including a "vendors" list.
	"""
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
