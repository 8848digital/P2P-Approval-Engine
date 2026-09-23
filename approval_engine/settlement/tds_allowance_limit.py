# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Supplier TDS allowance-limit application (the validate-time exempt/
taxable item split). Split out of tax_withholding.py to keep that file
under the line-count cap - called from its apply_supplier_allowance_limit
hook.
"""

import frappe
from frappe.utils import flt

from approval_engine.settlement.tds_shared import _tds_account_by_category


def apply_supplier_allowance_limit_impl(self, settings) -> None:
	"""Sequentially split TDS-applicable items into exempt/taxable
	portions against the supplier's remaining allowance (earlier item
	rows consume the allowance first), then rewrite self.taxes,
	_item_wise_tax_details, and tax_withholding_entries to reflect only
	the taxable portion, and stamp each item's own exempt amount."""
	items_with_category = [
		i for i in self.items if i.get("apply_tds") and i.get("tax_withholding_category")
	]
	if not items_with_category:
		return

	category_rates = {
		entry.tax_withholding_category: flt(entry.tax_rate)
		for entry in self.get("tax_withholding_entries") or []
	}

	tds_account_by_category = _tds_account_by_category(
		self.company, {i.tax_withholding_category for i in items_with_category}
	)

	tds_accounts = set(tds_account_by_category.values())
	if not tds_accounts:
		return

	remaining_allowance = max(flt(settings.allowance_limit) - flt(settings.consumed_amount), 0)

	# Sequential per-item exempt/taxable split.
	running_total = 0
	item_taxable = {}
	category_taxable = {}
	for item in items_with_category:
		item_amount = flt(item.amount)
		cumulative_before = running_total
		running_total += item_amount
		if running_total <= remaining_allowance:
			taxable = 0
		elif cumulative_before >= remaining_allowance:
			taxable = item_amount
		else:
			taxable = running_total - remaining_allowance
		item_taxable[item.name] = taxable
		category = item.tax_withholding_category
		category_taxable[category] = category_taxable.get(category, 0) + taxable

	account_amounts = {}
	for category, taxable_amount in category_taxable.items():
		account = tds_account_by_category.get(category)
		if not account:
			continue
		rate = category_rates.get(category, 0)
		account_amounts[account] = account_amounts.get(account, 0) + flt(taxable_amount) * rate / 100

	remaining_taxes = []
	kept_tax_by_account = {}
	changed = False
	for tax in self.taxes:
		if tax.account_head not in tds_accounts:
			remaining_taxes.append(tax)
			continue
		changed = True
		new_amount = flt(account_amounts.get(tax.account_head, 0), tax.precision("tax_amount"))
		if new_amount:
			tax.tax_amount = new_amount
			tax.dont_recompute_tax = 1
			kept_tax_by_account[tax.account_head] = tax
			remaining_taxes.append(tax)
		# else: fully within the remaining allowance - drop the row entirely.

	if not changed:
		return

	self.set("taxes", remaining_taxes)
	self._item_wise_tax_details = [
		d
		for d in (self.get("_item_wise_tax_details") or [])
		if not (d.get("tax") and d["tax"].get("account_head") in tds_accounts)
	]
	for item in items_with_category:
		taxable = item_taxable.get(item.name, 0)
		if not taxable:
			continue
		tax_row = kept_tax_by_account.get(tds_account_by_category.get(item.tax_withholding_category))
		if not tax_row:
			continue
		rate = category_rates.get(item.tax_withholding_category, 0)
		multiplier = -1 if tax_row.get("add_deduct_tax") == "Deduct" else 1
		self._item_wise_tax_details.append(
			frappe._dict(
				item=item,
				tax=tax_row,
				rate=rate,
				amount=flt(flt(taxable) * rate / 100 * multiplier, tax_row.precision("tax_amount")),
				taxable_amount=flt(taxable, tax_row.precision("tax_amount")),
			)
		)

	remaining_entries = []
	for entry in self.get("tax_withholding_entries") or []:
		if entry.tax_withholding_category not in category_taxable:
			remaining_entries.append(entry)
			continue
		taxable_amount = category_taxable[entry.tax_withholding_category]
		new_withholding = flt(
			flt(taxable_amount) * flt(entry.tax_rate) / 100, entry.precision("withholding_amount")
		)
		if new_withholding:
			entry.taxable_amount = flt(taxable_amount, entry.precision("taxable_amount"))
			entry.withholding_amount = new_withholding
			remaining_entries.append(entry)
		# else: fully within the remaining allowance - drop the ledger entry too.
	self.set("tax_withholding_entries", remaining_entries)

	self.calculate_taxes_and_totals()

	for item in items_with_category:
		taxable = item_taxable.get(item.name, 0)
		item.custom_allowance_exempt_amount = flt(item.amount) - flt(taxable)
		# server is authoritative here, not just a fallback for whatever the
		# client-side lock predicted - a row fully within the allowance gets
		# unchecked and locked read-only regardless of what apply_tds/
		# custom_tds_within_allowance were coming in.
		item.custom_tds_within_allowance = 0 if taxable else 1
		if item.custom_tds_within_allowance:
			item.apply_tds = 0
