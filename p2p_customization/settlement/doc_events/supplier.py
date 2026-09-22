# apps/p2p_customization/p2p_customization/settlement/doc_events/supplier.py
import frappe
from frappe import _
from frappe.utils import now_datetime


def _get_faq_master_rows():
	"""Active FAQ Master rows as a dict keyed by question_code."""
	rows = frappe.get_all(
		"FAQ Master",
		filters={"is_active": 1},
		fields=["question_code", "expected_answer", "question_label"],
		order_by="sort_order asc",
	)
	return {r.question_code: r for r in rows}


def validate_vendor_onboarding(doc, method) -> None:
	"""
	Supplier validate hook: enforce MSA Agreement and log/validate FAQ
	answer changes.

	custom_msa_agreement's reqd:1 became reqd:0 (+ mandatory_depends_on) so
	the field can be hidden client-side when the toggle is off; server-side
	mandatory checking only looks at the static reqd flag, so it's
	enforced here instead, only while settlement customizations are enabled.

	Parameters:
	    doc (Document, required): The Supplier document being validated.
	    method (str, required): The hook event name passed by Frappe.

	Returns:
	    None
	"""
	if not doc.custom_msa_agreement:
		frappe.throw(_("MSA Agreement is mandatory."), frappe.MandatoryError)

	faq_rows = _get_faq_master_rows()
	_log_faq_changes(doc, faq_rows)
	_validate_expected_answers(doc, faq_rows)


def sync_company_to_supplier(doc, method):
	"""Company is shown read-only on the onboarding web form -- the value
	comes from the Vendor Email record created when the invite was sent
	(set there by whoever sent the invite), prefilled here once rather
	than trusting whatever the client actually submitted for a read-only
	field. Also keeps the Accounts child table (Party Account) in sync
	with whatever Company currently holds -- that's the field ERPNext
	itself actually uses for company-specific behaviour, Supplier has no
	top-level "company" of its own."""
	if not doc.custom_company and doc.email_id:
		doc.custom_company = frappe.db.get_value("Vendor Email", doc.email_id, "company")

	if not doc.custom_company:
		return

	existing = [row.company for row in doc.get("accounts") if row.company]
	if doc.custom_company not in existing:
		doc.append("accounts", {"company": doc.custom_company})


def _log_faq_changes(doc, faq_rows) -> None:
	"""Append a Vendor FAQ Change Log row for each FAQ field whose value
	changed since the last save (skips the first save if left blank)."""
	before = doc.get_doc_before_save()

	for fieldname, row in faq_rows.items():
		new_value = doc.get(fieldname)
		old_value = before.get(fieldname) if before else None

		if new_value == old_value:
			continue
		if before is None and not new_value:
			continue  # first save, question left blank — nothing to log

		doc.append(
			"faq_change_log",
			{
				"question_label": row.question_label,
				"old_value": old_value or "",
				"new_value": new_value or "",
				"changed_on": now_datetime(),
				"changed_by": frappe.session.user,
			},
		)


def _validate_expected_answers(doc, faq_rows) -> None:
	"""For a webform-created Supplier, block submission unless every FAQ
	question with an expected_answer got that answer, and the Code of
	Conduct was accepted."""
	if not doc.get("is_created_from_webform"):
		return

	errors = []
	for fieldname, row in faq_rows.items():
		if not row.expected_answer:
			continue  # question has no right/wrong answer to enforce
			# (e.g. sustainable_goods_percentage)
		value = doc.get(fieldname)
		if value and value != row.expected_answer:
			errors.append(
				_('"{0}" must be "{1}" (you selected "{2}")').format(
					row.question_label, row.expected_answer, value
				)
			)

	if errors:
		frappe.throw(
			_("Submission blocked. Please review the following:<br>{0}").format("<br>".join(errors)),
			title=_("Cannot Submit"),
		)

	if not doc.get("code_of_conduct_accepted"):
		frappe.throw(_("You must accept the Code of Conduct to submit this form."))


def update_brn_msa_agreement(self, method) -> None:
	"""
	Supplier validate hook: propagate this Supplier's MSA Agreement value
	onto every Supplier Quotation, BRN, and Purchase Invoice that
	references it as either the existing or new vendor.

	Parameters:
	    self (Document, required): The Supplier document being validated.
	    method (str, required): The hook event name passed by Frappe.

	Returns:
	    None
	"""
	# Convert Supplier field (Yes/No) to checkbox value (1/0)
	msa_value = 1 if self.custom_msa_agreement == "Yes" else 0

	# Get all BRNs where this supplier is selected as Existing Vendor or New Vendor
	filters = {}

	if self.name:
		filters = {"supplier": self.name, "is_existing_vendor": 1}
	elif self.supplier_name:
		filters = {"new_vendor": self.supplier_name, "is_new_vendor": 1}

	if filters:
		frappe.db.set_value("Supplier Quotation", filters, "msa_agreement", msa_value)

	brns = frappe.get_all(
		"BRN", filters=[["BRN", "docstatus", "!=", 2]], fields=["name", "is_existing_vendor", "is_new_vendor"]
	)

	for brn in brns:
		filters = {"name": brn.name}

		if brn.is_existing_vendor:
			filters["existing_vendor"] = self.name

		elif brn.is_new_vendor:
			filters["new_vendor"] = self.name

		else:
			continue

		if frappe.db.exists("BRN", filters):
			frappe.db.set_value(
				"BRN",
				brn.name,
				"msa_agreement",
				msa_value,
			)
		if frappe.db.exists(
			"Purchase Invoice", {"brn": brn.name, "supplier": self.name, "docstatus": ["!=", 2]}
		):
			frappe.db.set_value(
				"Purchase Invoice",
				{"brn": brn.name, "supplier": self.name, "docstatus": ["!=", 2]},
				"msa_agreement",
				msa_value,
			)
