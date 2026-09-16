# apps/p2p_customization/p2p_customization/settlement/doc_events/tds_reference.py
import re

import frappe
from frappe import _
from frappe.utils import flt

STANDARD_DUAL_RATE_REMARK = "1%- If vendor is Individual/ HUF, 2% - In other cases"

RATE_FROM_DATE = "2020-01-01"
RATE_TO_DATE = "9999-12-31"

# (company, TDS account) rows attached to every auto-created Tax Withholding
# Category, mirroring the pattern used by the existing categories in this system.
TDS_ACCOUNTS = [
	("Jio Finance Limited", "3815003 - Tax Deducted at Source - RRFL"),
	("Jio Financial Services Limited", "3815003 - Tax Deducted at Source - JFS"),
	("Jio Payment Solutions Limited", "3815003 - Tax Deducted at Source - RPSL"),
	("JIO Payments Bank Limited", "3815003 - Tax Deducted at Source - JPBL"),
	("Jio Leasing Services Limited", "3815003 - Tax Deducted at Source - JIASL"),
	("JIO Insurance Broking Limited", "3815003 - Tax Deducted at Source - RRIBL"),
]

RATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# Data fieldtype (category_name / the docname itself, since autoname is "Prompt")
# truncates at this length - keep composed names within it.
MAX_NAME_LENGTH = 140


def create_tax_withholding_categories(doc, method=None):
	"""doc_event: after_insert on TDS Reference.

	Creates the corresponding Tax Withholding Category record(s) - one per
	entity_type. A TDS Reference row with a single rate gets one category
	(entity_type = Others). A row with two rates (e.g. "1% /2%") only gets
	split into three categories (Individual / HUF / Others) when the remark
	is exactly the standard Individual-HUF-vs-others text - that's the only
	case where we know which rate applies to which entity type. Any other
	multi-rate remark is skipped for manual handling.
	"""
	rates = RATE_RE.findall(doc.tds_rate or "")
	if not rates:
		return

	base_name = _category_base_name(doc)

	if len(rates) == 1:
		_create_category(_build_name(base_name), doc, "Others", flt(rates[0]))
		return

	remark = (doc.remarks or "").strip()
	if remark != STANDARD_DUAL_RATE_REMARK:
		frappe.msgprint(
			_(
				"TDS Reference {0} has multiple rates ({1}) with a non-standard remark. "
				"Skipped automatic Tax Withholding Category creation - please create it manually."
			).format(doc.name, doc.tds_rate),
			alert=True,
			indicator="orange",
		)
		return

	individual_huf_rate = flt(rates[0])
	others_rate = flt(rates[1])
	_create_category(_build_name(base_name, " - Individual"), doc, "Individual", individual_huf_rate)
	_create_category(_build_name(base_name, " - HUF"), doc, "HUF", individual_huf_rate)
	_create_category(_build_name(base_name, " - Others"), doc, "Others", others_rate)


# Maps Supplier.supplier_type (Individual / Hindu Undivided Family / ...) to
# the Tax Withholding Category.entity_type bucket it should resolve to. Any
# supplier_type not listed here (Company, Firm, blank, etc.) falls back to
# the "Others" category for that nature of service.
SUPPLIER_TYPE_TO_ENTITY = {"Individual": "Individual", "Hindu Undivided Family": "HUF"}


@frappe.whitelist()
def get_tax_withholding_category(nature_of_service, supplier=None):
	"""Called from Purchase Order/Invoice Item's nature_of_service handler.

	Picks the Tax Withholding Category auto-created for this TDS Reference
	row that matches the supplier's legal type: Individual/HUF get their own
	category (when one was split out), everyone else gets "Others".
	"""
	if not nature_of_service:
		return None
	return _resolve_category(nature_of_service, _entity_bucket_for_supplier(supplier))


@frappe.whitelist()
def get_tax_withholding_categories(nature_of_services, supplier=None):
	"""Batched counterpart of get_tax_withholding_category - resolves every
	nature_of_service value against one supplier in a single call, so a
	Purchase Order/Invoice with many line items doesn't fire one round-trip
	(and one Supplier.supplier_type lookup) per row on a supplier change.

	Returns {nature_of_service: category_or_None}.
	"""
	if isinstance(nature_of_services, str):
		nature_of_services = frappe.parse_json(nature_of_services)

	bucket = _entity_bucket_for_supplier(supplier)
	return {
		nature_of_service: _resolve_category(nature_of_service, bucket)
		for nature_of_service in set(nature_of_services or [])
		if nature_of_service
	}


def _entity_bucket_for_supplier(supplier):
	"""Map a Supplier's supplier_type to its entity_type bucket (Individual/HUF/Others)."""
	supplier_type = frappe.db.get_value("Supplier", supplier, "supplier_type") if supplier else None
	return SUPPLIER_TYPE_TO_ENTITY.get(supplier_type, "Others")


def _resolve_category(nature_of_service, bucket):
	"""Look up the Tax Withholding Category for nature_of_service + bucket,
	falling back to "Others" if this TDS Reference was never split by entity type."""
	category = frappe.db.get_value(
		"Tax Withholding Category", {"tds_reference": nature_of_service, "entity_type": bucket}, "name"
	)
	if category:
		return category

	if bucket != "Others":
		# Single-rate TDS Reference rows only ever get an "Others" category.
		category = frappe.db.get_value(
			"Tax Withholding Category", {"tds_reference": nature_of_service, "entity_type": "Others"}, "name"
		)

	return category


def _category_base_name(doc):
	"""Builds "<section>-<nature_of_service>", or just nature_of_service if no section is set."""
	section = (doc.section_as_per_it_act_1961 or "").strip()
	return f"{section}-{doc.nature_of_service}" if section else doc.nature_of_service


def _build_name(base_name, suffix=""):
	"""base_name + suffix, trimmed to fit MAX_NAME_LENGTH (Data fieldtype limit) without losing the suffix."""
	name = f"{base_name}{suffix}"
	if len(name) <= MAX_NAME_LENGTH:
		return name
	trimmed_base = base_name[: MAX_NAME_LENGTH - len(suffix)].rstrip()
	return f"{trimmed_base}{suffix}"


def _create_category(name, tds_reference, entity_type, rate) -> None:
	"""Insert one Tax Withholding Category for tds_reference/entity_type/rate,
	skipping if it already exists or if none of TDS_ACCOUNTS' companies/accounts exist on this site."""
	if frappe.db.exists("Tax Withholding Category", name):
		return

	category = frappe.new_doc("Tax Withholding Category")
	category.name = name
	category.category_name = name
	category.tds_section = tds_reference.section_as_per_it_act_1961
	category.entity_type = entity_type
	category.tds_reference = tds_reference.name

	category.append(
		"rates",
		{
			"from_date": RATE_FROM_DATE,
			"to_date": RATE_TO_DATE,
			"tax_withholding_rate": rate,
			"cumulative_threshold": 0,
			"single_threshold": 0,
		},
	)

	for company, account in TDS_ACCOUNTS:
		if frappe.db.exists("Company", company) and frappe.db.exists("Account", account):
			category.append("accounts", {"company": company, "account": account})

	if not category.accounts:
		return

	category.insert(ignore_permissions=True)
