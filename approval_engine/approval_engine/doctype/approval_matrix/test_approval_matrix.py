# Copyright (c) 2026, 8848 Digital and Contributors
# See license.txt

import frappe
from frappe.tests import UnitTestCase

from approval_engine.generator import band_condition


def _matrix(rows):
    """Build an in-memory (unsaved) Approval Matrix for validation tests."""
    m = frappe.new_doc("Approval Matrix")
    m.company = "_Test Company"
    m.document_type = "Purchase Order"
    for r in rows:
        m.append("detail", r)
    return m


def _row(dept, mn, mx, **extra):
    row = {"department": dept, "min_amount": mn, "max_amount": mx,
           "approver_1_user_1": "a@example.com"}
    row.update(extra)
    return row


class UnitTestApprovalMatrix(UnitTestCase):
    # ---------------- band_condition (pure logic) ----------------

    def test_band_condition_inclusive_bounds(self):
        self.assertEqual(band_condition("grand_total", 0, 100000),
                         "doc.grand_total <= 100000")
        self.assertEqual(band_condition("grand_total", 100001, 200000),
                         "doc.grand_total >= 100001 and doc.grand_total <= 200000")
        self.assertEqual(band_condition("grand_total", 200001, 0),
                         "doc.grand_total >= 200001")
        self.assertEqual(band_condition("grand_total", 0, 0), "")

    def test_band_condition_uses_configured_amount_field(self):
        self.assertEqual(band_condition("net_total", 0, 50000), "doc.net_total <= 50000")

    # ---------------- band validation (Min = prev.Max + 1, inclusive) ----------------

    def test_bands_max_plus_one_accepted(self):
        _matrix([_row("IT", 0, 100000), _row("IT", 100001, 0)])._validate_bands()

    def test_bands_three_contiguous_accepted(self):
        _matrix([_row("IT", 0, 100000), _row("IT", 100001, 200000),
                 _row("IT", 200001, 0)])._validate_bands()

    def test_single_catch_all_band_accepted(self):
        _matrix([_row("IT", 0, 0)])._validate_bands()

    def test_touching_bands_rejected(self):
        # old scheme (next.min == prev.max) is now invalid
        with self.assertRaises(frappe.ValidationError):
            _matrix([_row("IT", 0, 100000), _row("IT", 100000, 0)])._validate_bands()

    def test_gap_between_bands_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            _matrix([_row("IT", 0, 100000), _row("IT", 100002, 0)])._validate_bands()

    def test_highest_band_must_be_unbounded(self):
        # single bounded band leaves everything above it uncovered
        with self.assertRaises(frappe.ValidationError):
            _matrix([_row("IT", 0, 100000)])._validate_bands()

    def test_only_highest_band_may_be_unbounded(self):
        with self.assertRaises(frappe.ValidationError):
            _matrix([_row("IT", 0, 0), _row("IT", 1, 0)])._validate_bands()

    # ---------------- tier validation ----------------

    def test_tiers_must_be_contiguous(self):
        # Approver 3 filled while Approver 2 is blank -> reject
        row = _row("IT", 0, 0, approver_3_user_1="x@example.com")
        with self.assertRaises(frappe.ValidationError):
            _matrix([row])._validate_rows()

    def test_approver_1_required(self):
        row = {"department": "IT", "min_amount": 0, "max_amount": 0,
               "approver_2_user_1": "x@example.com"}
        with self.assertRaises(frappe.ValidationError):
            _matrix([row])._validate_rows()

    def test_two_tiers_contiguous_accepted(self):
        row = _row("IT", 0, 0, approver_2_user_1="b@example.com")
        _matrix([row])._validate_rows()
