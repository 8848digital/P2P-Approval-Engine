import frappe
from frappe import _

from p2p_customization.settlement.utils import (
	validate_fiscal_year_and_brn_dates,
	validate_item_rate_and_qty_with_brn,
)
from p2p_customization.settlement.tax_withholding import apply_tax_withholding


def validate(doc, method=None):
	validate_fiscal_year_and_brn_dates(doc, method)
	validate_item_rate_and_qty_with_brn(doc, method)
	apply_tax_withholding(doc, method)
