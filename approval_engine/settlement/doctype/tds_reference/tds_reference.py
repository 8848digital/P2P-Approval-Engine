# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from frappe.model.document import Document

from approval_engine.settlement.doc_events.tds_reference import create_tax_withholding_categories


class TDSReference(Document):
	"""Master list of TDS rates per Nature of Service / IT Act section --
	source of truth for the Tax Withholding Category records auto-created
	on insert (see doc_events/tds_reference.py)."""

	def after_insert(self) -> None:
		"""Auto-create the matching Tax Withholding Category record(s)."""
		create_tax_withholding_categories(self)
