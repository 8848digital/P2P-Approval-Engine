# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class FAQMaster(Document):
	"""A single onboarding FAQ question, synced onto the Supplier form as a
	Custom Field and onto the vendor onboarding web form (see
	settlement/doc_events/faq_master.py)."""
