import frappe
from .utils import (
	make_purchase_invoice,
	send_po_mail_to_vendor,
)
from p2p_customization.settlement.utils import (
	validate_brn_dates,
	_get_fiscal_year_and_validity,
)
from .rate_comparison import get_rate_comparison_rows, get_rate_comparison_config

@frappe.whitelist()
def send_po_to_vendor(purchase_order):
	"""Send Purchase Order email with PDF attachment to vendor"""
	return send_po_mail_to_vendor(purchase_order)

@frappe.whitelist()
def make_purchase_invoice_from_portal(purchase_order_name, items=None, supplier_invoice_no = None, supplier_invoice_date = None):
	# create purchase invoice from portal
	return make_purchase_invoice(purchase_order_name, items, supplier_invoice_no, supplier_invoice_date)

@frappe.whitelist()
def validate_transaction_date_with_brn_dates(brn, transaction_date):
	return validate_brn_dates(brn, transaction_date)

@frappe.whitelist()
def get_fiscal_year_and_validity(date, brn = None):
	return _get_fiscal_year_and_validity(date, brn)

@frappe.whitelist()
def get_vendor_rate_comparison(supplier, nature_of_services, company, transaction_date, brn=None, exclude_po=None):
	return get_rate_comparison_rows(supplier, nature_of_services, company, transaction_date, brn, exclude_po)

@frappe.whitelist()
def get_vendor_rate_comparison_config():
	return get_rate_comparison_config()