import json
import frappe
from frappe import _
from frappe.utils.user import is_website_user
from frappe.model.document import Document
from erpnext.controllers.website_list_for_contact import get_parents_for_user
from .doc_events import set_total_amount, validate_comparision_rows, block_requisition_id
from .api import get_expiry_date
class BRN(Document):
	def validate(self):
		self.expiry_date = get_expiry_date(self.service_start_date, self.duration_of_service_months)
		set_total_amount(self)
		validate_comparision_rows(self)

	def on_submit(self):
		block_requisition_id(self)

def get_list_context(context=None):
	return {
		"global_number_format": frappe.db.get_default("number_format") or "#,###.##",
		"currency": frappe.db.get_default("currency"),
		"currency_symbols": json.dumps(
			dict(
				frappe.db.sql("""
					SELECT name, symbol
					FROM `tabCurrency`
					WHERE enabled = 1
				""")
			)
		),
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
	user = frappe.session.user

	if not filters:
		filters = {}

	# supplier/existing_vendor no longer live on BRN itself -- they're
	# columns on the BRN Comparision child table now, so the portal
	# restriction below joins against it instead of filtering tabBRN
	# directly.
	conditions = ["brn.docstatus = 1"]
	join = ""
	values = {
		"limit_start": limit_start,
		"limit_page_length": limit_page_length,
	}

	# Portal Supplier Restriction
	if user != "Guest" and is_website_user():
		suppliers = get_parents_for_user("Supplier")

		if not suppliers:
			return []

		conditions.append("brn.po_type = %(po_type)s")
		values["po_type"] = "YEXP Proposal"

		join = "INNER JOIN `tabBRN Comparision` bc ON bc.parent = brn.name AND bc.parenttype = 'BRN'"
		conditions.append("bc.existing_vendor IN %(suppliers)s")
		values["suppliers"] = tuple(suppliers)

	if txt:
		conditions.append("brn.name LIKE %(txt)s")
		values["txt"] = f"%{txt}%"

	query = f"""
		SELECT DISTINCT brn.name
		FROM `tabBRN` brn
		{join}
		WHERE {" AND ".join(conditions)}
		ORDER BY brn.creation DESC
		LIMIT %(limit_page_length)s OFFSET %(limit_start)s
	"""

	brns = frappe.db.sql(query, values, as_dict=True)

	result = []

	for brn in brns:
		doc = frappe.get_doc("BRN", brn.name)

		doc.items_preview = ", ".join(
			item.item_name for item in doc.items if item.item_name
		)

		result.append(doc)

	return result