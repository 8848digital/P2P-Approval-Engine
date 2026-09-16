import frappe

from .utils import _send_supplier_status_mail, approval_mail


@frappe.whitelist()
def send_supplier_message(supplier, reason, action):
	"""Send a status-change notification email to a Supplier."""
	return _send_supplier_status_mail(supplier, reason, action)


@frappe.whitelist()
def send_approval_mail(supplier_name, email_id):
	"""Send the Supplier approval email."""
	return approval_mail(supplier_name, email_id)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_nature_of_service_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Returns all matching TDS Reference records (no pagination) so the
	Nature of Service Table MultiSelect on Supplier is not capped at
	the default page length of 20.
	"""
	TDS = frappe.qb.DocType("TDS Reference")
	txt_like = f"%{txt or ''}%"
	exact_txt = txt or ""

	return (
		frappe.qb.from_(TDS)
		.select(TDS.name, TDS.section_as_per_it_act_1961, TDS.tds_rate)
		.where(
			(TDS.name.like(txt_like))
			| (TDS.section_as_per_it_act_1961.like(txt_like))
			| (TDS.tds_rate.like(txt_like))
		)
		.orderby(TDS.name != exact_txt)
		.orderby(TDS.name)
	).run()
