# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""BRN balance-consumption helper for validate_item_rate_and_qty_with_brn in
utils.py - split out to keep utils.py under the line-count cap.
"""

import frappe
from pypika import functions as fn


class POI_Fields:
	"""Which Purchase Order Item aggregate _sum_other_po_items() computes."""

	qty = "qty"
	amount = "amount"


def _sum_other_po_items(doc, item_code: str, field: str) -> float:
	"""
	Sum qty (or qty*rate as amount) for item_code across every other
	non-cancelled Purchase Order linked to doc's BRN.

	Parameters:
		doc (Document, required): The Purchase Order being validated
			(excluded from the sum by name).
		item_code (str, required): The Item to sum.
		field (str, required): POI_Fields.qty or POI_Fields.amount.

	Returns:
		float: The summed value, or 0 if no other PO has this item.
	"""
	POI = frappe.qb.DocType("Purchase Order Item")
	PO = frappe.qb.DocType("Purchase Order")
	measure = POI.qty if field == POI_Fields.qty else POI.qty * POI.rate

	result = (
		frappe.qb.from_(POI)
		.join(PO)
		.on(PO.name == POI.parent)
		.select(fn.Coalesce(fn.Sum(measure), 0))
		.where(PO.docstatus < 2)
		.where(PO.brn == doc.brn)
		.where(POI.item_code == item_code)
		.where(PO.name != doc.name)
	).run()

	return result[0][0]
