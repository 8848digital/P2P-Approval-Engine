# Copyright (c) 2026, p2p_customization
import frappe

def evaluate_supplier_hold(supplier_name):
	settings = frappe.get_single("JFS Settings")

	if not settings.auto_hold_supplier_on_kyc_failure:
		return  # feature switched off — never touch on_hold automatically

	required_types = [d.kyc_check_type for d in (settings.block_supplier_on_failure_types or [])]
	if not required_types:
		return  # nothing configured to enforce
	frappe.log_error("required_types",required_types)

	unverified = [t for t in required_types if get_latest_status_for_type(supplier_name, t) != "Success"]
	frappe.log_error("unverified",unverified)

	supplier = frappe.get_doc("Supplier", supplier_name)

	if unverified:
		_set_on_hold(supplier, unverified, settings.hold_type_to_apply or "All")
	else:
		_release_hold_if_ours(supplier)


def get_latest_status_for_type(supplier_name, kyc_type):

	rows = frappe.db.sql(
		"""
		SELECT l.status
		FROM `tabKYC Validation Log` l
		INNER JOIN `tabKYC Validation Run` r ON r.name = l.parent
		WHERE r.supplier = %s AND l.kyc_type = %s AND l.status != 'Error'
		ORDER BY l.checked_on DESC
		LIMIT 1
		""",
		(supplier_name, kyc_type),
		as_dict=True,
	)
	frappe.log_error("rows",rows)
	return rows[0].status if rows else None


def _set_on_hold(supplier, unverified_types, hold_type):
	updates = {
		"on_hold": 1,
		"hold_type": hold_type,
		"custom_kyc_hold_active": 1,
		"custom_kyc_blocked_types": ", ".join(unverified_types),
	}
	for fieldname, value in updates.items():
		frappe.db.set_value("Supplier", supplier.name, fieldname, value, update_modified=False)

	frappe.publish_realtime(
		"kyc_supplier_hold_changed",
		{"supplier": supplier.name, "on_hold": 1, "blocked_types": unverified_types},
		user=frappe.session.user,
	)


def _release_hold_if_ours(supplier):
	"""Only auto-clear on_hold if OUR automation was the one that set it —
	never silently lift a hold a human placed manually for an unrelated reason."""
	if supplier.get("custom_kyc_hold_active"):
		frappe.db.set_value(
			"Supplier",
			supplier.name,
			{
				"on_hold": 0,
				"custom_kyc_hold_active": 0,
				"custom_kyc_blocked_types": "",
			},
			update_modified=False,
		)
		frappe.publish_realtime(
			"kyc_supplier_hold_changed",
			{"supplier": supplier.name, "on_hold": 0, "blocked_types": []},
			user=frappe.session.user,
		)
	else:
		# not ours to release, but keep the visibility field accurate
		frappe.db.set_value("Supplier", supplier.name, "custom_kyc_blocked_types", "", update_modified=False)
