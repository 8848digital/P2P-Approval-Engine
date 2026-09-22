# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""PDF extraction and BRN header/table parsing for Supplier Quotation import.
Called from supplier_quotation.py's whitelisted endpoints.
"""

import re

import frappe

from approval_engine.settlement.doc_events.supplier_quotation_parsing import (
	clean,
	default_cost_center,
	find_table,
	lookup_field,
	parse_business_table,
	parse_comparison_table,
	resolve_company,
	to_frappe_date,
	value_after_marker,
)


def extract_text(file_path):
	import pdfplumber

	text = ""
	with pdfplumber.open(file_path) as pdf:
		for page in pdf.pages:
			text += (page.extract_text(layout=True) or "") + "\n"

	return text


def extract_tables(file_path):
	"""Business Requisition Notes are laid out as bordered tables, and
	pdfplumber's table detector reconstructs them far more reliably than
	regexing the wrapped, column-jumbled layout=True text does."""
	import pdfplumber

	all_tables = []
	with pdfplumber.open(file_path) as pdf:
		for page in pdf.pages:
			for table in page.extract_tables():
				all_tables.append(table)

	return all_tables


def parse_brn_data(tables):
	data = {
		"company": "",
		"cost_center": "",
		"currency": "",
		"transaction_date": "",
		"valid_till": "",
		"duration_of_service_months": "",
		"service_start_date": "",
		"msa_agreement": "",
		"gstin": "",
		"vendor_email": "",
		"preferred_supplier": "",  # informational only, no longer used to filter
		"vendors": [],
	}

	# ------------------------------------------------------------------
	# 1. Preferred Supplier (with reason) - kept for reference/debug only.
	# We now create a Supplier Quotation for every vendor row, not just
	# this one.
	# ------------------------------------------------------------------
	preferred_supplier_full = value_after_marker(tables, "Preferred Supplier")
	data["preferred_supplier"] = (
		preferred_supplier_full.split(" - ")[0].strip() if preferred_supplier_full else ""
	)

	# ------------------------------------------------------------------
	# 2. Comparison Vendor Costing table -> one entry per proposed vendor
	# ------------------------------------------------------------------
	comparison_table = find_table(tables, ["Proposed Vendors", "Onboarded"])
	data["vendors"] = parse_comparison_table(comparison_table)

	# ------------------------------------------------------------------
	# 3. Header block. Two templates are in use:
	#   - Newer "Proposal" layout: a single row with "Proposal From" /
	#     "Proposal To" / "Proposal No. ... Date ... Valid Till Date" -
	#     entity_name, gstin, transaction_date and valid_till all come
	#     straight from here.
	#   - Older BRN layout: a "To Be Filled by Business Users" table with
	#     an "Entity Name" row; transaction_date/valid_till aren't in the
	#     PDF at all there, so they default to today.
	# ------------------------------------------------------------------
	proposal_header = _parse_proposal_header(tables)

	if proposal_header["entity_name"] or proposal_header["transaction_date"] or proposal_header["valid_till"]:
		entity_name = proposal_header["entity_name"]
		data["gstin"] = proposal_header["gstin"]
		data["vendor_email"] = proposal_header["vendor_email"]
		data["transaction_date"] = proposal_header["transaction_date"] or frappe.utils.today()
		data["valid_till"] = proposal_header["valid_till"] or frappe.utils.today()
	else:
		business_table = find_table(tables, ["Particulars", "Details"])
		business_fields = parse_business_table(business_table)
		entity_name = lookup_field(business_fields, "Entity Name")
		data["transaction_date"] = frappe.utils.today()
		data["valid_till"] = frappe.utils.today()

	data["company"] = resolve_company(entity_name)

	# cost_center is not read from the PDF - it's always "Main - {company abbr}"
	data["cost_center"] = default_cost_center(data["company"])

	# ------------------------------------------------------------------
	# 4. Fixed / derived fields per business rule - common to every
	# quotation created from this BRN
	# ------------------------------------------------------------------
	data["service_start_date"] = str(frappe.utils.get_first_day(frappe.utils.today()))
	# duration_of_service_months is no longer a shared default - each
	# vendor row can quote its own periodicity, so it's parsed per-vendor
	# in _create_quotation_for_vendor via parse_qty_and_duration().

	return data


def _parse_proposal_header(tables):
	"""Newer 'Proposal' PDF layout ships one 3-column header row, e.g.:
	['Proposal From\\nName: ...\\n...\\nGSTIN : 27AAAFC0662N1ZF\\n...',
	 'Proposal To\\nEntity Name : Jio Financial Services\\nLimited\\nAddress : ...',
	 'Proposal\\nNo. : 0987\\nDate : 09/07/2026\\nValid Till Date :10/07/2026']

	Returns empty strings for anything not found, so the caller can fall
	back to the older BRN "To Be Filled by Business Users" table instead.
	"""
	result = {"entity_name": "", "gstin": "", "vendor_email": "", "transaction_date": "", "valid_till": ""}

	header_table = find_table(tables, ["Proposal From", "Proposal To"])
	if not header_table or not header_table[0]:
		return result

	row = header_table[0]
	from_cell = (row[0] or "") if len(row) > 0 else ""
	to_cell = (row[1] or "") if len(row) > 1 else ""
	meta_cell = (row[2] or "") if len(row) > 2 else ""

	gstin_match = re.search(r"GSTIN\s*:\s*([A-Z0-9]+)", from_cell)
	if gstin_match:
		result["gstin"] = gstin_match.group(1).strip()

	entity_match = re.search(r"Entity Name\s*:\s*(.*?)\n\s*Address", to_cell, re.S)
	if entity_match:
		result["entity_name"] = clean(entity_match.group(1))

	email_match = re.search(r"Vendor Email\s*:\s*(\S+@\S+)", to_cell)
	if email_match:
		result["vendor_email"] = email_match.group(1).strip()

	# "Date :" also occurs inside "Valid Till Date :" further down the same
	# cell, but re.search finds the leftmost match, and the proposal Date
	# line always comes first - so this reliably grabs the proposal date,
	# not the valid-till one.
	date_match = re.search(r"\bDate\s*:\s*(\d{2}/\d{2}/\d{4})", meta_cell)
	if date_match:
		result["transaction_date"] = to_frappe_date(date_match.group(1), "%d/%m/%Y")

	valid_match = re.search(r"Valid Till Date\s*:\s*(\d{2}/\d{2}/\d{4})", meta_cell)
	if valid_match:
		result["valid_till"] = to_frappe_date(valid_match.group(1), "%d/%m/%Y")

	return result
