import frappe

from .utils import _send_supplier_status_mail, approval_mail

@frappe.whitelist()
def send_supplier_message(supplier, reason, action):
	return _send_supplier_status_mail(supplier, reason, action)

@frappe.whitelist()
def send_approval_mail(supplier_name, email_id):
	return approval_mail(supplier_name, email_id)

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_nature_of_service_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Returns all matching TDS Reference records (no pagination) so the
	Nature of Service Table MultiSelect on Supplier is not capped at
	the default page length of 20.
	"""
	return frappe.db.sql(
		"""
		select name, section_as_per_it_act_1961, tds_rate
		from `tabTDS Reference`
		where name like %(txt)s
			or section_as_per_it_act_1961 like %(txt)s
			or tds_rate like %(txt)s
		order by
			case when name = %(exact_txt)s then 0 else 1 end,
			name
		""",
		{
			"txt": "%{}%".format(txt or ""),
			"exact_txt": txt or "",
		},
	)