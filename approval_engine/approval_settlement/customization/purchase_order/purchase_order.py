# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from approval_engine.approval_settlement.customization.procure_to_pay.utils import (
	validate_fiscal_year_and_brn_dates,
)
from approval_engine.approval_settlement.customization.purchase_order.brn_validity import (
	validate_transaction_date_within_brn_validity,
)
from approval_engine.approval_settlement.customization.purchase_order.utils import (
	backdated_po_validation,
	validate_item_rate_and_qty_with_brn,
)
from approval_engine.approval_settlement.tax_withholding import apply_tax_withholding


def validate(doc, method=None):
	"""
	Purchase Order validate hook: fiscal-year/BRN-date alignment, the hard
	BRN validity-window check, BRN balance checks, and TDS withholding, in
	that order.

	Parameters:
	        doc (Document, required): The Purchase Order document being validated.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	validate_fiscal_year_and_brn_dates(doc, method)
	validate_transaction_date_within_brn_validity(doc, method)
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
