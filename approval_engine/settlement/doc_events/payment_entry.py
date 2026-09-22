# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Payment Entry hook: block payment against a BRN-linked Purchase Invoice
whose vendor was marked "Has MSA" on the BRN Comparision but never had the
MSA document attached. Purchase Orders/Invoices themselves are unaffected --
this only stops the actual payment.
"""

import frappe
from frappe import _


def block_payment_without_msa_attachment(doc, method=None) -> None:
	"""
	Payment Entry before_submit hook: for every referenced Purchase
	Invoice that's linked to a BRN, find that vendor's row in the BRN's
	Comparision table and refuse to submit if it has "Vendor Has MSA?"
	checked but no MSA Agreement Attachment.

	Parameters:
		doc (Document, required): The Payment Entry document being submitted.
		method (str, optional): The hook event name passed by Frappe.

	Returns:
		None
	"""
	for row in doc.references:
		if row.reference_doctype != "Purchase Invoice":
			continue

		pi = frappe.db.get_value(
			"Purchase Invoice", row.reference_name, ["brn", "supplier", "supplier_name"], as_dict=True
		)
		if not pi or not pi.brn:
			continue

		_check_brn_msa_attachment(pi.brn, pi.supplier, pi.supplier_name, row.reference_name)


def _check_brn_msa_attachment(brn: str, supplier: str, supplier_name: str, invoice: str) -> None:
	"""
	Raise if the BRN Comparision row for this vendor has MSA checked but
	no attachment. Matches by Supplier link for an existing vendor, or by
	vendor name for a new vendor (no Supplier link exists on the
	comparison row until after onboarding) -- same matching this app
	already uses elsewhere to tie a BRN Comparision row back to a vendor.

	Parameters:
		brn (str, required): The BRN this Purchase Invoice is linked to.
		supplier (str, required): The Purchase Invoice's Supplier.
		supplier_name (str, required): The Purchase Invoice's Supplier Name.
		invoice (str, required): The Purchase Invoice name, for the error message.

	Returns:
		None
	"""
	rows = frappe.get_all(
		"BRN Comparision",
		filters={"parent": brn, "msa_agreement": 1},
		or_filters={"existing_vendor": supplier, "vendor_name": supplier_name},
		fields=["msa_agreement_attachment"],
	)

	if any(not row.msa_agreement_attachment for row in rows):
		brn_link = frappe.utils.get_link_to_form("BRN", brn)
		invoice_link = frappe.utils.get_link_to_form("Purchase Invoice", invoice)
		frappe.throw(
			_(
				"Payment blocked: {0} (against {1}) is marked as having an MSA in {2}, "
				"but the MSA Agreement Attachment has not been updated."
			).format(invoice_link, supplier_name or supplier, brn_link),
			title=_("MSA Attachment Required"),
		)
