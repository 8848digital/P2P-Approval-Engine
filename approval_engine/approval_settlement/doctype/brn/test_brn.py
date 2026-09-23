# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Unit tests for the BRN Comparision rules (doc_events.py). Pure logic on
in-memory frappe._dict stand-ins -- no database needed."""

import frappe
from frappe.tests import UnitTestCase

from approval_engine.approval_settlement.doctype.brn.doc_events import (
	validate_comparision_rows,
	validate_preferred_row_details,
)


def _row(**values):
	"""Build a Comparision row stand-in with sensible defaults."""
	row = {"idx": 1, "preferred": 0, "related_party": "No", "rate": 0}
	row.update(values)
	return frappe._dict(row)


def _brn(rows, **flags):
	"""Build a BRN stand-in with the given Comparision rows and Single/Multi/RPT flags."""
	return frappe._dict(comparision=rows, **flags)


def _rows(count, **values):
	"""count rows, the first marked Preferred."""
	return [_row(idx=i + 1, preferred=1 if i == 0 else 0, **values) for i in range(count)]


class TestComparisionRows(UnitTestCase):
	"""Single/Multi/RPT, row-count, quote and Preferred rules."""

	def test_single_with_one_row_passes(self):
		"""Single with exactly one Preferred row is valid."""
		validate_comparision_rows(_brn(_rows(1), single=1))

	def test_single_with_two_rows_is_blocked(self):
		"""Single allows only one row."""
		self.assertRaises(frappe.ValidationError, validate_comparision_rows, _brn(_rows(2), single=1))

	def test_single_and_multi_together_is_blocked(self):
		"""Single cannot be combined with Multi."""
		self.assertRaises(
			frappe.ValidationError, validate_comparision_rows, _brn(_rows(3), single=1, multi=1)
		)

	def test_neither_single_nor_multi_is_blocked(self):
		"""One comparison mode must be chosen."""
		self.assertRaises(frappe.ValidationError, validate_comparision_rows, _brn(_rows(1)))

	def test_multi_needs_three_rows(self):
		"""Multi with fewer than 3 rows is blocked; more than 3 is fine."""
		self.assertRaises(frappe.ValidationError, validate_comparision_rows, _brn(_rows(2), multi=1))
		validate_comparision_rows(_brn(_rows(5), multi=1))

	def test_rpt_counts_as_multi(self):
		"""RPT alone needs 3 quoted rows, like Multi."""
		self.assertRaises(frappe.ValidationError, validate_comparision_rows, _brn(_rows(3), rpt=1))
		validate_comparision_rows(_brn(_rows(3, rate=10), rpt=1))

	def test_related_party_allowed_under_single(self):
		"""A Related Party vendor on a Single BRN no longer needs 3 quotes."""
		validate_comparision_rows(_brn(_rows(1, related_party="Yes"), single=1))

	def test_related_party_under_multi_needs_three_quotes(self):
		"""Under Multi, a Related Party vendor requires 3 rows with Rate filled in."""
		self.assertRaises(
			frappe.ValidationError,
			validate_comparision_rows,
			_brn(_rows(3, related_party="Yes"), multi=1),
		)
		validate_comparision_rows(_brn(_rows(3, related_party="Yes", rate=10), multi=1))

	def test_exactly_one_preferred_row(self):
		"""Zero or two Preferred rows are both blocked."""
		none_preferred = [_row(idx=i + 1) for i in range(3)]
		self.assertRaises(
			frappe.ValidationError, validate_comparision_rows, _brn(none_preferred, multi=1)
		)

		two_preferred = _rows(3)
		two_preferred[1].preferred = 1
		self.assertRaises(
			frappe.ValidationError, validate_comparision_rows, _brn(two_preferred, multi=1)
		)


class TestPreferredRowDetails(UnitTestCase):
	"""Email ID and Justification on the Preferred row, checked at submit."""

	def test_missing_justification_is_blocked(self):
		"""A Preferred row without Justification cannot be submitted."""
		brn = _brn([_row(preferred=1, email_id="vendor@example.com")])
		self.assertRaises(frappe.ValidationError, validate_preferred_row_details, brn)

	def test_missing_email_is_blocked(self):
		"""A Preferred row without Email ID cannot be submitted."""
		brn = _brn([_row(preferred=1, justification="Lowest quote")])
		self.assertRaises(frappe.ValidationError, validate_preferred_row_details, brn)

	def test_complete_preferred_row_passes(self):
		"""Email ID and Justification present: submit is allowed."""
		brn = _brn([_row(preferred=1, email_id="vendor@example.com", justification="Lowest quote")])
		validate_preferred_row_details(brn)

	def test_non_preferred_rows_are_not_checked(self):
		"""Only the Preferred row needs the details."""
		brn = _brn(
			[
				_row(preferred=1, email_id="vendor@example.com", justification="Lowest quote"),
				_row(idx=2),
			]
		)
		validate_preferred_row_details(brn)
