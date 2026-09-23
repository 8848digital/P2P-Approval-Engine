# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Unit tests for the vendor-portal BRN rules (brn_portal.py): who may open
a BRN on the portal, and the qty/rate limits on portal Purchase Invoices.
Session, user type and supplier lookups are patched -- no database needed."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from approval_engine.settlement.doctype.brn import brn_portal

MODULE = "approval_engine.settlement.doctype.brn.brn_portal"


def _brn(**values):
	"""A submitted YEXP Proposal BRN stand-in listing SUP-1 (Preferred) and SUP-2.
	A plain object, not frappe._dict: a dict's own .items() would shadow the
	BRN's `items` child table."""
	fields = {
		"name": "BRN-TEST-0001",
		"docstatus": 1,
		"status": "Open",
		"po_type": "YEXP Proposal",
		"comparision": [
			frappe._dict(existing_vendor="SUP-1", preferred=1),
			frappe._dict(existing_vendor="SUP-2", preferred=0),
		],
		"items": [frappe._dict(item_code="ITEM-1", qty=10, rate=100, expense_gl="Expenses - T")],
	}
	fields.update(values)
	return SimpleNamespace(**fields)


def _lines(*lines):
	"""JSON-encode portal item lines as the page sends them."""
	return json.dumps([{"item_code": code, "qty": qty, "rate": rate} for code, qty, rate in lines])


class TestPortalAccess(UnitTestCase):
	"""check_brn_portal_access for guests, portal suppliers and desk users."""

	def _check(self, brn, user="vendor@example.com", website_user=True, suppliers=("SUP-1",)):
		"""Run the access check as the given user type and linked Suppliers."""
		with (
			patch("frappe.session", frappe._dict(user=user)),
			patch(f"{MODULE}.is_website_user", return_value=website_user),
			patch(f"{MODULE}.get_vendor_suppliers", return_value=list(suppliers)),
		):
			brn_portal.check_brn_portal_access(brn)

	def test_guest_is_blocked(self):
		"""Guests must log in first."""
		self.assertRaises(frappe.PermissionError, self._check, _brn(), user="Guest")

	def test_supplier_on_brn_is_allowed(self):
		"""A portal user whose Supplier is on the BRN may view it."""
		self._check(_brn())

	def test_supplier_not_on_brn_is_blocked(self):
		"""A portal user whose Supplier isn't on the BRN may not view it."""
		self.assertRaises(frappe.PermissionError, self._check, _brn(), suppliers=("SUP-9",))

	def test_draft_or_po_based_brn_is_blocked(self):
		"""Portal users only see submitted YEXP Proposal BRNs."""
		self.assertRaises(frappe.PermissionError, self._check, _brn(docstatus=0))
		self.assertRaises(frappe.PermissionError, self._check, _brn(po_type="PO Based"))

	def test_invoice_supplier_prefers_preferred_row(self):
		"""The Preferred vendor is used when the user may act as it."""
		with (
			patch(f"{MODULE}.is_website_user", return_value=True),
			patch(f"{MODULE}.get_vendor_suppliers", return_value=["SUP-2", "SUP-1"]),
		):
			self.assertEqual(brn_portal._get_invoice_supplier(_brn()), "SUP-1")


class TestPortalInvoiceLines(UnitTestCase):
	"""_parse_invoice_items: lines must stay within the BRN's approved items."""

	def test_line_within_limits_passes(self):
		"""A BRN item at or below the approved qty and rate is accepted."""
		items = brn_portal._parse_invoice_items(_brn(), _lines(("ITEM-1", 5, 100)))
		self.assertEqual(
			items, [{"item_code": "ITEM-1", "qty": 5, "rate": 100, "expense_account": "Expenses - T"}]
		)

	def test_item_not_on_brn_is_blocked(self):
		"""Items that aren't on the BRN are rejected."""
		self.assertRaises(
			frappe.ValidationError, brn_portal._parse_invoice_items, _brn(), _lines(("OTHER", 1, 1))
		)

	def test_rate_above_brn_is_blocked(self):
		"""The rate may not exceed the BRN's rate."""
		self.assertRaises(
			frappe.ValidationError, brn_portal._parse_invoice_items, _brn(), _lines(("ITEM-1", 1, 101))
		)

	def test_qty_cap_applies_across_lines(self):
		"""Splitting an item over two lines can't get around the qty cap."""
		self.assertRaises(
			frappe.ValidationError,
			brn_portal._parse_invoice_items,
			_brn(),
			_lines(("ITEM-1", 6, 100), ("ITEM-1", 6, 100)),
		)

	def test_zero_qty_or_empty_list_is_blocked(self):
		"""Qty must be positive and at least one line is required."""
		self.assertRaises(
			frappe.ValidationError, brn_portal._parse_invoice_items, _brn(), _lines(("ITEM-1", 0, 1))
		)
		self.assertRaises(frappe.ValidationError, brn_portal._parse_invoice_items, _brn(), "[]")

	def test_service_item_without_qty_is_not_capped(self):
		"""BRN items with no qty (Service) are only rate-capped."""
		brn = _brn(items=[frappe._dict(item_code="SVC", qty=None, rate=50, expense_gl="Expenses - T")])
		items = brn_portal._parse_invoice_items(brn, _lines(("SVC", 3, 50)))
		self.assertEqual(items[0]["qty"], 3)
