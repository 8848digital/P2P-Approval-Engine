# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
import frappe
from frappe.model.document import Document


class KYCValidationRun(Document):
	"""One KYC validation pass for a Supplier: one or more vendor checks
	(see KYCValidationLog child rows), with a rolled-up overall_status."""

	def validate(self) -> None:
		"""Default run_by/run_on, and recompute the summary counts/overall_status."""
		if not self.run_by:
			self.run_by = frappe.session.user
		if not self.run_on:
			self.run_on = frappe.utils.now_datetime()
		self.recompute_summary()

	def recompute_summary(self) -> None:
		"""Set total_checks/success_count/failed_count and overall_status
		(Success if every log row succeeded, Failed if none did or there
		are no rows at all, Partial otherwise) from self.logs."""
		total = len(self.logs)
		success = sum(1 for r in self.logs if r.status == "Success")
		failed = sum(1 for r in self.logs if r.status in ("Failed", "Error"))

		self.total_checks = total
		self.success_count = success
		self.failed_count = failed

		if total == 0:
			self.overall_status = "Failed"
		elif success == total:
			self.overall_status = "Success"
		elif success == 0:
			self.overall_status = "Failed"
		else:
			self.overall_status = "Partial"

	def on_update(self) -> None:
		"""Roll up this run's outcome onto the Supplier (for list views/
		dashboards without opening the run), then re-evaluate whether the
		Supplier should be put on/off hold."""
		# Keep a lightweight rollup on the Supplier so list views / dashboards can
		# show "last KYC status" without opening the run.
		frappe.db.set_value(
			"Supplier",
			self.supplier,
			{
				"custom_last_kyc_status": self.overall_status,
				"custom_last_kyc_run": self.name,
			},
			update_modified=False,
		)

		from approval_engine.settlement.kyc_validation.utils import evaluate_supplier_hold

		evaluate_supplier_hold(self.supplier)
