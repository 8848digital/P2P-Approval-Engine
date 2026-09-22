# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
# See license.txt
"""Regression coverage for the BRN auto-close sweep, written before
converting its per-item raw SQL (_brn_amount_fully_invoiced /
_brn_qty_fully_invoiced) into a single batched frappe.qb query, per issue #7's
"add a regression test ... before changing query logic" instruction.

NOT executed against a live site -- see this PR's test plan.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from approval_engine.settlement.doctype.brn.brn_auto_close import (
	_billed_totals_by_item,
	_should_close_brn,
)


class TestShouldCloseBRN(UnitTestCase):
	"""_should_close_brn() routes to the right closure check by requisition_type."""

	def test_service_routes_to_amount_check(self):
		brn = frappe._dict(name="BRN-TEST-0001", requisition_type="Service")
		with (
			patch(
				"approval_engine.settlement.doctype.brn.brn_auto_close._brn_amount_fully_invoiced",
				return_value=True,
			) as amount_check,
			patch(
				"approval_engine.settlement.doctype.brn.brn_auto_close._brn_qty_fully_invoiced"
			) as qty_check,
		):
			self.assertTrue(_should_close_brn(brn))
			amount_check.assert_called_once_with(brn.name)
			qty_check.assert_not_called()

	def test_material_routes_to_qty_check(self):
		brn = frappe._dict(name="BRN-TEST-0002", requisition_type="Material")
		with (
			patch(
				"approval_engine.settlement.doctype.brn.brn_auto_close._brn_qty_fully_invoiced",
				return_value=False,
			) as qty_check,
			patch(
				"approval_engine.settlement.doctype.brn.brn_auto_close._brn_amount_fully_invoiced"
			) as amount_check,
		):
			self.assertFalse(_should_close_brn(brn))
			qty_check.assert_called_once_with(brn.name)
			amount_check.assert_not_called()

	def test_fixed_asset_routes_to_qty_check(self):
		brn = frappe._dict(name="BRN-TEST-0003", requisition_type="Fixed Asset")
		with patch(
			"approval_engine.settlement.doctype.brn.brn_auto_close._brn_qty_fully_invoiced",
			return_value=True,
		) as qty_check:
			self.assertTrue(_should_close_brn(brn))
			qty_check.assert_called_once_with(brn.name)

	def test_unknown_requisition_type_never_closes(self):
		brn = frappe._dict(name="BRN-TEST-0004", requisition_type="")
		self.assertFalse(_should_close_brn(brn))


class TestBilledTotalsByItem(IntegrationTestCase):
	"""_billed_totals_by_item() -- the batched replacement for the old
	per-BRN-item frappe.db.sql calls."""

	def test_empty_item_codes_short_circuits(self):
		# No item_codes -> no query at all, just {} -- documents the guard
		# added when batching (the original per-item loop never had this
		# case, since it always had at least one BRN item to iterate).
		self.assertEqual(_billed_totals_by_item("BRN-DOES-NOT-EXIST", []), {})

	def test_no_matching_invoices_returns_empty_dict(self):
		# An item_code with zero billed rows is simply absent from the
		# result (not a zero-valued entry) -- callers use
		# `(totals.get(item_code) or {}).get(...)  or 0`, which depends on
		# this absent-vs-zero distinction.
		result = _billed_totals_by_item("BRN-DOES-NOT-EXIST", ["ITEM-DOES-NOT-EXIST"])
		self.assertEqual(result, {})
