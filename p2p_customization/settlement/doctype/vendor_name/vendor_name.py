# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class VendorName(Document):
	"""
	Master doctype storing distinct vendor names for use elsewhere in the
	settlement module (e.g. as a selectable reference list).

	Carries no custom validation of its own; uniqueness of `vendor` is
	enforced by the DocType schema.
	"""

	pass
