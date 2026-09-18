import frappe
from frappe import _

# Only these doctype/fieldname combinations may be written by
# upload_invoice_file_from_portal (below) -- the vendor portal
# (templates/pages/order.html) is the only caller, and it only ever
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


def send_purchase_invoice_to_vendor(purchase_invoice: str) -> bool:
	"""
	Email a Purchase Invoice's PDF to its supplier.

	Parameters:
		purchase_invoice (str, required): The Purchase Invoice document name.

	Returns:
		bool: True on success (raises on permission/validation failure).
	"""
	doc = frappe.get_doc("Purchase Invoice", purchase_invoice)
	# frappe.get_doc() does not check permissions on its own -- without this,
	# any logged-in user could pass an arbitrary Purchase Invoice name and
	# have its PDF emailed to that supplier, regardless of whether they can
	# actually see/print this document.
	if not doc.has_permission("email"):
		frappe.throw(
			_("You are not permitted to email this Purchase Invoice."),
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
		frappe.throw(_("Please set Vendor Email in Supplier or Address master"))

	# Email content
	subject = f"Purchase Invoice {doc.name}"
	message = f"""
		<p>Dear {doc.supplier_name},</p>
		<p>Please find attached Purchase Invoice <b>{doc.name}</b> for your reference.</p>
		<p>Regards,<br>{frappe.session.user}</p>
	"""
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
				file_name=f"{doc.name}.pdf",
			)
		],
	)

	return True


def upload_invoice_file_from_portal(**args) -> str:
	"""
	Validate and persist a vendor-uploaded invoice-copy file reference onto
	a Purchase Order/Purchase Invoice, from the vendor portal.

	Parameters:
		**args: doctype (str, required), name (str, required, the docname),
			fieldname (str, required), value (str, required, the File's file_url).

	Returns:
		str: "success" once the field has been updated.
	"""
	doctype = args.get("doctype")
	fieldname = args.get("fieldname")

	if doctype not in PORTAL_UPLOAD_ALLOWED_FIELDS or fieldname not in PORTAL_UPLOAD_ALLOWED_FIELDS.get(
		doctype, ()
	):
		frappe.throw(
			_("This field cannot be updated from the vendor portal."),
			frappe.PermissionError,
		)

	docname = args.get("name")
	if not frappe.has_permission(doctype, ptype="write", doc=docname):
		frappe.throw(
			_("You are not permitted to update this document."),
			frappe.PermissionError,
		)

	file_url = args.get("value")
	if file_url and not frappe.db.exists("File", {"file_url": file_url}):
		frappe.throw(_("Invalid file reference."))

	return upload_file(**args)


def upload_file(**args) -> str:
	"""
	Replace whatever file currently sits in a document's attach field with a
	newly-uploaded one, deleting the old File record(s) first.

	Parameters:
		**args: doctype (str, required), name (str, required, the docname),
			fieldname (str, required, the attach field to update),
			value (str, required, the new file's URL).

	Returns:
		str: "success" once the field is updated.
	"""
	doctype = args.get("doctype")
	docname = args.get("name")
	fieldname = args.get("fieldname")
	file_url = args.get("value")

	if not (doctype and docname and fieldname and file_url):
		frappe.throw(_("Missing required parameters"))

	old_file = frappe.db.get_value(doctype, docname, fieldname)

	if old_file:
		files = frappe.get_all(
			"File",
			filters={"file_url": old_file, "attached_to_doctype": doctype, "attached_to_name": docname},
			fields=["name"],
		)

		for f in files:
			try:
				frappe.delete_doc("File", f.name, ignore_permissions=True)
			except Exception:
				pass

	frappe.db.set_value(doctype, docname, fieldname, file_url, update_modified=False)

	return "success"
