# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Small helpers shared across the tax_withholding.py hook family. Split
out to keep tax_withholding.py under the line-count cap.
"""

import frappe
from frappe.utils import flt


def _get_pi_tds_category_map(self):
	"""Sum each TDS-applicable item's amount per tax_withholding_category
	for this Purchase Invoice -- only items actually part of the TDS calc
	(custom_tds_within_allowance or apply_tds)."""
	category_taxable_map = {}
	for item in self.get("items") or []:
		if not item.get("tax_withholding_category"):
			continue
		if not (item.get("custom_tds_within_allowance") or item.get("apply_tds")):
			continue
		category = item.tax_withholding_category
		category_taxable_map[category] = category_taxable_map.get(category, 0) + flt(item.amount)
	return category_taxable_map


def _get_supplier_allowance_settings(supplier, for_update=False):
	"""Fetch supplier's TDS allowance-limit fields. for_update=True locks
	the row for the write path (see update_supplier_allowance_consumed)."""
	return frappe.db.get_value(
		"Supplier",
		supplier,
		["set_allowance_limit_for_tds", "allowance_limit", "consumed_amount"],
		as_dict=True,
		for_update=for_update,
	)


def _tds_account_by_category(company, categories):
	"""Company's configured Tax Withholding Account per category - only
	categories with a real account are ones the allowance-limit/reversal
	logic actually acts on, so callers use this set to decide what counts."""
	result = {}
	for category in categories:
		if category in result:
			continue
		account = frappe.db.get_value(
			"Tax Withholding Account", {"parent": category, "company": company}, "account"
		)
		if account:
			result[category] = account
	return result
