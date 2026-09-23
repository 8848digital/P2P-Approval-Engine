# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""doc_events hook wiring for Purchase Invoice. Delegates to sibling files
(doc_events.py, itc_reversal.py, po_auto_close.py), procure_to_pay/utils.py
and settlement/tax_withholding.py for the actual logic.
"""

from approval_engine.settlement.customization.procure_to_pay.utils import (
	validate_fiscal_year_and_brn_dates,
)
from approval_engine.settlement.customization.purchase_invoice.doc_events import (
	validate_rate_and_qty,
)
from approval_engine.settlement.customization.purchase_invoice.itc_reversal import (
	handle_itc_reversal_on_submit,
	set_itc_status,
)
from approval_engine.settlement.customization.purchase_invoice.po_auto_close import (
	on_purchase_invoice_submit,
)
from approval_engine.settlement.tax_withholding import (
	apply_return_tds_reversal,
	apply_supplier_allowance_limit,
	cancel_supplier_allowance_consumed,
	force_apply_tds_for_locked_allowance_rows,
	update_supplier_allowance_consumed,
)


def before_validate(doc, method=None):
	"""
	Purchase Invoice before_validate hook: force TDS on rows whose supplier
	allowance is locked.

	Parameters:
	        doc (Document, required): The Purchase Invoice.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	force_apply_tds_for_locked_allowance_rows(doc, method)


def validate(doc, method=None):
	"""
	Purchase Invoice validate hook: TDS supplier allowance and return
	reversal, then fiscal-year/BRN-date alignment and BRN/PO balance checks.

	Parameters:
	        doc (Document, required): The Purchase Invoice document being validated.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	apply_supplier_allowance_limit(doc, method)
	apply_return_tds_reversal(doc, method)
	validate_fiscal_year_and_brn_dates(doc, method)
	validate_rate_and_qty(doc, method)


def after_insert(doc, method=None):
	"""
	Purchase Invoice after_insert hook: classify the ITC reversal requirement.

	Parameters:
	        doc (Document, required): The Purchase Invoice.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	set_itc_status(doc, method)


def on_update(doc, method=None):
	"""
	Purchase Invoice on_update hook: re-classify the ITC reversal requirement.

	Parameters:
	        doc (Document, required): The Purchase Invoice.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	set_itc_status(doc, method)


def on_submit(doc, method=None):
	"""
	Purchase Invoice on_submit hook: record TDS allowance consumed, close
	fully invoiced POs, and handle ITC reversal -- in that order.

	Parameters:
	        doc (Document, required): The Purchase Invoice.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	update_supplier_allowance_consumed(doc, method)
	on_purchase_invoice_submit(doc, method)
	handle_itc_reversal_on_submit(doc, method)


def on_cancel(doc, method=None):
	"""
	Purchase Invoice on_cancel hook: release the TDS allowance consumed.

	Parameters:
	        doc (Document, required): The Purchase Invoice.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	cancel_supplier_allowance_consumed(doc, method)
