// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.
frappe.ui.form.on("KYC Vendor", {
	refresh(frm) {
		if (frm.doc.__islocal) return;

		frm.add_custom_button(__("Test with Sample Values"), () => {
			frappe.call({
				method: "approval_engine.settlement.api.v1.kyc_validation.test_kyc_vendor",
				args: { vendor_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Calling API with sample values..."),
				callback: (r) => {
					const m = r.data;
					if (!m) return;
					const color =
						m.status === "Success"
							? "green"
							: m.status === "Failed"
							? "red"
							: "orange";
					frappe.msgprint({
						title: __("Test Result — {0}", [m.status]),
						indicator: color,
						message: `
							<p><b>${__("Status")}:</b> <span class="indicator-pill ${color}">${m.status}</span></p>
							<p><b>${__("HTTP Code")}:</b> ${m.http_status_code ?? "-"}</p>
							<p><b>${__("Message")}:</b> ${frappe.utils.escape_html(m.message || "")}</p>
							<details><summary>${__("Request")}</summary><pre>${frappe.utils.escape_html(
							m.request || ""
						)}</pre></details>
							<details><summary>${__("Response")}</summary><pre>${frappe.utils.escape_html(
							m.response || ""
						)}</pre></details>
						`,
					});
				},
			});
		}).addClass("btn-default");
	},
});
