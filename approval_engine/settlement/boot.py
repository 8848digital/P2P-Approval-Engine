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
	"""
	bootinfo.jfs_faq_section_enabled = frappe.db.get_single_value("JFS Settings", "enable_faq_section")
	bootinfo.jfs_faq_manager_role = (
		frappe.db.get_single_value("JFS Settings", "faq_manager_role") or "Vendor FAQ Manager"
	)
