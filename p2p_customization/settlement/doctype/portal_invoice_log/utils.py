import frappe
from frappe.model.document import Document


def send_portal_invoice_notification(log_name: str) -> None:
	"""
	Load the Portal Invoice Log and its linked Purchase Invoice, then
	notify the company and supplier by email. Exits quietly (with an
	error log entry) when no default outgoing Email Account is configured.

	Parameters:
		log_name (str, required): Name of the Portal Invoice Log document.

	Returns:
		None
	"""

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
		frappe.log_error(title="Portal Invoice Notification Failed", message=frappe.get_traceback())


def is_email_configured() -> str | None:
	"""
	Check whether a default outgoing Email Account exists for this site.

	Parameters:
		None

	Returns:
		str | None: The matching Email Account's name if one is
		configured with outgoing enabled, else None.
	"""

	return frappe.db.exists("Email Account", {"default_outgoing": 1, "enable_outgoing": 1})


def get_po_text(pi: Document) -> str:
	"""
	Build a comma-separated, de-duplicated, sorted list of Purchase Orders
	referenced by a Purchase Invoice's item rows.

	Parameters:
		pi (Document, required): Purchase Invoice document (or any object
			exposing an `items` iterable of rows with `purchase_order`).

	Returns:
		str: Comma separated Purchase Order names, or "N/A" if none.
	"""

	po_names = sorted({row.purchase_order for row in pi.items if row.purchase_order})

	return ", ".join(po_names) if po_names else "N/A"


def send_company_notification(pi: Document, po_text: str) -> None:
	"""
	Notify the Purchase Invoice's Company that a supplier created it
	through the Vendor Portal. Skipped (with an error log entry) when the
	Company has no email address on file.

	Parameters:
		pi (Document, required): The Purchase Invoice document.
		po_text (str, required): Comma separated Purchase Order names.

	Returns:
		None
	"""

	company_email = frappe.db.get_value("Company", pi.company, "email")

	if not company_email:
		create_error_log(f"Email not found for Company {pi.company}")
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


def send_supplier_acknowledgement(pi: Document, po_text: str) -> None:
	"""
	Send an acknowledgement email to the Purchase Invoice's Supplier.
	Skipped (with an error log entry) when the Supplier has no email
	address on file.

	Parameters:
		pi (Document, required): The Purchase Invoice document.
		po_text (str, required): Comma separated Purchase Order names.

	Returns:
		None
	"""

	supplier_email = frappe.db.get_value("Supplier", pi.supplier, "email_id")

	if not supplier_email:
		create_error_log(f"Email not found for Supplier {pi.supplier}")
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


def send_email(recipients: list[str], subject: str, message: str) -> None:
	"""
	Common email sender used by both the company and supplier
	notifications. No-op when `recipients` is empty.

	Parameters:
		recipients (list[str], required): Email addresses to send to.
		subject (str, required): Email subject line.
		message (str, required): HTML email body.

	Returns:
		None
	"""

	if not recipients:
		return

	frappe.sendmail(recipients=recipients, subject=subject, message=message, delayed=False)


def create_error_log(message: str) -> None:
	"""
	Create an Error Log entry for a Portal Invoice notification issue.

	Parameters:
		message (str, required): Error detail to log.

	Returns:
		None
	"""

	frappe.log_error(title="Portal Invoice Notification", message=message)
