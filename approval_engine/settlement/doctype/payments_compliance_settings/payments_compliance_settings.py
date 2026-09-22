# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# Copyright (c) 2026, Jio Financial Services and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Landing route for any Role listed in Allowed Roles -- see before_save/
# on_update below. Kept in sync with the Page name at
# page/procure_to_pay_management/procure_to_pay_management.json.
PROCURE_TO_PAY_MANAGEMENT_HOME_PAGE = "/app/procure-to-pay-management"


class PaymentsComplianceSettings(Document):
	"""Single: MSME ageing-bucket thresholds, dashboard access (Allowed
	Roles), Workflow State Mapping, and chart display settings for the
	Payments Compliance / Procure-to-Pay dashboard (see
	customization/procure_to_pay/dashboard_data.py)."""

	def validate(self) -> None:
		"""Enforce that the four MSME ageing-bucket day thresholds are
		strictly increasing, so build_dashboard_payload's bucket ranges
		never overlap or invert."""
		b1 = self.immediate_due_days or 5
		b2 = self.bucket_2_end_days or 14
		b3 = self.bucket_3_end_days or 30
		b4 = self.bucket_4_end_days or 45

		if not (b1 < b2 < b3 < b4):
			frappe.throw(
				_(
					"MSME ageing buckets must be increasing: "
					"Immediate Due < Bucket 2 End < Bucket 3 End < Bucket 4 End"
				)
			)

	def before_save(self) -> None:
		"""Snapshot the CURRENT (pre-save) Allowed Roles from the DB -- child
		table rows are only replaced later in the save cycle (see
		Document._save -> update_children(), which runs after
		before_save), so this still reflects the old list. on_update
		compares this against the new list to know which roles were
		removed, so it can clear a stale Home Page redirect for them."""
		self.flags.previous_allowed_roles = set(
			frappe.get_all(
				"Payments Compliance Allowed Role",
				filters={"parent": self.name, "parentfield": "allowed_roles"},
				pluck="role",
			)
		)

	def on_update(self) -> None:
		"""Every Role listed in Allowed Roles lands directly on the Procure
		to Pay Management dashboard after login (Role.home_page is
		Frappe's own per-role post-login redirect field). Only touches
		roles actually in our list, and only clears a role's Home Page
		when it still points at OUR route -- never clobbers a Home Page
		an admin set for some other, unrelated reason."""
		new_roles = {row.role for row in (self.get("allowed_roles") or []) if row.role}
		previous_roles = self.flags.previous_allowed_roles or set()

		for role in new_roles:
			if frappe.db.get_value("Role", role, "home_page") != PROCURE_TO_PAY_MANAGEMENT_HOME_PAGE:
				frappe.db.set_value("Role", role, "home_page", PROCURE_TO_PAY_MANAGEMENT_HOME_PAGE)

		for role in previous_roles - new_roles:
			if frappe.db.get_value("Role", role, "home_page") == PROCURE_TO_PAY_MANAGEMENT_HOME_PAGE:
				frappe.db.set_value("Role", role, "home_page", "")
