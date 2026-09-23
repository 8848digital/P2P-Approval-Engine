# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Debit-note TDS reversal (mirrors the original invoice's actual
withholding, scaled by how much of it the return covers). Split out of
tax_withholding.py to keep that file under the line-count cap - called
from its apply_return_tds_reversal hook.
"""

import frappe
from frappe.utils import flt

from approval_engine.settlement.tds_shared import _tds_account_by_category


def get_return_category_ratios(self, original):
	"""Per tax_withholding_category, what fraction of the original
	invoice's TAXABLE amount in that category this return is reversing.

	Computed from each returned item's own original counterpart's taxable
	share (item.amount minus its stamped custom_allowance_exempt_amount),
	matched via purchase_invoice_item - not from raw item amounts. A
	category can span both fully-exempt and taxable items (the supplier
	allowance limit splits sequentially across items, not per category), so
	weighting by raw amount would misattribute TDS to a returned item that
	was never actually taxed. Also only counts items that were actually
	part of the TDS calc (custom_tds_within_allowance or apply_tds), so an
	item the user opted out of TDS entirely doesn't count as "taxable"
	merely because it was never stamped with an exempt amount.
	"""
	original_items_by_name = {i.name: i for i in original.get("items") or []}

	def _taxable_share(item):
		if not (item.get("custom_tds_within_allowance") or item.get("apply_tds")):
			return None
		return flt(item.amount) - flt(item.get("custom_allowance_exempt_amount"))

	original_taxable_by_category = {}
	for item in original.get("items") or []:
		category = item.get("tax_withholding_category")
		taxable = _taxable_share(item)
		if category and taxable is not None:
			original_taxable_by_category[category] = original_taxable_by_category.get(category, 0) + taxable

	returned_taxable_by_category = {}
	for item in self.get("items") or []:
		category = item.get("tax_withholding_category")
		source = original_items_by_name.get(item.get("purchase_invoice_item"))
		if not category or not source or not source.amount:
			continue
		source_taxable = _taxable_share(source)
		if source_taxable is None:
			continue
		# signed: item.amount is negative on a return, so this naturally
		# comes out negative (reversing) and scales down for a partial
		# quantity/value return of the same row.
		item_ratio = flt(item.amount) / flt(source.amount)
		returned_taxable_by_category[category] = (
			returned_taxable_by_category.get(category, 0) + source_taxable * item_ratio
		)

	ratios = {}
	for category, returned_taxable in returned_taxable_by_category.items():
		original_taxable = original_taxable_by_category.get(category)
		if original_taxable:
			ratios[category] = returned_taxable / original_taxable
	return ratios


def apply_return_tds_reversal_impl(self, original_entries_by_category, ratios) -> None:
	"""Rewrites self.taxes/_item_wise_tax_details/tax_withholding_entries
	to reflect the reversed portion of the original invoice's withholding,
	once apply_return_tds_reversal's guard clauses and ratio computation
	have confirmed there's something to reverse."""
	tds_account_by_category = _tds_account_by_category(
		self.company, original_entries_by_category.keys()
	)

	tds_accounts = set(tds_account_by_category.values())
	if not tds_accounts:
		return

	category_reversal = {}
	account_amounts = {}
	for category, ratio in ratios.items():
		entry = original_entries_by_category.get(category)
		account = tds_account_by_category.get(category)
		if not entry or not account:
			continue
		withholding = flt(entry.withholding_amount) * ratio
		taxable = flt(entry.taxable_amount) * ratio
		category_reversal[category] = {
			"taxable": taxable,
			"withholding": withholding,
			"rate": entry.tax_rate,
			"ldc": entry.lower_deduction_certificate,
			"reason": entry.under_withheld_reason,
		}
		account_amounts[account] = account_amounts.get(account, 0) + withholding

	if not category_reversal:
		return

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
		# else: nothing to reverse for this account - drop the row.

	if not changed:
		return

	self.set("taxes", remaining_taxes)
	self._item_wise_tax_details = [
		d
		for d in (self.get("_item_wise_tax_details") or [])
		if not (d.get("tax") and d["tax"].get("account_head") in tds_accounts)
	]

	items_by_category = {}
	for item in self.items:
		category = item.get("tax_withholding_category")
		if category in category_reversal:
			items_by_category.setdefault(category, []).append(item)
			item.apply_tds = 1

	for category, data in category_reversal.items():
		items = items_by_category.get(category) or []
		tax_row = kept_tax_by_account.get(tds_account_by_category.get(category))
		if not tax_row or not items:
			continue
		multiplier = -1 if tax_row.get("add_deduct_tax") == "Deduct" else 1
		category_amount_total = sum(flt(i.amount) for i in items) or 1
		for item in items:
			share = flt(item.amount) / category_amount_total
			self._item_wise_tax_details.append(
				frappe._dict(
					item=item,
					tax=tax_row,
					rate=data["rate"],
					amount=flt(data["withholding"] * share * multiplier, tax_row.precision("tax_amount")),
					taxable_amount=flt(data["taxable"] * share, tax_row.precision("tax_amount")),
				)
			)

	remaining_entries = []
	for entry in self.get("tax_withholding_entries") or []:
		if entry.tax_withholding_category not in category_reversal:
			remaining_entries.append(entry)
			continue
		data = category_reversal[entry.tax_withholding_category]
		if data["withholding"]:
			entry.taxable_amount = flt(data["taxable"], entry.precision("taxable_amount"))
			entry.withholding_amount = flt(data["withholding"], entry.precision("withholding_amount"))
			entry.lower_deduction_certificate = data["ldc"]
			entry.under_withheld_reason = data["reason"]
			remaining_entries.append(entry)
		# else: nothing to reverse - drop the ledger entry too.
	self.set("tax_withholding_entries", remaining_entries)

	self.calculate_taxes_and_totals()
