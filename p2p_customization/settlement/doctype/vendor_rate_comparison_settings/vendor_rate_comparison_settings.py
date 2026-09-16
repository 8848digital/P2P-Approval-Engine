# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VendorRateComparisonSettings(Document):
	"""Single: whether/how the Purchase Order rate-comparison dialog is enabled (see customization/purchase_order/rate_comparison.py)."""
