# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""doc_events hook wiring for Supplier Quotation. Delegates to utils.py for
the actual logic.
"""

from approval_engine.approval_settlement.customization.supplier_quotation.utils import (
	ensure_requisition_number,
)


def on_update_after_submit(doc, method=None):
	"""
	Supplier Quotation on_update_after_submit hook: assign a Requisition ID
	when this quotation was raised against "New Requisition" and hasn't
	been assigned one yet.

	Parameters:
	        doc (Document, required): The Supplier Quotation document.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	ensure_requisition_number(doc)
