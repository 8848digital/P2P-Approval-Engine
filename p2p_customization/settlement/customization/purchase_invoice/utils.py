import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form
from pypika import Case
from pypika import functions as fn

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


def validate_item_qty_with_brn(self) -> None:
	"""
	Validate a standalone (non-PO) BRN-linked Purchase Invoice: item
	qty/rate (non-Service only) and amount must stay within the balance
	still available on the BRN, across every other non-cancelled PI
	against the same BRN.

	Parameters:
		self (Document, required): The Purchase Invoice document being validated.

	Returns:
		None
	"""
	if not self.items or not self.brn:
		return

	item_codes = list({d.item_code for d in self.items})

	# Get only requisition_type
	requisition_type = frappe.db.get_value("BRN", self.brn, "requisition_type")

	# Load only required BRN items
	brn_items = frappe.get_all(
		"BRN Item",
		filters={
			"parent": self.brn,
			"item_code": ["in", item_codes],
		},
		fields=["item_code", "qty", "rate", "amount"],
	)

	brn_item_map = {d.item_code: d for d in brn_items}

	# Get already invoiced qty/amount
	PII = frappe.qb.DocType("Purchase Invoice Item")
	PI = frappe.qb.DocType("Purchase Invoice")
	invoiced_data = (
		frappe.qb.from_(PII)
		.inner_join(PI)
		.on(PI.name == PII.parent)
		.select(
			PII.item_code,
			fn.Sum(PII.qty).as_("invoiced_qty"),
			fn.Sum(PII.amount).as_("invoiced_amount"),
		)
		.where(PI.brn == self.brn)
		.where(PI.name != self.name)
		.where(PI.docstatus < 2)
		.where(PII.item_code.isin(item_codes))
		.groupby(PII.item_code)
	).run(as_dict=True)

	invoiced_map = {d.item_code: (flt(d.invoiced_qty), flt(d.invoiced_amount)) for d in invoiced_data}

	brn_link = get_link_to_form("BRN", self.brn)

	for row in self.items:
		brn_item = brn_item_map.get(row.item_code)

		if not brn_item:
			frappe.throw(
				_("Row {0}: Item {1} is not found in BRN {2}").format(row.idx, row.item_code, brn_link)
			)

		brn_qty = flt(brn_item.qty)
		brn_rate = flt(brn_item.rate)
		brn_amount = flt(brn_item.amount)

		invoiced_qty, invoiced_amount = invoiced_map.get(row.item_code, (0, 0))

		row_qty = flt(row.qty)
		row_rate = flt(row.rate)
		row_amount = flt(row.amount)

		if requisition_type != "Service":
			if row_qty + invoiced_qty > brn_qty:
				frappe.throw(
					_("Row {0}: Qty {1} exceeds BRN Quantity. Available Qty: {2} for Item {3} in {4}").format(
						row.idx,
						row_qty,
						brn_qty - invoiced_qty,
						row.item_code,
						brn_link,
					),
					title=_("Qty Exceeded"),
				)

			if abs(row_rate - brn_rate) >= 0.01:
				frappe.throw(
					_("Row {0}: Rate {1} does not match BRN Rate {2} for Item {3} in {4}").format(
						row.idx,
						row_rate,
						brn_rate,
						row.item_code,
						brn_link,
					),
					title=_("Rate Mismatch"),
				)

		if row_amount + invoiced_amount > brn_amount:
			frappe.throw(
				_("Row {0}: Amount {1} exceeds BRN Amount. Available Amount: {2} for Item {3} in {4}").format(
					row.idx,
					row_amount,
					brn_amount - invoiced_amount,
					row.item_code,
					brn_link,
				),
				title=_("Amount Exceeded"),
			)


def validate_item_qty_with_po(self) -> None:
	"""
	Validate a PO-based Purchase Invoice: each row's qty/rate (non-Service
	only) and amount must stay within its Purchase Order Item's balance,
	across every other non-cancelled PI already invoiced against that PO
	line.

	Parameters:
		self (Document, required): The Purchase Invoice document being validated.

	Returns:
		None
	"""
	if not self.items:
		return

	# Collect all PO Detail names from the invoice items
	po_details = [row.po_detail for row in self.items if row.po_detail]
	if not po_details:
		return

	# Fetch PO Item info + cumulative qty/amount already invoiced (exclude current PI if submitted)
	POI = frappe.qb.DocType("Purchase Order Item")
	PO = frappe.qb.DocType("Purchase Order")
	PII = frappe.qb.DocType("Purchase Invoice Item")
	PI = frappe.qb.DocType("Purchase Invoice")

	still_counted = (PI.docstatus < 2) & (PI.name != self.name)
	invoiced_qty_case = Case().when(still_counted, PII.qty).else_(0)
	invoiced_amount_case = Case().when(still_counted, PII.amount).else_(0)

	po_item_map = (
		frappe.qb.from_(POI)
		.join(PO)
		.on(PO.name == POI.parent)
		.left_join(PII)
		.on(PII.po_detail == POI.name)
		.left_join(PI)
		.on(PI.name == PII.parent)
		.select(
			POI.name.as_("po_detail"),
			POI.item_code,
			POI.qty.as_("po_qty"),
			POI.rate.as_("po_rate"),
			POI.amount.as_("po_amount"),
			POI.parent.as_("po_name"),
			PO.brn,
			PO.requisition_type,
			fn.Coalesce(fn.Sum(invoiced_qty_case), 0).as_("already_invoiced_qty"),
			fn.Coalesce(fn.Sum(invoiced_amount_case), 0).as_("already_invoiced_amount"),
		)
		.where(POI.name.isin(po_details))
		.groupby(
			POI.name, POI.item_code, POI.qty, POI.rate, POI.amount, POI.parent, PO.brn, PO.requisition_type
		)
	).run(as_dict=True)

	po_map = {d.po_detail: d for d in po_item_map}

	for row in self.items:
		if not row.po_detail:
			continue

		po_item = po_map.get(row.po_detail)
		if not po_item:
			continue

		po_link = get_link_to_form("Purchase Order", po_item.po_name)

		# --- Validate Qty (only if requisition type != "Service") ---
		if po_item.requisition_type != "Service":
			available_qty = po_item.po_qty - po_item.already_invoiced_qty
			if row.qty + po_item.already_invoiced_qty > po_item.po_qty:
				frappe.throw(
					_(
						"Row {0}: Qty {1} exceeds Purchase Order Item Quantity. Available Qty: {2} for Item {3} in {4}"
					).format(row.idx, row.qty, available_qty, row.item_code, po_link),
					title=_("Qty Exceeded"),
				)

			# --- Validate Rate (only if requisition type != "Service") ---
			if abs(flt(row.rate) - flt(po_item.po_rate)) >= 0.01:
				frappe.throw(
					_("Row {0}: Rate {1} does not match Purchase Order Rate {2} for Item {3} in {4}").format(
						row.idx, row.rate, po_item.po_rate, row.item_code, po_link
					),
					title=_("Rate Mismatch"),
				)

		# --- Validate Amount always ---
		available_amount = po_item.po_amount - po_item.already_invoiced_amount
		row_amount = row.amount or (row.qty * row.rate)
		if row_amount + po_item.already_invoiced_amount > po_item.po_amount:
			frappe.throw(
				_(
					"Row {0}: Amount {1} exceeds Purchase Order Item Amount. Available Amount: {2} for Item {3} in {4}"
				).format(row.idx, row_amount, available_amount, row.item_code, po_link),
				title=_("Amount Exceeded"),
			)
