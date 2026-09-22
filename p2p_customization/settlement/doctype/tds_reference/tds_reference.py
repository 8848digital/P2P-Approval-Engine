# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from p2p_customization.settlement.doc_events.tds_reference import (
	create_tax_withholding_categories,
)


class TDSReference(Document):
	"""Master list of TDS rates per Nature of Service / IT Act section --
	source of truth for the Tax Withholding Category records auto-created
	on insert (see doc_events/tds_reference.py)."""

	def after_insert(self) -> None:
		"""Auto-create the matching Tax Withholding Category record(s)."""
		create_tax_withholding_categories(self)
