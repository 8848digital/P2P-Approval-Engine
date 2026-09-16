# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class NatureOfTransaction(Document):
	"""
	Master doctype storing the distinct kinds of financial transaction
	(e.g. Advance, Settlement) used to classify related settlement records.

	Carries no custom validation of its own; uniqueness of
	`nature_of_transition` is enforced by the DocType schema.
	"""

	pass
