import frappe

def manage_supplier_role_based_on_workflow(doc):
	if not doc.email_id:
		return

	user_id = frappe.db.get_value("User", {"email": doc.email_id}, "name")
	if not user_id:
		return

	if not frappe.db.exists("Has Role", {"parent": user_id, "role": "Supplier"}):
		frappe.get_doc({
			"doctype": "Has Role",
			"parent": user_id,
			"parenttype": "User",
			"parentfield": "roles",
			"role": "Supplier"
		}).insert(ignore_permissions=True)
		# Has Role is inserted directly here rather than via User.save(), so
		# User's own cache-clearing on update never fires -- frappe.get_roles()
		# caches per-user in redis (see frappe.permissions.get_roles) and
		# would otherwise keep returning the pre-grant role list until the
		# vendor's next fresh login, hiding role-gated portal sidebar items
		# even though the role was actually granted.
		frappe.cache.hdel("roles", user_id)

def update_vendor_email_doc(doc, method=None):
	if not doc.is_created_from_webform:
		return

	if doc.email_id:
		if frappe.db.exists("Vendor Email", doc.email_id):
			frappe.db.set_value("Vendor Email", doc.email_id, "supplier_created", 1)

		existing_users = [d.user for d in doc.get("portal_users") if d.user]

		if (
			doc.email_id not in existing_users
			and frappe.db.exists("User", doc.email_id)
		):
			doc.append("portal_users", {"user": doc.email_id})

def update_supplier_in_brn(doc, method=None):
	if not doc.brn:
		return

	update_comparision_row_for_onboarded_vendor(doc)
	log_supplier_onboarded_from_brn(doc)


def update_comparision_row_for_onboarded_vendor(doc):
	"""BRN itself no longer carries supplier/existing_vendor/is_new_vendor
	-- those fields were removed from the parent and now live only on its
	Comparision child table -- so linking a newly onboarded Supplier back
	to the BRN it came from means finding the row whose Email ID matches
	the email this vendor actually onboarded on (rather than whichever
	row happens to still be marked Preferred by the time onboarding
	completes, which could have changed) and updating that row, the same
	way BRN's own now-removed existing_vendor/is_new_vendor pair used to
	work at the top level."""
	if not doc.email_id:
		return

	brn = frappe.get_doc("BRN", doc.brn)
	matched = False
	for row in brn.comparision:
		if row.email_id and row.email_id.strip().lower() == doc.email_id.strip().lower():
			row.is_new_vendor = 0
			row.is_existing_vendor = 1
			row.existing_vendor = doc.name
			matched = True

	if matched:
		brn.save(ignore_permissions=True)

def log_supplier_onboarded_from_brn(doc):
	# reference_name has to point at a real document -- guard each insert
	# individually rather than bailing out on the whole function, so a
	# stale/mistyped doc.brn only costs the BRN-side comment, not the
	# Supplier-side one (and vice versa).
	if frappe.db.exists("BRN", doc.brn):
		frappe.get_doc({
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "BRN",
			"reference_name": doc.brn,
			"content": f"Vendor {frappe.bold(doc.name)} was onboarded from this BRN.",
		}).insert(ignore_permissions=True)

	if frappe.db.exists("Supplier", doc.name):
		frappe.get_doc({
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "Supplier",
			"reference_name": doc.name,
			"content": f"This Supplier was onboarded from BRN {frappe.bold(doc.brn)}.",
		}).insert(ignore_permissions=True)

def create_bank_accounts_for_supplier(doc, method=None):
	for row in doc.get("bank_account") or []:
		if row.bank_account or not row.bank_account_no:
			continue

		bank_account = create_bank_account_for_row(doc, row)
		row.db_set("bank_account", bank_account.name, update_modified=False)


def create_bank_account_for_row(doc, row):
	bank_account = frappe.get_doc({
		"doctype": "Bank Account",
		"account_name": doc.supplier_name or doc.name,
		"bank": get_or_create_bank(row.bank_name),
		"party_type": "Supplier",
		"party": doc.name,
		"bank_account_no": row.bank_account_no,
		"ifsc": row.ifsc,
		"branch_code": row.ifsc,
	})
	bank_account.insert(ignore_permissions=True)
	return bank_account


def get_or_create_bank(bank_name):
	bank_name = (bank_name or "").strip() or "Unspecified Bank"
	existing = frappe.db.exists("Bank", bank_name)
	if existing:
		return existing

	bank = frappe.get_doc({"doctype": "Bank", "bank_name": bank_name})
	bank.insert(ignore_permissions=True)
	return bank.name


def create_supplier_address(doc):
	if supplier_address_exists(doc):
		return

	if not doc.is_created_from_webform:
		return

	address = get_supplier_address_doc(doc)
	address.flags.ignore_permissions = True
	address.insert(ignore_permissions=True)

def supplier_address_exists(doc):
	return frappe.db.sql(
		"""
		SELECT a.name
		FROM `tabAddress` a
		INNER JOIN `tabDynamic Link` dl
			ON dl.parent = a.name
		WHERE
			dl.link_doctype = 'Supplier'
			AND dl.link_name = %s
			AND IFNULL(a.address_line1, '') = %s
			AND IFNULL(a.city, '') = %s
			AND IFNULL(a.state, '') = %s
			AND IFNULL(a.country, '') = %s
			AND IFNULL(a.pincode, '') = %s
		LIMIT 1
		""",
		(
			doc.name,
			doc.get("address_line1") or "",
			doc.get("city") or "",
			doc.get("state") or "",
			doc.get("country") or "",
			doc.get("pincode") or "",
		),
	)


def get_supplier_address_doc(doc):
	return frappe.get_doc({
		"doctype": "Address",
		"address_title": doc.get("supplier_name"),
		"address_type": "Billing",
		"address_line1": doc.get("address_line1"),
		"city": doc.get("city"),
		"state": doc.get("state"),
		"country": doc.get("country"),
		"pincode": doc.get("pincode"),
		"phone": doc.get("mobile_no") or doc.get("phone"),
		"email_id": doc.get("email_id"),
		"gstin": doc.get("gstin"),
		"gst_category": doc.get("gst_category") or "Unregistered",
		"applicable_date": "2020-01-01",
		"cancellation_date": "2099-12-31",
		"is_primary_address": 1,
		"links": [
			{
				"link_doctype": "Supplier",
				"link_name": doc.name,
			}
		],
	})