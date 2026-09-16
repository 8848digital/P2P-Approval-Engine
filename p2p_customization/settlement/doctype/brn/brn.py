import json

import frappe
from erpnext.controllers.website_list_for_contact import get_parents_for_user
from frappe import _
from frappe.model.document import Document
from frappe.utils.user import is_website_user

from .api import get_expiry_date
from .doc_events import block_requisition_id, set_total_amount, validate_comparision_rows


class BRN(Document):
	"""Business Requisition Note -- a procurement proposal comparing vendors,
	mapped into a Purchase Order/Invoice once approved."""

	def validate(self):
		"""Recompute the expiry date and total amount, and enforce the
		Comparision table's Single/Multi/Preferred row constraints."""
		self.expiry_date = get_expiry_date(self.service_start_date, self.duration_of_service_months)
		set_total_amount(self)
		validate_comparision_rows(self)

	def on_submit(self):
		"""Mark the source Requisition ID (if any) as consumed by this BRN."""
		block_requisition_id(self)


def get_list_context(context=None):
	"""
	Website list-view config for the "Approved Proposals" portal page
	(the /brn route -- see hooks.py's standard_portal_menu_items).

	Parameters:
		context (dict, optional): Unused; matches Frappe's get_list_context
			hook signature.

	Returns:
		dict: Template/list config consumed by Frappe's website list view.
	"""
	currencies = frappe.get_all("Currency", filters={"enabled": 1}, fields=["name", "symbol"])

	return {
		"global_number_format": frappe.db.get_default("number_format") or "#,###.##",
		"currency": frappe.db.get_default("currency"),
		"currency_symbols": json.dumps({c.name: c.symbol for c in currencies}),
		"title": _("Approved Proposals"),
		"show_sidebar": True,
		"show_search": True,
		"no_breadcrumbs": True,
		"list_template": "templates/includes/brn_list_view.html",
		"row_template": "templates/includes/brn_row.html",
		"get_list": get_brn_list,
	}


def get_brn_list(
	doctype,
	txt=None,
	filters=None,
	limit_start=0,
	limit_page_length=20,
	order_by="creation desc",
	**kwargs,
):
	"""
	Fetch submitted BRNs for the portal list view, restricted to the
	logged-in Supplier's own proposals when a portal user is browsing.

	Parameters:
		doctype (str, required): Unused; matches Frappe's get_list signature.
		txt (str, optional): Search text, matched against BRN name.
		filters (dict, optional): Unused beyond presence (kept for signature
			compatibility with Frappe's website list view).
		limit_start (int, optional): Pagination offset.
		limit_page_length (int, optional): Page size.
		order_by (str, optional): Unused; results are always creation desc.
		**kwargs: Ignored, absorbs any other args Frappe's list view passes.

	Returns:
		list[Document]: Submitted BRN documents, each with an added
			`items_preview` attribute (comma-joined item names).
	"""
	user = frappe.session.user

	BRNTable = frappe.qb.DocType("BRN")
	query = frappe.qb.from_(BRNTable).select(BRNTable.name).distinct().where(BRNTable.docstatus == 1)

	# supplier/existing_vendor no longer live on BRN itself -- they're
	# columns on the BRN Comparision child table now, so the portal
	# restriction below joins against it instead of filtering tabBRN
	# directly.
	if user != "Guest" and is_website_user():
		suppliers = get_parents_for_user("Supplier")

		if not suppliers:
			return []

		Comparision = frappe.qb.DocType("BRN Comparision")
		query = (
			query.inner_join(Comparision)
			.on((Comparision.parent == BRNTable.name) & (Comparision.parenttype == "BRN"))
			.where(BRNTable.po_type == "YEXP Proposal")
			.where(Comparision.existing_vendor.isin(suppliers))
		)

	if txt:
		query = query.where(BRNTable.name.like(f"%{txt}%"))

	query = (
		query.orderby(BRNTable.creation, order=frappe.qb.desc).limit(limit_page_length).offset(limit_start)
	)

	brns = query.run(as_dict=True)

	result = []

	for brn in brns:
		doc = frappe.get_doc("BRN", brn.name)

		doc.items_preview = ", ".join(item.item_name for item in doc.items if item.item_name)

		result.append(doc)

	return result
