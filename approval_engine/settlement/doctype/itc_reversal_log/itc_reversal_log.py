# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe.model.document import Document


class ITCReversalLog(Document):
	"""Tracks one Purchase Invoice's ITC (Input Tax Credit) reversal
	decision and outcome -- see doc_events/purchase_invoice_itc_reversal.py
	for the classification/reversal logic that maintains it."""

	def validate(self) -> None:
		"""Keep Purchase Invoice.is_itc_reversed in sync with this log's
		own reversal_status."""
		if self.purchase_invoice:
			is_reversed = 1 if self.reversal_status == "Reversed" else 0
			frappe.db.set_value(
				"Purchase Invoice",
				self.purchase_invoice,
				"is_itc_reversed",
				is_reversed,
				update_modified=False,
			)
