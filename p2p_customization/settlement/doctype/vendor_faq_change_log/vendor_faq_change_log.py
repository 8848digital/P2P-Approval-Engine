# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VendorFAQChangeLog(Document):
	"""Supplier child table row: an audit entry recording one FAQ answer's
	old/new value change (see doc_events/supplier.py's _log_faq_changes)."""
