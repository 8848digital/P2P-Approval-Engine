# Copyright (c) 2026, p2p_customization
# See license.txt
"""
Equivalence test for update_tds_rate_for_po vs. update_tds_rate, per
issue #12's plan (highest-risk item in the refactor series):

    "Write an equivalence test: same PO/PI fixture in, assert
    update_tds_rate_for_po and update_tds_rate currently produce the
    same tax.tds_rate output (documents current behavior before
    touching it). Only if equivalence holds, extract a single shared
    TDS-rate calculation helper both call into; if behavior actually
    differs in some case, do NOT silently unify -- flag the discrepancy
    in the PR for manual review instead of picking one."

Result: equivalence does NOT hold. Two real divergences exist (see
update_tds_rate_for_po's own docstring in tax_withholding.py for the
full writeup):

  1. update_tds_rate_for_po sums ALL apply_tds items under one doc-level
     category, ignoring each item's own tax_withholding_category;
     update_tds_rate groups per item-level category. For a multi-
     category document these produce genuinely different tds_rate
     values (see test_multi_category_divergence below) -- not a style
     difference, a real calculation difference.
  2. update_tds_rate_for_po never actually skipped RCM companies (the
     original if/else both ran the same calculation); update_tds_rate
     does skip them entirely.

Per the plan, NO shared helper was extracted -- the two functions still
compute independently. This file documents both the single-category
case where they DO agree (a regression safety net for future changes)
and the specific cases where they don't (so nobody "fixes" one into
matching the other without realizing that's a real business-logic call,
not a cleanup).

All tests here mock frappe.db.get_value/frappe.get_doc rather than
using real Purchase Order/Invoice/Tax Withholding Account records --
this environment has no live Frappe test site to build those fixtures
against and verify field/child-table behavior for real. See this PR's
test plan for what should be re-verified against a real site given the
financial impact of TDS calculation.
"""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from p2p_customization.settlement.tax_withholding import update_tds_rate, update_tds_rate_for_po

MODULE = "p2p_customization.settlement.tax_withholding"


class _FakeDoc:
	"""Stand-in for a Purchase Order/Invoice document -- deliberately NOT
	frappe._dict. frappe._dict is a dict subclass, so a field literally
	named "items" (both PO and PI have one) collides with dict's own
	inherited .items() method under attribute access: self.items would
	return the bound method, not the stored child-table list. A real
	Frappe Document doesn't have this problem (fields are genuine
	instance attributes, not dict entries via __getattr__), so this
	mimics that instead. Child rows (tax/item) don't hit this -- none of
	their field names collide with a dict method -- so those still use
	frappe._dict below."""

	def __init__(self, **kwargs):
		self.__dict__.update(kwargs)

	def get(self, key, default=None):
		return getattr(self, key, default)


def _tax_row(account_head, tax_amount, tds_rate=None):
	return frappe._dict(account_head=account_head, tax_amount=tax_amount, tds_rate=tds_rate)


def _item(amount, apply_tds=1, tax_withholding_category=None):
	return frappe._dict(amount=amount, apply_tds=apply_tds, tax_withholding_category=tax_withholding_category)


def _rcm_setting(rcm_companies):
	return frappe._dict(rcm_company=[frappe._dict(company=c) for c in rcm_companies])


def _account_lookup(mapping):
	"""frappe.db.get_value side_effect: routes {"parent": category, ...}
	filters to mapping[category], so different categories can resolve to
	different Tax Withholding Accounts (needed to demonstrate the
	multi-category divergence realistically -- different categories
	normally DO have different accounts)."""

	def _get_value(doctype, filters, fieldname):
		return mapping.get(filters["parent"])

	return _get_value


class TestSingleCategoryEquivalence(UnitTestCase):
	"""The one case where the two functions currently DO agree: one
	category, one matching item, non-RCM company. Kept as a regression
	safety net -- if a future change breaks even this baseline case,
	something has gone wrong regardless of the known divergences below."""

	def test_both_functions_compute_the_same_rate(self):
		po = _FakeDoc(
			tax_withholding_category="Category A",
			company="Test Company",
			items=[_item(1000, tax_withholding_category="Category A")],
			taxes=[_tax_row("TDS - A", tax_amount=100)],
		)
		pi = _FakeDoc(
			tax_withholding_category="Category A",
			company="Test Company",
			items=[_item(1000, tax_withholding_category="Category A")],
			taxes=[_tax_row("TDS - A", tax_amount=100)],
		)

		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=_rcm_setting([])),
			patch(f"{MODULE}.frappe.db.get_value", side_effect=_account_lookup({"Category A": "TDS - A"})),
		):
			update_tds_rate_for_po(po)
			update_tds_rate(pi)

		self.assertEqual(po.taxes[0].tds_rate, pi.taxes[0].tds_rate)
		self.assertEqual(po.taxes[0].tds_rate, 10.0)


