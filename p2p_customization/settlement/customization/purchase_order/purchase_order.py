from p2p_customization.settlement.customization.procure_to_pay.utils import (
	validate_fiscal_year_and_brn_dates,
)
from p2p_customization.settlement.customization.purchase_order.utils import (
	backdated_po_validation,
	validate_item_rate_and_qty_with_brn,
)
from p2p_customization.settlement.tax_withholding import apply_tax_withholding


def validate(doc, method=None):
	"""
	Purchase Order validate hook: fiscal-year/BRN-date alignment, BRN
	balance checks, and TDS withholding, in that order.

	Parameters:
		doc (Document, required): The Purchase Order document being validated.
		method (str, optional): The hook event name passed by Frappe.

	Returns:
		None
	"""
	validate_fiscal_year_and_brn_dates(doc, method)
	validate_item_rate_and_qty_with_brn(doc, method)
	apply_tax_withholding(doc, method)


def before_save(doc, method=None):
	"""
	Purchase Order before_save hook: enforce the backdated-posting window.

	Parameters:
		doc (Document, required): The Purchase Order document being saved.
		method (str, optional): The hook event name passed by Frappe.

	Returns:
		None
	"""
	backdated_po_validation(doc, method)
