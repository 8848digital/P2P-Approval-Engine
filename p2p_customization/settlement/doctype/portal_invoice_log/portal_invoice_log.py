# Copyright (c) 2026, Satya and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from .utils import send_portal_invoice_notification


class PortalInvoiceLog(Document):
	"""
	Records a Purchase Invoice created by a supplier through the Vendor
	Portal, so the company and supplier can be notified asynchronously.
	"""

	def after_insert(self) -> None:
		"""
		Queue a background job to email the company and supplier once a
		Portal Invoice Log entry is created.

		Parameters:
			None (operates on self).

		Returns:
			None
		"""
		frappe.enqueue(
			method=send_portal_invoice_notification,
			queue="short",
			timeout=300,
			log_name=self.name,
		)
