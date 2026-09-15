import frappe

def send_portal_invoice_notification(log_name):
	"""Send notifications to Company and Supplier"""

	if not is_email_configured():
		create_error_log(
			f"No default outgoing email account configured. "
			f"Skipping notifications for Portal Invoice Log {log_name}"
		)
		return

	try:
		log = frappe.get_doc("Portal Invoice Log", log_name)
		pi = frappe.get_doc("Purchase Invoice", log.purchase_invoice)

		po_text = get_po_text(pi)

		send_company_notification(pi, po_text)
		send_supplier_acknowledgement(pi, po_text)

	except Exception:
		frappe.log_error(
			title="Portal Invoice Notification Failed",
			message=frappe.get_traceback()
		)


def is_email_configured():
	"""Check if a default outgoing email account exists"""

	return frappe.db.exists(
		"Email Account",
		{
			"default_outgoing": 1,
			"enable_outgoing": 1
		}
	)


def get_po_text(pi):
	"""Return comma separated Purchase Orders"""

	po_names = sorted(
		{
			row.purchase_order
			for row in pi.items
			if row.purchase_order
		}
	)

	return ", ".join(po_names) if po_names else "N/A"


def send_company_notification(pi, po_text):
	"""Notify company that supplier created a Purchase Invoice"""

	company_email = frappe.db.get_value(
		"Company",
		pi.company,
		"email"
	)

	if not company_email:
		create_error_log(
			f"Email not found for Company {pi.company}"
		)
		return

	subject = f"Vendor Purchase Invoice Created - {pi.name}"

	message = f"""
	<p>Hello,</p>

	<p>
		A supplier has Created a Purchase Invoice through the Vendor Portal.
	</p>

	<table border="1" cellpadding="5" cellspacing="0">
		<tr>
			<td><b>Supplier</b></td>
			<td>{pi.supplier}</td>
		</tr>
		<tr>
			<td><b>Purchase Invoice</b></td>
			<td>{pi.name}</td>
		</tr>
		<tr>
			<td><b>Purchase Order</b></td>
			<td>{po_text}</td>
		</tr>
		<tr>
			<td><b>Supplier Invoice No</b></td>
			<td>{pi.bill_no or ""}</td>
		</tr>
		<tr>
			<td><b>Supplier Invoice Date</b></td>
			<td>{pi.bill_date or ""}</td>
		</tr>
		<tr>
			<td><b>Amount</b></td>
			<td>{pi.grand_total}</td>
		</tr>
	</table>
	"""

	send_email(
		recipients=[company_email],
		subject=subject,
		message=message,
	)


def send_supplier_acknowledgement(pi, po_text):
	"""Send acknowledgement to supplier"""

	supplier_email = frappe.db.get_value(
		"Supplier",
		pi.supplier,
		"email_id"
	)

	if not supplier_email:
		create_error_log(
			f"Email not found for Supplier {pi.supplier}"
		)
		return

	subject = f"Purchase Invoice Created Successfully - {pi.name}"

	message = f"""
	<p>Hello,</p>

	<p>
		Your Purchase Invoice has been created successfully through the Vendor Portal.
	</p>

	<table border="1" cellpadding="5" cellspacing="0">
		<tr>
			<td><b>Purchase Invoice</b></td>
			<td>{pi.name}</td>
		</tr>
		<tr>
			<td><b>Purchase Order</b></td>
			<td>{po_text}</td>
		</tr>
		<tr>
			<td><b>Supplier Invoice No</b></td>
			<td>{pi.bill_no or ""}</td>
		</tr>
		<tr>
			<td><b>Supplier Invoice Date</b></td>
			<td>{pi.bill_date or ""}</td>
		</tr>
		<tr>
			<td><b>Amount</b></td>
			<td>{pi.grand_total}</td>
		</tr>
	</table>

	<p>
		Thank you.
	</p>
	"""

	send_email(
		recipients=[supplier_email],
		subject=subject,
		message=message,
	)


def send_email(recipients, subject, message):
	"""Common email sender"""

	if not recipients:
		return

	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		delayed=False
	)


def create_error_log(message):
	"""Create error log entry"""

	frappe.log_error(
		title="Portal Invoice Notification",
		message=message
	)