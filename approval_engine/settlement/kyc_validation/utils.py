# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
import frappe
from pypika import Order


def evaluate_supplier_hold(supplier_name: str) -> None:
	"""
	Put a Supplier on/off hold based on whether every KYC check type
	configured in JFS Settings' "Block Supplier On Failure Types" currently
	has a Success status -- called from KYCValidationRun.on_update() after
	every validation run.

	Parameters:
		supplier_name (str, required): The Supplier document name.

	Returns:
		None
	"""
	settings = frappe.get_single("JFS Settings")

	if not settings.auto_hold_supplier_on_kyc_failure:
		return  # feature switched off — never touch on_hold automatically

	required_types = [d.kyc_check_type for d in (settings.block_supplier_on_failure_types or [])]
	if not required_types:
		return  # nothing configured to enforce

	latest_statuses = get_latest_statuses_for_types(supplier_name, required_types)
	unverified = [t for t in required_types if latest_statuses.get(t) != "Success"]

	supplier = frappe.get_doc("Supplier", supplier_name)

	if unverified:
		_set_on_hold(supplier, unverified, settings.hold_type_to_apply or "All")
	else:
		_release_hold_if_ours(supplier)


def get_latest_statuses_for_types(supplier_name: str, kyc_types: list) -> dict:
	"""
	Batch-fetch the latest non-Error status per kyc_type across this
	Supplier's KYC Validation Runs, in a single query -- one call covers
	every required type instead of one query per type.

	Parameters:
		supplier_name (str, required): The Supplier document name.
		kyc_types (list, required): The KYC check types to look up.

	Returns:
		dict: {kyc_type: latest_status}. A kyc_type with no non-Error log
			row is simply absent.
	"""
	if not kyc_types:
		return {}

	Log = frappe.qb.DocType("KYC Validation Log")
	Run = frappe.qb.DocType("KYC Validation Run")

	rows = (
		frappe.qb.from_(Log)
		.inner_join(Run)
		.on(Run.name == Log.parent)
		.select(Log.kyc_type, Log.status, Log.checked_on)
		.where(Run.supplier == supplier_name)
		.where(Log.kyc_type.isin(kyc_types))
		.where(Log.status != "Error")
		.orderby(Log.checked_on, order=Order.desc)
	).run(as_dict=True)

	# Rows are already ordered newest-first, so the first row seen per
	# kyc_type is its latest status.
	latest = {}
	for row in rows:
		latest.setdefault(row.kyc_type, row.status)
	return latest


def _set_on_hold(supplier, unverified_types: list, hold_type: str) -> None:
	"""Put supplier on hold and record which KYC check types are still
	unverified, then notify the desk in real time."""
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
