# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Unit tests for the Purchase Order vs BRN checks (brn_validity.py): the BRN
must exist, be submitted and open, and the PO date must fall inside its
service window. BRN lookups are patched -- no database needed."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from approval_engine.settlement.customization.purchase_order.brn_validity import (
	validate_transaction_date_within_brn_validity,
)

MODULE = "approval_engine.settlement.customization.purchase_order.brn_validity"
BRN_DEFAULTS = {
	"docstatus": 1,
	"status": "Open",
	"service_start_date": "2026-01-01",
	"expiry_date": "2026-12-31",
}


def _fake_db(brn=None):
	"""A frappe.db stand-in whose get_value returns the given BRN fields (None = missing)."""

	def get_value(doctype, name, fields, as_dict=False):
		"""Return the requested BRN fields as a dict or tuple, like frappe.db.get_value."""
		if brn is None:
			return None
		values = {field: brn[field] for field in fields}
		return frappe._dict(values) if as_dict else tuple(values.values())

	db = MagicMock()
	db.get_value.side_effect = get_value
	return db


class TestPurchaseOrderBRNValidity(UnitTestCase):
	"""validate_transaction_date_within_brn_validity."""

	def _validate(self, transaction_date="2026-06-01", **brn_changes):
		"""Run the PO check against a BRN stand-in (brn_changes=None-able fields)."""
		brn = None if brn_changes.pop("missing", False) else {**BRN_DEFAULTS, **brn_changes}
		po = frappe._dict(brn="BRN-TEST-0001", transaction_date=transaction_date)
		with (
			patch("frappe.db", _fake_db(brn)),
			patch(f"{MODULE}.get_link_to_form", return_value="BRN-TEST-0001"),
		):
			validate_transaction_date_within_brn_validity(po)

	def test_po_without_brn_is_skipped(self):
		"""No BRN on the PO means nothing to check."""
		validate_transaction_date_within_brn_validity(frappe._dict(brn=None))

	def test_date_inside_window_passes(self):
		"""A submitted, open BRN with the date inside its window is accepted."""
		self._validate()

	def test_missing_brn_is_blocked(self):
		"""A BRN name that doesn't exist gives a clear error, not a crash."""
		self.assertRaises(frappe.ValidationError, self._validate, missing=True)

	def test_draft_cancelled_or_closed_brn_is_blocked(self):
		"""Only submitted, open BRNs may have POs."""
		self.assertRaises(frappe.ValidationError, self._validate, docstatus=0)
		self.assertRaises(frappe.ValidationError, self._validate, docstatus=2)
		self.assertRaises(frappe.ValidationError, self._validate, status="Closed")

	def test_date_outside_window_is_blocked(self):
		"""Before the service start or after the expiry date is rejected."""
		self.assertRaises(frappe.ValidationError, self._validate, transaction_date="2025-12-31")
		self.assertRaises(frappe.ValidationError, self._validate, transaction_date="2027-01-01")
