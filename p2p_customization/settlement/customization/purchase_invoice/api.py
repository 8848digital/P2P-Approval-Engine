import frappe
from frappe.utils import get_url_to_form
from .utils import upload_file

@frappe.whitelist()
def send_po_to_vendor(purchase_invoice):
	"""Send Purchase Invoice email with PDF attachment to vendor"""
	doc = frappe.get_doc("Purchase Invoice", purchase_invoice)
	# frappe.get_doc() does not check permissions on its own -- without this,
	# any logged-in user could pass an arbitrary Purchase Invoice name and
	# have its PDF emailed to that supplier, regardless of whether they can
	# actually see/print this document.
	if not doc.has_permission("email"):
		frappe.throw(
			frappe._("You are not permitted to email this Purchase Invoice."),
			frappe.PermissionError,
		)

	# 1. Try to get email from Purchase Order contact person
	supplier_email = None
	if doc.supplier_address:
		supplier_email = frappe.db.get_value("Address", doc.supplier_address, "email_id")

	# 2. If not found, get from Supplier master
	if not supplier_email:
		supplier_email = frappe.db.get_value("Supplier", doc.supplier, "email_id")

	if not supplier_email:
		frappe.throw("Please set Vendor Email in Supplier or Address master")

	# Email content
	subject = f"Purchase Invoice {doc.name}"
	message = f"""
		<p>Dear {doc.supplier_name},</p>
		<p>Please find attached Purchase Invoice <b>{doc.name}</b> for your reference.</p>
		<p>Regards,<br>{frappe.session.user}</p>
	"""
 # <p>You can also view it online: <a href="{get_url_to_form('Purchase Invoice', doc.name)}">{doc.name}</a></p>
	# Send Email with PDF attachment
	frappe.sendmail(
		recipients=[supplier_email],
		sender=None,
		subject=subject,
		message=message,
		now=True,
		attachments=[
			frappe.attach_print(
				doctype="Purchase Invoice",
				name=doc.name,
				# print_format="Payment Voucher 1",   # or your custom format
				file_name=f"{doc.name}.pdf"
			)
		]
	)

	return True

# Only these doctype/fieldname combinations may be written by
# upload_file_to_pi_from_portal (see .utils.upload_file) -- the vendor
# portal (templates/pages/order.html) is the only caller, and it only ever
# attaches the supplier's own invoice copy to a Purchase Order or Purchase
# Invoice it's showing. Without this allowlist, the endpoint accepted ANY
# doctype/docname/fieldname/value from the request and wrote it straight
# via frappe.db.set_value with no permission check at all -- any logged-in
# user (including a Website User on the public vendor portal) could set any
# field on any document of any doctype to any value.
PORTAL_UPLOAD_ALLOWED_FIELDS = {
	"Purchase Order": {"custom_supplier_invoice_copy"},
	"Purchase Invoice": {"custom_supplier_invoice_copy"},
}


@frappe.whitelist()
def upload_file_to_pi_from_portal(**args):
	doctype = args.get("doctype")
	fieldname = args.get("fieldname")

	if doctype not in PORTAL_UPLOAD_ALLOWED_FIELDS or fieldname not in PORTAL_UPLOAD_ALLOWED_FIELDS.get(doctype, ()):
		frappe.throw(
			frappe._("This field cannot be updated from the vendor portal."),
			frappe.PermissionError,
		)

	docname = args.get("name")
	if not frappe.has_permission(doctype, ptype="write", doc=docname):
		frappe.throw(
			frappe._("You are not permitted to update this document."),
			frappe.PermissionError,
		)

	file_url = args.get("value")
	if file_url and not frappe.db.exists("File", {"file_url": file_url}):
		frappe.throw(frappe._("Invalid file reference."))

	return upload_file(**args)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_nature_of_service_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Restrict BRN's Nature of Service (Table MultiSelect -> TDS Reference)
	to only the values selected on the linked Supplier's
	Nature of Services multiselect.
	"""
	supplier = filters.get("supplier") if filters else None

	if not supplier:
		return []

	allowed_services = frappe.get_all(
		"Nature of Service Reference",
		filters={"parent": supplier, "parenttype": "Supplier"},
		pluck="nature_of_service"
	)

	if not allowed_services:
		return []

	return frappe.db.sql(
		"""
		select name, section_as_per_it_act_1961, tds_rate
		from `tabTDS Reference`
		where (
				name like %(txt)s
				or section_as_per_it_act_1961 like %(txt)s
				or tds_rate like %(txt)s
			)
			and name in %(allowed_services)s
		order by
			case when name = %(exact_txt)s then 0 else 1 end,
			name
		""",
		{
			"txt": "%{}%".format(txt or ""),
			"exact_txt": txt or "",
			"allowed_services": allowed_services,
		},
	)