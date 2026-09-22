"""Reverses a supplier's consumed TDS allowance for a debit note. Split out
of tax_withholding.py to keep that file under the line-count cap - called
from its update_supplier_allowance_consumed hook.
"""

import frappe
from frappe.utils import flt


def reverse_supplier_allowance_consumed_for_return(self, settings) -> None:
	"""Mirror of cancel_supplier_allowance_consumed, but for a debit note
	instead of an actual cancellation: give back exactly the slice of
	Supplier.consumed_amount that the returned row(s) contributed.

	Each original item's own exempt amount was stamped onto
	custom_allowance_exempt_amount by apply_supplier_allowance_limit_impl
	at submit time, so this sums exactly the returned items' shares instead
	of approximating from the original invoice's total exempted amount -
	exact even for a return that covers only some of a multi-item, multi
	-category invoice, or a partial quantity/value return of one row."""
	if not self.get("return_against") or not self.get("items"):
		return

	original_items = {
		i.name: i
		for i in frappe.get_all(
			"Purchase Invoice Item",
			filters={"parent": self.return_against},
			fields=["name", "amount", "custom_allowance_exempt_amount"],
		)
	}
	if not original_items:
		return

	reversal = 0
	for item in self.items:
		source = original_items.get(item.get("purchase_invoice_item"))
		if not source or not source.amount or not source.custom_allowance_exempt_amount:
			continue
		ratio = abs(flt(item.amount)) / flt(source.amount)
		reversal += flt(source.custom_allowance_exempt_amount) * ratio

	if not reversal:
		return

	current = flt(settings.consumed_amount)
	new_total = max(current - reversal, 0)
	frappe.db.set_value("Supplier", self.supplier, "consumed_amount", new_total)
	frappe.db.set_value("Purchase Invoice", self.name, "custom_allowance_consumed_amount", -reversal)
