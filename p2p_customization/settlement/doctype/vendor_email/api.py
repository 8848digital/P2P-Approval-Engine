import frappe

from .utils import create_vendor


@frappe.whitelist()
def send_vendor_mail(
	mail: str,
	reference_doctype: str,
	reference_docname: str | None = None,
	name: str | None = None,
	email_2: str | None = None,
	company: str | None = None,
) -> dict:
	"""
		Create (or reuse) a Vendor Email record for a supplier onboarding
		through the Vendor Portal and send the onboarding invite email.

		**Endpoint:** `/api/method/p2p_customization.settlement.doctype.vendor_email.api.send_vendor_mail`
		**HTTP Method:** POST
		**Parameters:**
			- mail (str, required): Vendor's primary email address.
			- reference_doctype (str, required): DocType this onboarding is linked to.
			- reference_docname (str, optional): Name of the linked reference document.
			- name (str, optional): Vendor's display name.
			- email_2 (str, optional): Secondary recipient for the same invite link.
			- company (str, optional): Company the vendor is onboarding against.
		**Response:**
	```json
			{
				"status": "success",
				"message": "Email sent to vendor@example.com"
			}
	```
	"""
	return create_vendor(mail, reference_doctype, reference_docname, name, email_2=email_2, company=company)
