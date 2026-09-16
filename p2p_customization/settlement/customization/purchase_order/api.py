import frappe

from p2p_customization.settlement.customization.procure_to_pay.utils import (
	get_fiscal_year_and_validity as _get_fiscal_year_and_validity,
)
from p2p_customization.settlement.customization.procure_to_pay.utils import (
	validate_brn_dates,
)

from .rate_comparison import get_rate_comparison_config, get_rate_comparison_rows
from .utils import make_purchase_invoice, send_po_mail_to_vendor


@frappe.whitelist()
def send_po_to_vendor(purchase_order):
	"""Send Purchase Order email with PDF attachment to vendor"""
	return send_po_mail_to_vendor(purchase_order)


@frappe.whitelist()
def make_purchase_invoice_from_portal(
	purchase_order_name, items=None, supplier_invoice_no=None, supplier_invoice_date=None
):
	"""Create a Purchase Invoice mapped from a Purchase Order, from the vendor portal."""
	return make_purchase_invoice(purchase_order_name, items, supplier_invoice_no, supplier_invoice_date)


@frappe.whitelist()
def validate_transaction_date_with_brn_dates(brn, transaction_date):
	"""Check a transaction date against a BRN's service start/expiry dates."""
	return validate_brn_dates(brn, transaction_date)


@frappe.whitelist()
def get_fiscal_year_and_validity(date, brn=None):
	"""Resolve the fiscal year for date, clamping a BRN's validity period to it if given."""
	return _get_fiscal_year_and_validity(date, brn)


@frappe.whitelist()
def get_vendor_rate_comparison(
	supplier, nature_of_services, company, transaction_date, brn=None, exclude_po=None
):
	"""Return this-period vs. previous-period vendor rate comparison rows for the dialog."""
	return get_rate_comparison_rows(supplier, nature_of_services, company, transaction_date, brn, exclude_po)


@frappe.whitelist()
def get_vendor_rate_comparison_config():
	"""Return whether rate comparison is permitted/enabled and its trigger mode."""
	return get_rate_comparison_config()
