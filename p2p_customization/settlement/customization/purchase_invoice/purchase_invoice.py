# Copyright (c) 2026, p2p_customization
"""doc_events hook wiring for Purchase Invoice. Delegates to sibling files --
see doc_events.py and procure_to_pay/utils.py for the actual logic.
"""

from p2p_customization.settlement.customization.procure_to_pay.utils import (
	validate_fiscal_year_and_brn_dates,
)
from p2p_customization.settlement.customization.purchase_invoice.doc_events import (
	validate_rate_and_qty,
)


def validate(doc, method=None):
	"""
	Purchase Invoice validate hook: fiscal-year/BRN-date alignment, then
	BRN/PO balance checks.

	Parameters:
		doc (Document, required): The Purchase Invoice document being validated.
		method (str, optional): The hook event name passed by Frappe.

	Returns:
		None
	"""
	validate_fiscal_year_and_brn_dates(doc, method)
	validate_rate_and_qty(doc, method)
