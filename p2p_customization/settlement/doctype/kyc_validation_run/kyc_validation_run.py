# Copyright (c) 2026, p2p_customization
import frappe
from frappe.model.document import Document


class KYCValidationRun(Document):
	def validate(self):
		if not self.run_by:
			self.run_by = frappe.session.user
		if not self.run_on:
			self.run_on = frappe.utils.now_datetime()
		self.recompute_summary()

	def recompute_summary(self):
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

	def on_update(self):
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

		from p2p_customization.settlement.kyc_validation.utils import evaluate_supplier_hold

		evaluate_supplier_hold(self.supplier)
