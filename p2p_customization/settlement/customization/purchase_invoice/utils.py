import frappe
from frappe.utils import flt, get_link_to_form
from frappe import _

def upload_file(**args):
	doctype = args.get("doctype")
	docname = args.get("name")
	fieldname = args.get("fieldname")
	file_url = args.get("value")

	if not (doctype and docname and fieldname and file_url):
		frappe.throw("Missing required parameters")

	old_file = frappe.db.get_value(doctype, docname, fieldname)

	if old_file:
		files = frappe.get_all(
			"File",
			filters={
				"file_url": old_file,
				"attached_to_doctype": doctype,
				"attached_to_name": docname
			},
			fields=["name"]
		)

		for f in files:
			try:
				frappe.delete_doc("File", f.name, ignore_permissions=True)
			except Exception:
				pass

	frappe.db.set_value(doctype, docname, fieldname, file_url, update_modified=False)

	return "success"


def validate_item_qty_with_brn(self):
	if not self.items or not self.brn:
		return

	item_codes = list({d.item_code for d in self.items})

	# Get only requisition_type
	requisition_type = frappe.db.get_value(
		"BRN",
		self.brn,
		"requisition_type"
	)

	# Load only required BRN items
	brn_items = frappe.get_all(
		"BRN Item",
		filters={
			"parent": self.brn,
			"item_code": ["in", item_codes],
		},
		fields=["item_code", "qty", "rate", "amount"],
	)

	brn_item_map = {
		d.item_code: d
		for d in brn_items
	}

	# Get already invoiced qty/amount
	invoiced_data = frappe.db.sql(
		"""
		SELECT
			pii.item_code,
			SUM(pii.qty) AS invoiced_qty,
			SUM(pii.amount) AS invoiced_amount
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi
			ON pi.name = pii.parent
		WHERE
			pi.brn = %(brn)s
			AND pi.name != %(pi)s
			AND pi.docstatus < 2
			AND pii.item_code IN %(item_codes)s
		GROUP BY pii.item_code
		""",
		{
			"brn": self.brn,
			"pi": self.name,
			"item_codes": tuple(item_codes),
		},
		as_dict=True,
	)

	invoiced_map = {
		d.item_code: (
			flt(d.invoiced_qty),
			flt(d.invoiced_amount)
		)
		for d in invoiced_data
	}

	brn_link = get_link_to_form("BRN", self.brn)

	for row in self.items:
		brn_item = brn_item_map.get(row.item_code)

		if not brn_item:
			frappe.throw(
				_("Row {0}: Item {1} is not found in BRN {2}")
				.format(row.idx, row.item_code, brn_link)
			)

		brn_qty = flt(brn_item.qty)
		brn_rate = flt(brn_item.rate)
		brn_amount = flt(brn_item.amount)

		invoiced_qty, invoiced_amount = invoiced_map.get(
			row.item_code,
			(0, 0)
		)

		row_qty = flt(row.qty)
		row_rate = flt(row.rate)
		row_amount = flt(row.amount)

		if requisition_type != "Service":

			if row_qty + invoiced_qty > brn_qty:
				frappe.throw(
					_("Row {0}: Qty {1} exceeds BRN Quantity. Available Qty: {2} for Item {3} in {4}")
					.format(
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
					_("Row {0}: Rate {1} does not match BRN Rate {2} for Item {3} in {4}")
					.format(
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
				_("Row {0}: Amount {1} exceeds BRN Amount. Available Amount: {2} for Item {3} in {4}")
				.format(
					row.idx,
					row_amount,
					brn_amount - invoiced_amount,
					row.item_code,
					brn_link,
				),
				title=_("Amount Exceeded"),
			)


def validate_item_qty_with_po(self):
	if not self.items:
		return

	# Collect all PO Detail names from the invoice items
	po_details = [row.po_detail for row in self.items if row.po_detail]
	if not po_details:
		return

	po_details_tuple = tuple(po_details)

	# Fetch PO Item info + cumulative qty/amount already invoiced (exclude current PI if submitted)
	po_item_map = frappe.db.sql(f"""
		SELECT
			poi.name AS po_detail,
			poi.item_code,
			poi.qty AS po_qty,
			poi.rate AS po_rate,
			poi.amount AS po_amount,
			poi.parent AS po_name,
			po.brn,
			po.requisition_type,
			COALESCE(SUM(CASE WHEN pi.docstatus < 2 AND pi.name != %s THEN pii.qty ELSE 0 END), 0) AS already_invoiced_qty,
			COALESCE(SUM(CASE WHEN pi.docstatus < 2 AND pi.name != %s THEN pii.amount ELSE 0 END), 0) AS already_invoiced_amount
		FROM `tabPurchase Order Item` poi
		JOIN `tabPurchase Order` po ON po.name = poi.parent
		LEFT JOIN `tabPurchase Invoice Item` pii ON pii.po_detail = poi.name
		LEFT JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE poi.name IN ({', '.join(['%s']*len(po_details_tuple))})
		GROUP BY poi.name, poi.item_code, poi.qty, poi.rate, poi.amount, poi.parent, po.brn, po.requisition_type
	""", (self.name, self.name, *po_details_tuple), as_dict=True)

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
					_("Row {0}: Qty {1} exceeds Purchase Order Item Quantity. Available Qty: {2} for Item {3} in {4}")
					.format(row.idx, row.qty, available_qty, row.item_code, po_link),
					title=_("Qty Exceeded"),
				)

			# --- Validate Rate (only if requisition type != "Service") ---
			if abs(flt(row.rate) - flt(po_item.po_rate)) >= 0.01:
				frappe.throw(
					_("Row {0}: Rate {1} does not match Purchase Order Rate {2} for Item {3} in {4}")
					.format(row.idx, row.rate, po_item.po_rate, row.item_code, po_link),
					title=_("Rate Mismatch"),
				)

		# --- Validate Amount always ---
		available_amount = po_item.po_amount - po_item.already_invoiced_amount
		row_amount = row.amount or (row.qty * row.rate)
		if row_amount + po_item.already_invoiced_amount > po_item.po_amount:
			frappe.throw(
				_("Row {0}: Amount {1} exceeds Purchase Order Item Amount. Available Amount: {2} for Item {3} in {4}")
				.format(row.idx, row_amount, available_amount, row.item_code, po_link),
				title=_("Amount Exceeded"),
			)
