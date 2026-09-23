// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.
frappe.ui.form.on("KYC Validation Run", {
	refresh(frm) {
		style_status_column(frm);

		if (!frm.doc.__islocal) {
			frm.add_custom_button(__("Revalidate All Failed"), () => {
				const failed = (frm.doc.logs || [])
					.filter((r) => r.status !== "Success")
					.map((r) => r.kyc_vendor);
				if (!failed.length) {
					frappe.msgprint(__("Nothing to revalidate — everything already succeeded."));
					return;
				}
				run_revalidation(frm, failed, __("all failed checks"));
			}).addClass("btn-default");
		}
	},

	logs_on_form_rendered(frm, cdt, cdn) {
		// when a log row is expanded, add a Revalidate button inside its detail form
		add_row_revalidate_button(frm, cdt, cdn);
	},
});

frappe.ui.form.on("KYC Validation Log", {
	form_render(frm, cdt, cdn) {
		add_row_revalidate_button(frm, cdt, cdn);
	},
});

function add_row_revalidate_button(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const grid_row = frm.fields_dict.logs.grid.grid_rows_by_docname[cdn];
	if (!grid_row || !grid_row.form_area) return;

	// avoid duplicate buttons on re-render
	$(grid_row.form_area).find(".kyc-revalidate-row-btn").remove();

	const $btn = $(`
		<button class="btn btn-xs btn-primary kyc-revalidate-row-btn" style="margin: 8px 0;">
			${__("Revalidate this check")}
		</button>
	`).on("click", () => {
		run_revalidation(frm, [row.kyc_vendor], row.kyc_vendor);
	});
	$(grid_row.form_area).append($btn);
}

function run_revalidation(frm, vendor_names, label) {
	frappe.call({
		method: "approval_engine.settlement.api.v1.kyc_validation.revalidate_in_run",
		args: {
			run_name: frm.doc.name,
			vendors: JSON.stringify(vendor_names),
		},
		freeze: true,
		freeze_message: __("Revalidating {0}...", [label]),
		callback: () => {
			frappe.show_alert({ message: __("Revalidation complete"), indicator: "green" });
			frm.reload_doc();
		},
	});
}

function style_status_column(frm) {
	const grid = frm.fields_dict.logs && frm.fields_dict.logs.grid;
	if (!grid) return;
	const field = grid.get_field && grid.get_field("status");
	if (field && field.df) {
		field.df.formatter = (value) => {
			const map = {
				Success: "green",
				Failed: "red",
				Error: "orange",
				Skipped: "gray",
				Pending: "blue",
			};
			const color = map[value] || "gray";
			return `<span class="indicator-pill ${color}" style="font-weight:600;">${__(
				value || "Pending"
			)}</span>`;
		};
	}
	grid.refresh();
}
