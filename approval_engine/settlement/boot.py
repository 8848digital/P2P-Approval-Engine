# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# apps/approval_engine/approval_engine/settlement/boot.py
import frappe


def boot_session(bootinfo):
	"""extend_bootinfo hook: exposes the FAQ Section toggle and the
	configured FAQ Manager Role from JFS Settings so client-side depends_on
	expressions (e.g. on the Supplier form's faq_section Tab Break) can read
	them synchronously instead of making an extra server call. Toggling
	either setting takes effect for a session on its next full page
	load/login, same as any other boot value.

	JFS Settings is owned by jfs_report_customization, which isn't a
	required_apps dependency here -- on a site without it installed, the
	FAQ section stays disabled (falls back to the same defaults used
	elsewhere in this app) instead of failing every page load.
	"""
	if not frappe.db.exists("DocType", "JFS Settings"):
		bootinfo.jfs_faq_section_enabled = 0
		bootinfo.jfs_faq_manager_role = "Vendor FAQ Manager"
		return

	bootinfo.jfs_faq_section_enabled = frappe.db.get_single_value(
		"JFS Settings", "enable_faq_section"
	)
	bootinfo.jfs_faq_manager_role = (
		frappe.db.get_single_value("JFS Settings", "faq_manager_role") or "Vendor FAQ Manager"
	)
