# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Access rules and Purchase Invoice creation for the vendor-portal BRN
page (/brn/<name>). A portal supplier may only see, and invoice against,
a submitted "YEXP Proposal" BRN that lists one of its Suppliers in the
Comparision table -- the same rule the /brn list view applies.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, today
from frappe.utils.user import is_website_user

from approval_engine.approval_settlement.customization.purchase_order.utils import (
	create_portal_invoice_log,
)
from approval_engine.approval_vendor_portal.vendor_identity import get_vendor_suppliers

PORTAL_PO_TYPE = "YEXP Proposal"


def check_brn_portal_access(brn) -> None:
	"""
	Raise PermissionError unless the session user may view this BRN on the
	portal. Desk users need normal BRN read permission; portal suppliers
	need a submitted YEXP Proposal BRN that lists one of their Suppliers.

	Parameters:
	        brn (Document, required): The BRN being opened.

	Returns:
	        None
	"""
	if frappe.session.user == "Guest":
		raise frappe.PermissionError(_("Please log in to view this BRN."))

	if not is_website_user():
		brn.check_permission("read")
		return

	if brn.docstatus != 1 or brn.po_type != PORTAL_PO_TYPE or not get_portal_suppliers(brn):
		raise frappe.PermissionError(_("You are not permitted to view this BRN."))


def can_make_purchase_invoice(brn) -> bool:
	"""
	Whether the portal "Create Purchase Invoice" action applies to this BRN.

	Parameters:
	        brn (Document, required): The BRN shown on the portal page.

	Returns:
	        bool: True for a submitted, not-Closed BRN.
	"""
	return brn.docstatus == 1 and brn.status != "Closed"


def make_purchase_invoice_from_brn(
	brn_name: str,
	items: str,
	supplier_invoice_no: str | None = None,
	supplier_invoice_date: str | None = None,
) -> str:
	"""
	Create a draft Purchase Invoice from a BRN for the portal supplier.
	Items must be on the BRN, and qty/rate may not exceed what it approved.
	Inserted with ignore_permissions because portal suppliers can't create
	Purchase Invoices themselves -- safe only after the checks above.

	Parameters:
	        brn_name (str, required): The BRN to invoice against.
	        items (str, required): JSON list of {item_code, qty, rate}.
	        supplier_invoice_no (str, optional): The supplier's own invoice number.
	        supplier_invoice_date (str, optional): The supplier's own invoice date.

	Returns:
	        str: The new Purchase Invoice's name.
	"""
	brn = frappe.get_doc("BRN", brn_name)
	check_brn_portal_access(brn)

	if not can_make_purchase_invoice(brn):
		frappe.throw(_("A Purchase Invoice can only be created from a submitted, open BRN."))

	pi = frappe.new_doc("Purchase Invoice")
	pi.company = brn.company
	pi.posting_date = today()
	pi.supplier = _get_invoice_supplier(brn)
	pi.po_type = PORTAL_PO_TYPE
	pi.brn = brn.name
	pi.requisition_type = brn.requisition_type
	pi.bill_no = supplier_invoice_no or None
	pi.bill_date = supplier_invoice_date or None

	for item in _parse_invoice_items(brn, items):
		pi.append("items", item)

	pi.flags.ignore_permissions = True
	pi.run_method("set_missing_values")
	pi.run_method("calculate_taxes_and_totals")
	pi.insert(ignore_mandatory=True)

	create_portal_invoice_log(pi)

	return pi.name


def get_portal_suppliers(brn) -> list[str]:
	"""
	The session user's Suppliers that appear as a vendor on this BRN.

	Parameters:
	        brn (Document, required): The BRN being checked.

	Returns:
	        list[str]: Matching Supplier names; empty if none.
	"""
	brn_vendors = {row.existing_vendor for row in brn.comparision if row.existing_vendor}
	return [supplier for supplier in get_vendor_suppliers() if supplier in brn_vendors]


