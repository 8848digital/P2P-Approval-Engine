import frappe
from .utils import create_vendor

@frappe.whitelist()
def send_vendor_mail(mail, reference_doctype, reference_docname = None, name = None, email_2 = None, company = None):
	return create_vendor(mail, reference_doctype, reference_docname, name, email_2=email_2, company=company)