# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""BRN/PO balance validation for Purchase Invoice items. Split out of
utils.py to keep that file under the line-count cap - imported by
doc_events.py's validate hook, never called from utils.py itself.
"""

from pypika import Case
from pypika import functions as fn

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form


def validate_item_qty_with_brn(self) -> None:
	"""
	Validate a standalone (non-PO) BRN-linked Purchase Invoice: item
	qty/rate (non-Service only) and amount must stay within the balance
	still available on the BRN, across every other non-cancelled PI
	against the same BRN.

	Parameters:
	        self (Document, required): The Purchase Invoice document being validated.

	Returns:
	        None
	"""
	if not self.items or not self.brn:
		return

	item_codes = list({d.item_code for d in self.items})

	# Get only requisition_type
	requisition_type = frappe.db.get_value("BRN", self.brn, "requisition_type")

	# Load only required BRN items
	brn_items = frappe.get_all(
		"BRN Item",
		filters={
			"parent": self.brn,
			"item_code": ["in", item_codes],
		},
		fields=["item_code", "qty", "rate", "amount"],
	)

	brn_item_map = {d.item_code: d for d in brn_items}

	# Get already invoiced qty/amount
	PII = frappe.qb.DocType("Purchase Invoice Item")
	PI = frappe.qb.DocType("Purchase Invoice")
	invoiced_data = (
		frappe.qb.from_(PII)
		.inner_join(PI)
		.on(PI.name == PII.parent)
		.select(
			PII.item_code,
			fn.Sum(PII.qty).as_("invoiced_qty"),
			fn.Sum(PII.amount).as_("invoiced_amount"),
		)
		.where(PI.brn == self.brn)
		.where(PI.name != self.name)
		.where(PI.docstatus < 2)
		.where(PII.item_code.isin(item_codes))
		.groupby(PII.item_code)
	).run(as_dict=True)

	invoiced_map = {d.item_code: (flt(d.invoiced_qty), flt(d.invoiced_amount)) for d in invoiced_data}

	brn_link = get_link_to_form("BRN", self.brn)

	for row in self.items:
		brn_item = brn_item_map.get(row.item_code)

		if not brn_item:
			frappe.throw(
				_("Row {0}: Item {1} is not found in BRN {2}").format(row.idx, row.item_code, brn_link)
			)

		brn_qty = flt(brn_item.qty)
		brn_rate = flt(brn_item.rate)
		brn_amount = flt(brn_item.amount)

		invoiced_qty, invoiced_amount = invoiced_map.get(row.item_code, (0, 0))

		row_qty = flt(row.qty)
		row_rate = flt(row.rate)
		row_amount = flt(row.amount)

		if requisition_type != "Service":
			if row_qty + invoiced_qty > brn_qty:
				frappe.throw(
					_("Row {0}: Qty {1} exceeds BRN Quantity. Available Qty: {2} for Item {3} in {4}").format(
						row.idx,
						row_qty,
						brn_qty - invoiced_qty,
						row.item_code,
						brn_link,
					),
					title=_("Qty Exceeded"),
				)

			if abs(row_rate - brn_rate) >= 0.01:
				frappe.throw(
					_("Row {0}: Rate {1} does not match BRN Rate {2} for Item {3} in {4}").format(
						row.idx,
						row_rate,
						brn_rate,
						row.item_code,
						brn_link,
					),
					title=_("Rate Mismatch"),
				)

		if row_amount + invoiced_amount > brn_amount:
			frappe.throw(
				_("Row {0}: Amount {1} exceeds BRN Amount. Available Amount: {2} for Item {3} in {4}").format(
					row.idx,
					row_amount,
					brn_amount - invoiced_amount,
					row.item_code,
					brn_link,
				),
				title=_("Amount Exceeded"),
			)


def validate_item_qty_with_po(self) -> None:
	"""
	Validate a PO-based Purchase Invoice: each row's qty/rate (non-Service
	only) and amount must stay within its Purchase Order Item's balance,
	across every other non-cancelled PI already invoiced against that PO
	line.

	Parameters:
	        self (Document, required): The Purchase Invoice document being validated.

	Returns:
	        None
	"""
	if not self.items:
		return

	# Collect all PO Detail names from the invoice items
	po_details = [row.po_detail for row in self.items if row.po_detail]
	if not po_details:
		return

	# Fetch PO Item info + cumulative qty/amount already invoiced (exclude current PI if submitted)
	POI = frappe.qb.DocType("Purchase Order Item")
	PO = frappe.qb.DocType("Purchase Order")
	PII = frappe.qb.DocType("Purchase Invoice Item")
	PI = frappe.qb.DocType("Purchase Invoice")

	still_counted = (PI.docstatus < 2) & (PI.name != self.name)
	invoiced_qty_case = Case().when(still_counted, PII.qty).else_(0)
	invoiced_amount_case = Case().when(still_counted, PII.amount).else_(0)

	po_item_map = (
		frappe.qb.from_(POI)
		.join(PO)
		.on(PO.name == POI.parent)
		.left_join(PII)
		.on(PII.po_detail == POI.name)
		.left_join(PI)
		.on(PI.name == PII.parent)
		.select(
			POI.name.as_("po_detail"),
			POI.item_code,
			POI.qty.as_("po_qty"),
			POI.rate.as_("po_rate"),
			POI.amount.as_("po_amount"),
			POI.parent.as_("po_name"),
			PO.brn,
			PO.requisition_type,
			fn.Coalesce(fn.Sum(invoiced_qty_case), 0).as_("already_invoiced_qty"),
			fn.Coalesce(fn.Sum(invoiced_amount_case), 0).as_("already_invoiced_amount"),
		)
		.where(POI.name.isin(po_details))
		.groupby(
			POI.name, POI.item_code, POI.qty, POI.rate, POI.amount, POI.parent, PO.brn, PO.requisition_type
		)
	).run(as_dict=True)

	po_map = {d.po_detail: d for d in po_item_map}

	for row in self.items:
		if not row.po_detail:
			continue

		po_item = po_map.get(row.po_detail)
		if not po_item:
			continue

		po_link = get_link_to_form("Purchase Order", po_item.po_name)

		# --- Validate Qty (only if requisition type != "Service") ---
		if po_item.requisition_type != "Service":
			available_qty = po_item.po_qty - po_item.already_invoiced_qty
			if row.qty + po_item.already_invoiced_qty > po_item.po_qty:
				frappe.throw(
					_(
						"Row {0}: Qty {1} exceeds Purchase Order Item Quantity. Available Qty: {2} for Item {3} in {4}"
					).format(row.idx, row.qty, available_qty, row.item_code, po_link),
					title=_("Qty Exceeded"),
				)

			# --- Validate Rate (only if requisition type != "Service") ---
			if abs(flt(row.rate) - flt(po_item.po_rate)) >= 0.01:
				frappe.throw(
					_("Row {0}: Rate {1} does not match Purchase Order Rate {2} for Item {3} in {4}").format(
						row.idx, row.rate, po_item.po_rate, row.item_code, po_link
					),
					title=_("Rate Mismatch"),
				)

		# --- Validate Amount always ---
		available_amount = po_item.po_amount - po_item.already_invoiced_amount
		row_amount = row.amount or (row.qty * row.rate)
		if row_amount + po_item.already_invoiced_amount > po_item.po_amount:
			frappe.throw(
				_(
					"Row {0}: Amount {1} exceeds Purchase Order Item Amount. Available Amount: {2} for Item {3} in {4}"
				).format(row.idx, row_amount, available_amount, row.item_code, po_link),
				title=_("Amount Exceeded"),
			)