def _get_invoice_supplier(brn) -> str:
	"""
	Pick the Supplier to invoice as: the Preferred row's vendor if the user
	may act as it, else the user's first Supplier on this BRN. Desk users
	may act as any vendor on the BRN.

	Parameters:
	        brn (Document, required): The BRN being invoiced.

	Returns:
	        str: The Supplier name.
	"""
	if is_website_user():
		candidates = get_portal_suppliers(brn)
	else:
		candidates = [row.existing_vendor for row in brn.comparision if row.existing_vendor]

	if not candidates:
		frappe.throw(_("No Supplier on this BRN can be invoiced by you."))

	preferred_vendor = next((row.existing_vendor for row in brn.comparision if row.preferred), None)
	return preferred_vendor if preferred_vendor in candidates else candidates[0]


def _parse_invoice_items(brn, items: str) -> list[dict]:
	"""
	Parse and validate the portal's item lines against the BRN: each item
	must be on the BRN, qty must be positive, rate may not exceed the BRN's,
	and the total qty per item (across lines) may not exceed the BRN's
	total -- capped only where the BRN sets a qty, since Service BRNs may
	leave it empty.

	Parameters:
	        brn (Document, required): The BRN being invoiced.
	        items (str, required): JSON list of {item_code, qty, rate}.

	Returns:
	        list[dict]: Purchase Invoice Item rows.
	"""
	lines = json.loads(items) if isinstance(items, str) else items
	if not isinstance(lines, list) or not lines:
		frappe.throw(_("Please keep at least one item."))

	brn_limits = _get_brn_item_limits(brn)
	requested_qty = {}
	invoice_items = []

	for line in lines:
		item_code = line.get("item_code") if isinstance(line, dict) else None
		limit = brn_limits.get(item_code)
		if not limit:
			frappe.throw(_("Item {0} is not on this BRN.").format(item_code))

		qty, rate = flt(line.get("qty")), flt(line.get("rate"))
		requested_qty[item_code] = requested_qty.get(item_code, 0) + qty
		_validate_line_limits(item_code, limit, qty, rate, requested_qty[item_code])

		invoice_items.append(
			{"item_code": item_code, "qty": qty, "rate": rate, "expense_account": limit["expense_gl"]}
		)

	return invoice_items


def _get_brn_item_limits(brn) -> dict:
	"""
	Approved limits per item code on the BRN: total qty, highest rate, and
	the expense account of its first row.

	Parameters:
	        brn (Document, required): The BRN being invoiced.

	Returns:
	        dict: {item_code: {"qty": float, "rate": float, "expense_gl": str}}
	"""
	limits = {}
	for row in brn.items:
		limit = limits.setdefault(row.item_code, {"qty": 0, "rate": 0, "expense_gl": row.expense_gl})
		limit["qty"] += flt(row.qty)
		limit["rate"] = max(limit["rate"], flt(row.rate))

	return limits


def _validate_line_limits(
	item_code: str, limit: dict, qty: float, rate: float, total_qty: float
) -> None:
	"""
	Reject a line whose qty is not positive, whose rate exceeds the BRN's,
	or that pushes the item's total qty over the BRN's approved qty.

	Parameters:
	        item_code (str, required): The item being invoiced.
	        limit (dict, required): The item's limits from _get_brn_item_limits.
	        qty (float, required): Requested quantity on this line.
	        rate (float, required): Requested rate on this line.
	        total_qty (float, required): Requested quantity for this item so far.

	Returns:
	        None
	"""
	if qty <= 0 or rate < 0:
		frappe.throw(_("Item {0}: Qty must be positive and Rate cannot be negative.").format(item_code))

	if limit["qty"] and total_qty > limit["qty"]:
		frappe.throw(
			_("Item {0}: total Qty {1} is more than the BRN's approved Qty {2}.").format(
				item_code, total_qty, limit["qty"]
			)
		)

	if rate > limit["rate"]:
		frappe.throw(
			_("Item {0}: Rate {1} is more than the BRN's approved Rate {2}.").format(
				item_code, rate, limit["rate"]
			)
		)
