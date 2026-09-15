import frappe
from .utils import validate_item_qty_with_brn, validate_item_qty_with_po



def validate_rate_and_qty(self, method=None):
	has_brn_po = False
	po_names = [d.purchase_order for d in self.items if d.purchase_order]

	if po_names:
		# Check if any of these POs has a BRN value
		has_brn_po = frappe.db.exists("Purchase Order", {"name": ["in", po_names], "brn": ["!=", ""]})

	# Case 1: PO-based Purchase Invoice
	if has_brn_po:
		validate_item_qty_with_po(self)

	# Case 2: Standalone BRN-based Purchase Invoice
	if self.brn and not any(d.purchase_order for d in self.items):
		validate_item_qty_with_brn(self)