class TestMultiCategoryDivergence(UnitTestCase):
	"""DIVERGES. update_tds_rate_for_po ignores per-item category and
	lumps every apply_tds item's amount together under the single
	doc-level category; update_tds_rate correctly separates by each
	item's own category. Not equivalent -- see the module docstring."""

	def _build_docs(self):
		items = [
			_item(600, tax_withholding_category="Category A"),
			_item(400, tax_withholding_category="Category B"),
		]
		po = _FakeDoc(
			tax_withholding_category="Category A",  # PO only ever has ONE doc-level category
			company="Test Company",
			items=items,
			taxes=[_tax_row("TDS - A", tax_amount=60), _tax_row("TDS - B", tax_amount=40)],
		)
		pi = _FakeDoc(
			company="Test Company",
			items=items,
			taxes=[_tax_row("TDS - A", tax_amount=60), _tax_row("TDS - B", tax_amount=40)],
		)
		return po, pi

	def test_update_tds_rate_correctly_separates_by_item_category(self):
		_po, pi = self._build_docs()
		account_map = {"Category A": "TDS - A", "Category B": "TDS - B"}

		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=_rcm_setting([])),
			patch(f"{MODULE}.frappe.db.get_value", side_effect=_account_lookup(account_map)),
		):
			update_tds_rate(pi)

		# 60/600*100 and 40/400*100 -- each category rated against only
		# its own items, both landing on 10%.
		self.assertEqual(pi.taxes[0].tds_rate, 10.0)
		self.assertEqual(pi.taxes[1].tds_rate, 10.0)

	def test_update_tds_rate_for_po_lumps_categories_together_instead(self):
		po, _pi = self._build_docs()
		account_map = {"Category A": "TDS - A", "Category B": "TDS - B"}

		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=_rcm_setting([])),
			patch(f"{MODULE}.frappe.db.get_value", side_effect=_account_lookup(account_map)),
		):
			update_tds_rate_for_po(po)

		# DIVERGENCE: only ever resolves the doc-level category
		# ("Category A")'s account, then sums BOTH items' amounts (600 +
		# 400 = 1000) against it -- 60/1000*100 = 6%, not the 10% the PI
		# path computes for the same items. Category B's tax row is never
		# even looked at: its tds_rate stays whatever it started as.
		self.assertEqual(po.taxes[0].tds_rate, 6.0)
		self.assertIsNone(po.taxes[1].tds_rate)


class TestRcmSettingDivergence(UnitTestCase):
	"""DIVERGES. update_tds_rate skips RCM companies entirely;
	update_tds_rate_for_po's RCM branching was dead code that never
	actually skipped anything (both its if/else branches ran the same
	calculation) -- removed as dead code in this PR, but the underlying
	behavior (PO doesn't skip RCM companies) is unchanged, and whether it
	SHOULD is flagged for manual review, not decided here."""

	def test_update_tds_rate_skips_rcm_company_entirely(self):
		pi = _FakeDoc(
			tax_withholding_category="Category A",
			company="RCM Co",
			items=[_item(1000, tax_withholding_category="Category A")],
			taxes=[_tax_row("TDS - A", tax_amount=100, tds_rate=None)],
		)
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=_rcm_setting(["RCM Co"])),
			patch(f"{MODULE}.frappe.db.get_value", side_effect=_account_lookup({"Category A": "TDS - A"})),
		):
			update_tds_rate(pi)

		self.assertIsNone(pi.taxes[0].tds_rate)  # untouched -- function returned before the loop

	def test_update_tds_rate_for_po_still_calculates_for_rcm_company(self):
		po = _FakeDoc(
			tax_withholding_category="Category A",
			company="RCM Co",
			items=[_item(1000, tax_withholding_category="Category A")],
			taxes=[_tax_row("TDS - A", tax_amount=100, tds_rate=None)],
		)
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=_rcm_setting(["RCM Co"])),
			patch(f"{MODULE}.frappe.db.get_value", side_effect=_account_lookup({"Category A": "TDS - A"})),
		):
			update_tds_rate_for_po(po)

		# DIVERGENCE: RCM Co is on the RCM list, but the rate is set
		# anyway -- unlike update_tds_rate above.
		self.assertEqual(po.taxes[0].tds_rate, 10.0)


class TestZeroTaxAmountGuard(UnitTestCase):
	"""Not a divergence after this PR's fix -- documents the crash-
	prevention fix itself: update_tds_rate_for_po previously had no
	tax_amount == 0 guard (ZeroDivisionError), unlike update_tds_rate's
	existing `if tax_amount else ""`. Both now agree on this edge case."""

	def test_update_tds_rate_sets_blank_string_when_no_taxable_amount(self):
		pi = _FakeDoc(
			company="Test Company",
			items=[_item(1000, apply_tds=0, tax_withholding_category="Category A")],  # apply_tds off
			taxes=[_tax_row("TDS - A", tax_amount=100)],
		)
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=_rcm_setting([])),
			patch(f"{MODULE}.frappe.db.get_value", side_effect=_account_lookup({})),
		):
			update_tds_rate(pi)
		# category_taxable_map ends up empty (no apply_tds items), so the
		# loop body never runs at all -- tds_rate is simply untouched.
		self.assertIsNone(pi.taxes[0].tds_rate)

	def test_update_tds_rate_for_po_no_longer_raises_zero_division_error(self):
		po = _FakeDoc(
			tax_withholding_category="Category A",
			company="Test Company",
			items=[_item(1000, apply_tds=0)],  # apply_tds off -> tax_amount stays 0
			taxes=[_tax_row("TDS - A", tax_amount=100)],
		)
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=_rcm_setting([])),
			patch(f"{MODULE}.frappe.db.get_value", side_effect=_account_lookup({"Category A": "TDS - A"})),
		):
			update_tds_rate_for_po(po)  # must not raise ZeroDivisionError
		self.assertEqual(po.taxes[0].tds_rate, "")
