# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from p2p_customization.settlement.doc_events.tds_reference import (
	create_tax_withholding_categories,
)


class TDSReference(Document):
	def after_insert(self):
		create_tax_withholding_categories(self)
