# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Field/table parsing helpers shared by supplier_quotation_extraction.py and
supplier_quotation_creation.py - pure text/value parsing, no PDF I/O.
"""

import re
from datetime import datetime

import frappe


def parse_comparison_table(table):
	"""table rows look like:
	['1', 'Canon Business\\nSolutions India Pvt\\nLtd',
	 'Managed Print Service\\n- MFP Lease +\\nMaintenance',
	 '12 units / 12\\nmonths', None, '18,500', '22,20,000', 'Y']
	"""
	rows = []
	if not table:
		return rows

	for row in table:
		if not row or not row[0]:
			continue
		sno = row[0].strip()
		if not sno.isdigit():
			continue

		row = row + [None] * (8 - len(row))  # pad defensively

		# The comparison table is returned by pdfplumber as one block that
		# also includes its section-number row (e.g. "3  Comparison Vendor
		# Costing ...") and the related-party row, both of which start with
		# a digit too. Real vendor rows always carry a rate and an amount -
		# skip anything that doesn't.
		if row[5] is None or row[6] is None:
			continue

		rows.append(
			{
				"sno": sno,
				"name": clean(row[1]),
				"description": clean(row[2]),
				"qty_period": clean(row[3]),
				"rate": row[5],
				"amount": row[6],
				"onboarded": clean(row[7]).upper(),
			}
		)

	return rows


def parse_business_table(table):
	fields = {}
	if not table:
		return fields

	for row in table:
		if not row or len(row) < 2:
			continue
		label = clean(row[-2])
		value = clean(row[-1])
		if label and value:
			fields[label] = value

	return fields


def lookup_field(fields_dict, keyword):
	for key, value in fields_dict.items():
		if keyword.lower() in key.lower():
			return value
	return ""


def find_table(tables, must_contain):
	"""Returns the first table whose flattened text contains every string
	in must_contain (case-sensitive substring match)."""
	for table in tables:
		joined = " ".join(cell for row in table if row for cell in row if cell)
		if all(marker in joined for marker in must_contain):
			return table
	return None


def value_after_marker(tables, marker):
	"""Finds the row containing `marker` and returns the very next row's
	text - matches the '<label row> / <value row>' pattern the BRN uses
	for its free-text sections (Preferred Supplier, ...)."""
	for table in tables:
		for i, row in enumerate(table):
			joined = " ".join(c for c in row if c) if row else ""
			if marker in joined and i + 1 < len(table):
				nxt = table[i + 1]
				return clean(" ".join(c for c in nxt if c))
	return ""


def parse_qty_and_duration(qty_period_text):
	"""The comparison table's qty_period cell has been seen in two
	wordings:
	  - Old:  "12 units / 12 months"
	  - New:  "Qty/Users:-12\\nPeriodicity\\n(Months) - 12" (the PDF itself
	    uses an en dash before the number there; the regex below matches
	    that literal character on purpose)
	Returns (qty, uom_word, duration_of_service_months). uom_word is ""
	when the text doesn't spell out a unit (the new format doesn't).
	"""
	text = qty_period_text or ""
	qty = 0.0
	uom_word = ""
	duration = None

	# New format: explicit "Qty/Users" and "Periodicity (Months)" labels
	qty_match = re.search(r"Qty\s*/?\s*Users?\s*:?-?\s*(\d+(?:\.\d+)?)", text, re.I)
	duration_match = re.search(
		r"Periodicity.*?\(?\s*Months?\s*\)?\s*[-–:]?\s*(\d+(?:\.\d+)?)",  # noqa: RUF001 - matches a literal en dash in the PDF text
		text,
		re.I | re.S,
	)

	if qty_match:
		qty = float(qty_match.group(1))
	if duration_match:
		duration = float(duration_match.group(1))

	if not qty_match:
		# Old format fallback: "12 units / 12 months" - first number+word
		# pair is the qty/uom.
		m = re.search(r"([\d.]+)\s*([A-Za-z]+)", text)
		if m:
			qty = float(m.group(1))
			uom_word = m.group(2)

	if duration is None:
		# Old format fallback: any "<number> month(s)" in the text.
		m2 = re.search(r"(\d+(?:\.\d+)?)\s*months?", text, re.I)
		if m2:
			duration = float(m2.group(1))

	if duration is None:
		duration = 1  # last-resort default when nothing at all is found

	duration = int(duration) if float(duration).is_integer() else duration

	return qty, uom_word, duration


def clean(value):
	if not value:
		return ""
	return re.sub(r"\s+", " ", str(value)).strip()


def to_float(value):
	if value in (None, ""):
		return 0.0
	try:
		return float(str(value).replace(",", "").strip())
	except ValueError:
		return 0.0


def to_frappe_date(date_str, fmt):
	try:
		return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
	except Exception:
		return None


def resolve_company(entity_name):
	if not entity_name:
		return entity_name
	if frappe.db.exists("Company", entity_name):
		return entity_name
	match = frappe.db.get_value("Company", {"company_name": entity_name}, "name")
	return match or entity_name


def resolve_supplier(supplier_name):
	return frappe.db.get_value("Supplier", {"supplier_name": supplier_name}, "name") or ""


def default_cost_center(company):
	"""Every Company in Frappe auto-creates a default "Main - {abbr}" cost
	center, so we build it from the company's abbreviation instead of
	reading anything off the PDF."""
	if not company:
		return ""
	abbr = frappe.db.get_value("Company", company, "abbr")
	if not abbr:
		return ""
	return f"Main - {abbr}"
