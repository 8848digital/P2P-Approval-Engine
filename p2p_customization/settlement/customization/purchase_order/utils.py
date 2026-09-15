import json

import frappe
from frappe import _
from frappe.utils import get_url_to_form
from erpnext.buying.doctype.purchase_order.purchase_order import get_mapped_purchase_invoice

def make_purchase_invoice(purchase_order_name, items, supplier_invoice_no, supplier_invoice_date):
	"""
	Create Purchase Invoice from Purchase Order (Portal)
	items: list of dicts [{item_code, qty, rate}]
	"""

	doc = get_mapped_purchase_invoice(purchase_order_name, ignore_permissions=True)

	if doc.contact_email != frappe.session.user:
		frappe.throw(_("Not Permitted"), frappe.PermissionError)

	if items:
		# Update item qty and rate
		items = json.loads(items) if isinstance(items, str) else items
		for inv_item in doc.items:
			for i in items:
				if inv_item.item_code == i['item_code']:
					inv_item.qty = i['qty']
					inv_item.rate = i['rate']
	if supplier_invoice_no:
		doc.bill_no = supplier_invoice_no
	if supplier_invoice_date:
		doc.bill_date = supplier_invoice_date

	doc.save()

	create_portal_invoice_log(doc)

	frappe.db.commit()

	return doc.name

def create_portal_invoice_log(purchase_invoice):
	"""Create Portal Invoice Log entry"""

	if frappe.db.exists(
		"Portal Invoice Log",
		{"purchase_invoice": purchase_invoice.name}
	):
		return

	frappe.get_doc({
		"doctype": "Portal Invoice Log",
		"purchase_invoice": purchase_invoice.name,
		"supplier": purchase_invoice.supplier
	}).insert(ignore_permissions=True)

@frappe.whitelist()
def send_po_mail_to_vendor(purchase_order):
	"""Send Purchase Order email with PDF attachment to vendor"""
	doc = frappe.get_doc("Purchase Order", purchase_order)

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
	subject = f"Purchase Order {doc.name}"
	message = f"""
		<p>Dear {doc.supplier_name},</p>
		<p>Please find attached Purchase Order <b>{doc.name}</b> for your reference.</p>
		<p>You can also view it online: <a href="{get_url_to_form('Purchase Order', doc.name)}">{doc.name}</a></p>
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
				doctype="Purchase Order",
				name=doc.name,
				# print_format="PO-3",   # or your custom format
				file_name=f"{doc.name}.pdf"
			)
		]
	)

	return True


