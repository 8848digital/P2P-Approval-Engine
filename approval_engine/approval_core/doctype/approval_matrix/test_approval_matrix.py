# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from approval_engine.approval_core.generator import band_condition


def _matrix(rows):
	"""Build an in-memory (unsaved) Approval Matrix for validation tests."""
	m = frappe.new_doc("Approval Matrix")
	m.company = "_Test Company"
	m.document_type = "Purchase Order"
	for r in rows:
		m.append("detail", r)
	return m


def _row(dept, mn, mx, **extra):
	"""Build one matrix row dict with a single Approver 1 user, plus any extra fields."""
	row = {
		"department": dept,
		"min_amount": mn,
		"max_amount": mx,
		"approver_1_user_1": "a@example.com",
	}
	row.update(extra)
	return row


class UnitTestApprovalMatrix(UnitTestCase):
	"""Pure-logic tests for band conditions and Approval Matrix validation (no database)."""

	# ---------------- band_condition (pure logic) ----------------

	def test_band_condition_inclusive_bounds(self):
		"""Band conditions use inclusive bounds, and 0 means unbounded on that side."""
		self.assertEqual(band_condition("grand_total", 0, 100000), "doc.grand_total <= 100000")
		self.assertEqual(
			band_condition("grand_total", 100001, 200000),
			"doc.grand_total >= 100001 and doc.grand_total <= 200000",
		)
		self.assertEqual(band_condition("grand_total", 200001, 0), "doc.grand_total >= 200001")
		self.assertEqual(band_condition("grand_total", 0, 0), "")

	def test_band_condition_uses_configured_amount_field(self):
		"""The configured amount field, not a hardcoded one, is baked into the condition."""
		self.assertEqual(band_condition("net_total", 0, 50000), "doc.net_total <= 50000")

	# ---------------- band validation (Min = prev.Max + smallest currency unit) ----------------
	# Amount fields are Currency (2 decimals), so the next band starts at prev.Max + 0.01,
	# NOT prev.Max + 1 -- a whole-number step would leave fractional amounts unmatched.

	def test_bands_decimal_step_accepted(self):
		"""Bands one currency unit apart (0.01) are contiguous."""
		_matrix([_row("IT", 0, 100000), _row("IT", 100000.01, 0)])._validate_bands()

	def test_bands_three_contiguous_decimal_accepted(self):
		"""Three contiguous decimal-stepped bands validate."""
		_matrix(
			[_row("IT", 0, 100000), _row("IT", 100000.01, 200000), _row("IT", 200000.01, 0)]
		)._validate_bands()

	def test_bands_whole_number_step_rejected(self):
		"""A whole-number step leaves fractional amounts uncovered, so it is refused."""
		# old scheme (next.min == prev.max + 1) now leaves a gap (100000.01 .. 100000.99)
		with self.assertRaises(frappe.ValidationError):
			_matrix([_row("IT", 0, 100000), _row("IT", 100001, 0)])._validate_bands()

	def test_single_catch_all_band_accepted(self):
		"""A single 0-0 band covers every amount."""
		_matrix([_row("IT", 0, 0)])._validate_bands()

	def test_touching_bands_rejected(self):
		"""Bands sharing a boundary value overlap, so they are refused."""
		# next.min == prev.max (shared boundary value) is an overlap -> invalid
		with self.assertRaises(frappe.ValidationError):
			_matrix([_row("IT", 0, 100000), _row("IT", 100000, 0)])._validate_bands()

	def test_gap_between_bands_rejected(self):
		"""A gap between bands leaves amounts unrouted, so it is refused."""
		with self.assertRaises(frappe.ValidationError):
			_matrix([_row("IT", 0, 100000), _row("IT", 100002, 0)])._validate_bands()

	def test_highest_band_must_be_unbounded(self):
		"""The top band must have Max 0, or high amounts match nothing."""
		# single bounded band leaves everything above it uncovered
		with self.assertRaises(frappe.ValidationError):
			_matrix([_row("IT", 0, 100000)])._validate_bands()

	def test_only_highest_band_may_be_unbounded(self):
		"""Only the top band may be unbounded."""
		with self.assertRaises(frappe.ValidationError):
			_matrix([_row("IT", 0, 0), _row("IT", 1, 0)])._validate_bands()

	# ---------------- tier validation ----------------

	def test_tiers_must_be_contiguous(self):
		"""Approver tiers must be filled in order, with no gaps."""
		# Approver 3 filled while Approver 2 is blank -> reject
		row = _row("IT", 0, 0, approver_3_user_1="x@example.com")
		with self.assertRaises(frappe.ValidationError):
			_matrix([row])._validate_rows()

	def test_approver_1_required(self):
		"""Every row needs at least one Approver 1 user."""
		row = {
			"department": "IT",
			"min_amount": 0,
			"max_amount": 0,
			"approver_2_user_1": "x@example.com",
		}
		with self.assertRaises(frappe.ValidationError):
			_matrix([row])._validate_rows()

	def test_two_tiers_contiguous_accepted(self):
		"""Tiers 1 and 2 filled in order validate."""
		row = _row("IT", 0, 0, approver_2_user_1="b@example.com")
		_matrix([row])._validate_rows()

	# ---------------- department / company validation ----------------

	def test_department_of_other_company_rejected(self):
		"""A department belonging to another company is refused."""
		m = _matrix([_row("Sales - OTHER", 0, 0)])  # matrix company is "_Test Company"
		with patch.object(frappe.db, "get_value", return_value="Other Company"):
			with self.assertRaises(frappe.ValidationError):
				m._validate_departments_company()

	def test_department_of_matrix_company_accepted(self):
		"""A department of the matrix's own company validates."""
		m = _matrix([_row("Sales - TC", 0, 0)])
		with patch.object(frappe.db, "get_value", return_value="_Test Company"):
			m._validate_departments_company()

	def test_department_without_company_skipped(self):
		"""A department with no company set skips the company check."""
		m = _matrix([_row("IT", 0, 0)])
		with patch.object(frappe.db, "get_value", return_value=None):
			m._validate_departments_company()
