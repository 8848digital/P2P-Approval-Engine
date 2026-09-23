# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# apps/approval_engine/approval_engine/settlement/permissions/faq_master.py
import frappe

VENDOR_FAQ_MANAGER_ROLE = (
	"Vendor FAQ Manager"  # fallback if JFS Settings.faq_manager_role is unset
)


def _faq_manager_role():
	if not frappe.db.exists("DocType", "JFS Settings"):
		return VENDOR_FAQ_MANAGER_ROLE
	return frappe.db.get_single_value("JFS Settings", "faq_manager_role") or VENDOR_FAQ_MANAGER_ROLE


def _faq_section_enabled():
	# JFS Settings is owned by jfs_report_customization, which isn't a
	# required_apps dependency here -- without it, the FAQ section stays
	# disabled (nothing visible) instead of every FAQ Master access crashing.
	if not frappe.db.exists("DocType", "JFS Settings"):
		return False
	return bool(frappe.db.get_single_value("JFS Settings", "enable_faq_section"))


def has_permission(doc, ptype, user):
	"""has_permission hook for FAQ Master (per-document checks: read/write/
	create/delete on a specific doc). Mirrors the Supplier form's Vendor
	FAQs tab gate (doc_events.faq_master.FAQ_SECTION_VISIBILITY_DEPENDS_ON):
	the configured FAQ Manager Role only grants access while JFS
	Settings.enable_faq_section is on, so "disabled" means nothing is
	visible, not just that the Supplier tab is hidden. System Manager always
	passes, matching the client-side check.
	"""
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True

	if _faq_manager_role() not in frappe.get_roles(user):
		return False

	return _faq_section_enabled()


def get_permission_query_conditions(user):
	"""permission_query_conditions hook for FAQ Master: without this, list
	view/report queries only go through DocPerm (not the per-doc
	has_permission hook above), so a Vendor FAQ Manager would still see
	every row while the section is disabled. Returns a condition matching
	no rows in that case; System Manager is left unrestricted.
	"""
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return ""

	if not _faq_section_enabled():
		return "1=0"

	return ""
