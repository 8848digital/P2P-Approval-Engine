# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Unit tests for how create_brn adds quotation vendors to an existing BRN
(quotation_actions.py): Multi is topped up to 3 rows and new vendors fill
empty rows first. Pure logic on in-memory stand-ins -- no database needed."""

import frappe
from frappe.tests import UnitTestCase

from approval_engine.settlement.customization.supplier_quotation.quotation_actions import (
	MULTI_MIN_COMPARISION_ROWS,
	_add_quotation_row,
	_top_up_comparision_rows,
)


class _BRN:
	"""Minimal BRN stand-in: a comparision list and Document.append()."""

	def __init__(self, vendor_names):
		"""Start with one row per vendor name."""
		self.comparision = [frappe._dict(vendor_name=name) for name in vendor_names]

	def append(self, fieldname, row):
		"""Append a row to the child table, like Document.append()."""
		self.comparision.append(frappe._dict(row))


def _vendor_names(brn):
	"""The vendor_name of every Comparision row, None for empty rows."""
	return [row.get("vendor_name") for row in brn.comparision]


class TestQuotationRows(UnitTestCase):
	"""_add_quotation_row and _top_up_comparision_rows."""

	def _add(self, brn, vendor_name):
		"""Add one quotation's vendor the way create_brn does."""
		_add_quotation_row(brn, {"vendor_name": vendor_name})
		_top_up_comparision_rows(brn, MULTI_MIN_COMPARISION_ROWS)

	def test_second_quotation_tops_up_to_three_rows(self):
		"""Switching to Multi on the 2nd quotation leaves 3 rows so the draft saves."""
		brn = _BRN(["A"])
		self._add(brn, "B")
		self.assertEqual(_vendor_names(brn), ["A", "B", None])

	def test_next_quotation_fills_empty_row_first(self):
		"""The 3rd quotation fills the empty row instead of adding a 4th."""
		brn = _BRN(["A"])
		self._add(brn, "B")
		self._add(brn, "C")
		self.assertEqual(_vendor_names(brn), ["A", "B", "C"])

	def test_further_quotations_append(self):
		"""Once all rows are used, new vendors are appended."""
		brn = _BRN(["A", "B", "C"])
		self._add(brn, "D")
		self.assertEqual(_vendor_names(brn), ["A", "B", "C", "D"])
