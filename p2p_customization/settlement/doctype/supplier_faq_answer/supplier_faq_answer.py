# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class SupplierFAQAnswer(Document):
	"""Child table row: one onboarding FAQ question/answer pair (faq_question, question_label, answer)."""
