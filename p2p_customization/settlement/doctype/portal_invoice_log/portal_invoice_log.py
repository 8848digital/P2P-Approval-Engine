import frappe
from frappe.model.document import Document
from .utils import send_portal_invoice_notification

class PortalInvoiceLog(Document):
	def after_insert(self):
		frappe.enqueue(
			method=send_portal_invoice_notification,
			queue="short",
			timeout=300,
			log_name=self.name,
		)