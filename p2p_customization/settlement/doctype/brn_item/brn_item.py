# Copyright (c) 2025, Satya and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class BRNItem(Document):
	"""BRN child table row: one item/service line being requisitioned, with its sanctioned qty/rate/amount."""
