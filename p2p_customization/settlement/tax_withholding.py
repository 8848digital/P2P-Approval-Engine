"""Purchase Order/Invoice TDS hook entrypoints. The heavier allowance-limit
split, return-reversal, and consumed-amount reversal logic lives in the
sibling tds_allowance_limit.py / tds_return_reversal.py / tds_allowance_consumed.py
modules - split out to keep this file under the line-count cap.
"""

import frappe
from erpnext.accounts.doctype.tax_withholding_entry.tax_withholding_entry import PurchaseTaxWithholding
from frappe.utils import flt

from p2p_customization.settlement.tds_allowance_consumed import (
	reverse_supplier_allowance_consumed_for_return,
)
from p2p_customization.settlement.tds_allowance_limit import apply_supplier_allowance_limit_impl
from p2p_customization.settlement.tds_return_reversal import (
	apply_return_tds_reversal_impl,
	get_return_category_ratios,
)
from p2p_customization.settlement.tds_shared import (
	_get_pi_tds_category_map,
	_get_supplier_allowance_settings,
	_tds_account_by_category,
)

__all__ = [
	"apply_return_tds_reversal",
	"apply_supplier_allowance_limit",
	"apply_tax_withholding",
	"cancel_supplier_allowance_consumed",
	"force_apply_tds_for_locked_allowance_rows",
	"update_supplier_allowance_consumed",
]


def apply_tax_withholding(doc, method=None):
	"""
	In version-16 TDS was removed from Purchase Order entirely. Rather
	than re-implement it, this reuses core's own Purchase Invoice TDS
	engine (PurchaseTaxWithholding) as-is -- same line-item-wise category
	grouping, thresholds, and Lower Deduction Certificate handling PI
	gets. Purchase Order is missing a handful of fields that engine
	reads directly off doc (it was only ever written against Purchase
	Invoice), so those are filled in here before handing off.

	No GL entries are posted from this -- Purchase Order has no
	make_gl_entries at all, so that side of PurchaseTaxWithholding
	(which only runs from Purchase Invoice's on_submit/make_gl_entries)
	never gets reached.

	Note: this DOES write real Tax Withholding Entry rows into the same
	cross-document threshold ledger Purchase Invoice uses. A submitted
	PO and the Purchase Invoice later raised against it will each
	contribute their own entries for what is really one transaction,
	so cumulative threshold tracking will double-count that amount
	until/unless the PO's entries are reconciled when the PI is made.
	"""
	doc.posting_date = doc.transaction_date
	doc.tax_withholding_group = doc.get("tax_withholding_group")
	doc.override_tax_withholding_entries = doc.get("override_tax_withholding_entries") or 0
	doc.ignore_tax_withholding_threshold = doc.get("ignore_tax_withholding_threshold") or 0
	doc.advances = doc.get("advances") or []

	PurchaseTaxWithholding(doc).on_validate()


def force_apply_tds_for_locked_allowance_rows(self, method=None) -> None:
	"""Purchase Invoice before_validate hook: a row locked read-only
	within-allowance by apply_supplier_allowance_limit must stay in the
	TDS calc even if the client submitted apply_tds unset."""
	for item in self.get("items") or []:
		if item.get("custom_tds_within_allowance") and item.get("tax_withholding_category"):
			item.apply_tds = 1


def apply_supplier_allowance_limit(self, method=None) -> None:
	"""Purchase Invoice validate hook: exempt whatever portion of this
	invoice still fits the supplier's remaining TDS allowance, when
	Supplier.set_allowance_limit_for_tds is on. No-op for returns (see
	apply_return_tds_reversal) or when the setting is off."""
	if not self.supplier or not self.get("items") or not self.get("taxes"):
		return

	if self.get("is_return"):
		return

	settings = _get_supplier_allowance_settings(self.supplier)
	if not settings or not settings.set_allowance_limit_for_tds:
		return

	apply_supplier_allowance_limit_impl(self, settings)


def apply_return_tds_reversal(self, method=None):
	"""A debit note's own item amounts don't reflect whatever
	allowance-limit exemption reduced the TDS on the original invoice, so
	letting core recompute TDS independently on the return over-reverses it.
	Instead, mirror the original invoice's actual withholding, scaled by how
	much of it this return covers - the same number that would come out of
	cancelling that portion of the original."""
	if not self.get("is_return") or not self.get("return_against"):
		return
	if not self.supplier or not self.get("items") or not self.get("taxes"):
		return

	settings = _get_supplier_allowance_settings(self.supplier)
	if not settings or not settings.set_allowance_limit_for_tds:
		return

	original = frappe.get_doc("Purchase Invoice", self.return_against)
	original_entries_by_category = {
		e.tax_withholding_category: e for e in original.get("tax_withholding_entries") or []
	}
	if not original_entries_by_category:
		return

	ratios = get_return_category_ratios(self, original)
	if not ratios:
		return

	apply_return_tds_reversal_impl(self, original_entries_by_category, ratios)


def update_supplier_allowance_consumed(self, method=None) -> None:
	"""Purchase Invoice on_submit hook: advance Supplier.consumed_amount
	by however much of this invoice's TDS-applicable amount actually
	counted toward the allowance (capped at the limit), or reverse it for
	a return -- see reverse_supplier_allowance_consumed_for_return."""
	if not self.supplier:
		return

	# for_update: this is the write path (unlike the settings reads in
	# apply_supplier_allowance_limit/apply_return_tds_reversal, which only
	# predict the split during validate) - locks the row so two concurrent
	# submits for the same supplier can't both read the same stale
	# consumed_amount and both write forward independently past the limit.
	settings = _get_supplier_allowance_settings(self.supplier, for_update=True)
	if not settings or not settings.set_allowance_limit_for_tds:
		return

	if self.get("is_return"):
		reverse_supplier_allowance_consumed_for_return(self, settings)
		return

	category_map = _get_pi_tds_category_map(self)
	# Only count categories that actually have a configured Tax Withholding
	# Account for this company - apply_supplier_allowance_limit bails out
	# entirely (no exemption applied, TDS left to core's own calc) when none
	# of a doc's categories have one, so consumed_amount must not advance
	# either in that case.
	valid_accounts = _tds_account_by_category(self.company, category_map.keys())
	total_amount = sum(amount for category, amount in category_map.items() if category in valid_accounts)
	if total_amount <= 0:
		return

	current = flt(settings.consumed_amount)
	limit = flt(settings.allowance_limit)
	# max(current, ...): if allowance_limit was lowered below what's already
	# consumed, this submit shouldn't claw consumed_amount back down - only
	# a cancel/return does that, via a positive stored contribution it can
	# reverse. Without this, a negative "contributed" here would make a
	# later cancel of *this* invoice incorrectly increase consumed_amount.
	new_total = max(current, min(current + total_amount, limit))
	contributed = new_total - current
	if not contributed:
		return

	frappe.db.set_value("Supplier", self.supplier, "consumed_amount", new_total)
	frappe.db.set_value("Purchase Invoice", self.name, "custom_allowance_consumed_amount", contributed)


def cancel_supplier_allowance_consumed(self, method=None) -> None:
	"""Purchase Invoice on_cancel hook: give back whatever this invoice
	contributed to Supplier.consumed_amount (stamped at submit time in
	custom_allowance_consumed_amount)."""
	if not self.supplier:
		return

	contributed = flt(self.get("custom_allowance_consumed_amount"))
	if not contributed:
		return

	current = flt(frappe.db.get_value("Supplier", self.supplier, "consumed_amount"))
	new_total = max(current - contributed, 0)
	frappe.db.set_value("Supplier", self.supplier, "consumed_amount", new_total)
