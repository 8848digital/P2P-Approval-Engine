// Copyright (c) 2026, p2p_customization
// KYC Validation button + dialog for the Supplier doctype.

frappe.ui.form.on("Supplier", {
	refresh(frm) {
		if (frm.doc.__islocal) return;
		frm.add_custom_button(__("KYC Validation"), () => open_kyc_dialog(frm)).addClass(
			"btn-primary"
		);
		render_last_kyc_indicator(frm);
	},
});

function render_last_kyc_indicator(frm) {
	if (!frm.dashboard || !frm.doc.custom_last_kyc_status) return;
	const color =
		frm.doc.custom_last_kyc_status === "Success"
			? "green"
			: frm.doc.custom_last_kyc_status === "Failed"
			? "red"
			: "orange";
	frm.dashboard.add_indicator(__("Last KYC: {0}", [frm.doc.custom_last_kyc_status]), color);
	if (frm.doc.custom_kyc_hold_active && frm.doc.custom_kyc_blocked_types) {
		frm.dashboard.add_indicator(
			__("On Hold — pending: {0}", [frm.doc.custom_kyc_blocked_types]),
			"red"
		);
	}
}

function status_pill(status) {
	const map = {
		Success: "green",
		Failed: "red",
		Error: "orange",
		Skipped: "gray",
		Pending: "blue",
	};
	return `<span class="indicator-pill ${map[status] || "gray"}">${__(status)}</span>`;
}

class KYCDialog {
	constructor(frm) {
		this.frm = frm;
		this.run_name = null;
	}

	open() {
		frappe.call({
			method: "p2p_customization.settlement.api.v1.kyc_validation.get_kyc_vendor_options",
			args: { supplier: this.frm.doc.name },
			callback: (r) => this.build_dialog(r.message || []),
		});
	}

	build_dialog(vendors) {
		if (!vendors.length) {
			frappe.msgprint({
				title: __("No KYC Checks Available"),
				message: __(
					"Ask your System Manager to enable at least one KYC Vendor in JFS Settings."
				),
				indicator: "orange",
			});
			return;
		}

		const options = vendors.map((v) => ({
			label: `${v.vendor_name} (${v.kyc_type})`,
			value: v.name,
			description: v.description,
		}));
		const default_checked = vendors.filter((v) => v.checked).map((v) => v.name);

		this.dialog = new frappe.ui.Dialog({
			title: __("KYC Validation — {0}", [this.frm.doc.supplier_name || this.frm.doc.name]),
			size: "extra-large",
			fields: [
				{
					fieldname: "kyc_vendors",
					fieldtype: "MultiSelectPills",
					label: __("Select KYC Checks to Run"),
					options,
					default: default_checked,
				},
				{ fieldname: "sb1", fieldtype: "Section Break" },
				{ fieldname: "results_html", fieldtype: "HTML" },
			],
			primary_action_label: __("Run Validation"),
			primary_action: (values) => {
				if (!values.kyc_vendors || !values.kyc_vendors.length) {
					frappe.msgprint(__("Select at least one KYC check"));
					return;
				}
				this.run(values.kyc_vendors);
			},
		});

		this.dialog.$wrapper.find(".modal-dialog").css("max-width", "900px");
		this.bind_events();
		this.dialog.show();

		// Load and preview the most recent KYC run (if any) right away,
		// so the user can review / revalidate without re-running everything.
		this.load_existing_results();
	}

	set_html(html) {
		this.dialog.get_field("results_html").$wrapper.html(html);
	}

	load_existing_results() {
		this.set_html(
			`<div class="text-muted kyc-loading">${__("Loading previous KYC results...")}</div>`
		);

		frappe.call({
			method: "p2p_customization.settlement.api.v1.kyc_validation.get_last_kyc_run",
			args: { supplier: this.frm.doc.name },
			callback: (res) => {
				if (!res.message || !res.message.run) {
					this.set_html(
						`<div class="text-muted kyc-empty">${__(
							"No previous KYC validation found for this supplier. Select checks above and click Run Validation."
						)}</div>`
					);
					return;
				}
				this.run_name = res.message.run;
				const normalized = {
					...res.message,
					rows: (res.message.rows || []).map((row) => this.normalize_row(row)),
				};
				this.render_results(normalized, true);
			},
			error: () => {
				this.set_html("");
			},
		});
	}

	// Different backend endpoints may key the vendor identifier differently
	// (vendor / kyc_vendor / vendor_name / etc). Normalize here so the rest
	// of the dialog can always rely on row.vendor being set correctly.
	normalize_row(row) {
		const vendor =
			row.vendor || row.kyc_vendor || row.vendor_name || row.vendor_id || row.name;
		if (!vendor) {
			console.warn("KYC row missing vendor identifier:", row);
		}
		return { ...row, vendor };
	}

	run(vendor_names) {
		this.dialog.disable_primary_action();
		this.set_html(`<div class="text-muted kyc-loading">${__("Running checks...")}</div>`);

		frappe.call({
			method: "p2p_customization.settlement.api.v1.kyc_validation.run_kyc_validation",
			args: { supplier: this.frm.doc.name, vendors: JSON.stringify(vendor_names) },
			callback: (res) => {
				this.dialog.enable_primary_action();
				if (!res.message) return;
				this.run_name = res.message.run;
				const normalized = {
					...res.message,
					rows: (res.message.rows || []).map((row) => this.normalize_row(row)),
				};
				this.render_results(normalized, false);
				this.frm.reload_doc();
			},
			error: () => this.dialog.enable_primary_action(),
		});
	}

	render_results(data, is_preview = false) {
		const preview_note = is_preview
			? `<div class="kyc-preview-note text-muted mb-2">
					<i class="fa fa-history"></i>
					${__(
						"Showing results from the last KYC run. Use Revalidate or Fix Details & Retry on any check below, or select checks above and click Run Validation to start a fresh run."
					)}
				</div>`
			: "";

		const summary = `
			<div class="kyc-summary mb-3">
				<b>${__("Run")}:</b>
				<a href="/desk/kyc-validation-run/${data.run}" target="_blank">${data.run}</a>
				&nbsp;·&nbsp; <b>${__("Result")}:</b> ${status_pill(data.overall_status)}
				&nbsp;·&nbsp; <span class="text-muted">${data.success_count}/${data.total_checks} ${__(
			"passed"
		)}</span>
			</div>`;
		const cards = data.rows.map((row) => this.render_card(row)).join("");
		this.set_html(`${preview_note}${summary}<div class="kyc-card-grid">${cards}</div>`);
	}

	render_card(row) {
		const is_success = row.status === "Success";
		const border = is_success ? "#2f9e44" : row.status === "Error" ? "#e8590c" : "#e03131";
		const icon = is_success ? "&#10003;" : "&#10007;";

		return `
		<div class="kyc-card" data-vendor="${row.vendor}" style="border-left:4px solid ${border};">
			<div class="kyc-card-head">
				<span class="kyc-card-icon" style="color:${border};">${icon}</span>
				<div class="kyc-card-title-wrap">
					<div class="kyc-card-title">${frappe.utils.escape_html(row.vendor)}</div>
					<div class="kyc-card-sub text-muted">${frappe.utils.escape_html(row.kyc_type || "")} · ${__(
			"Attempt"
		)} ${row.attempt_no}</div>
				</div>
				<div class="kyc-card-status">${status_pill(row.status)}</div>
			</div>
			<div class="kyc-card-message text-muted">${frappe.utils.escape_html(row.message || "")}</div>
			<div class="kyc-card-actions">
				<button class="btn btn-xs btn-default kyc-revalidate" data-vendor="${row.vendor}">${__(
			"Revalidate"
		)}</button>
				${
					!is_success
						? `<button class="btn btn-xs btn-default kyc-fix" data-vendor="${
								row.vendor
						  }">${__("Fix Details & Retry")}</button>`
						: ""
				}
			</div>
			<div class="kyc-fix-form" style="display:none;"></div>
		</div>`;
	}

	bind_events() {
		const $wrap = this.dialog.$wrapper;

		$wrap.on("click", ".kyc-revalidate", (e) => {
			const vendor = $(e.currentTarget).data("vendor");
			if (!vendor || vendor === "undefined") {
				frappe.msgprint(
					__(
						"Could not determine the KYC vendor for this row. Please run a fresh validation."
					)
				);
				return;
			}
			this.revalidate([vendor]);
		});

		$wrap.on("click", ".kyc-fix", (e) => {
			const $card = $(e.currentTarget).closest(".kyc-card");
			const vendor = $(e.currentTarget).data("vendor");
			if (!vendor || vendor === "undefined") {
				frappe.msgprint(
					__(
						"Could not determine the KYC vendor for this row. Please run a fresh validation."
					)
				);
				return;
			}
			const $form_area = $card.find(".kyc-fix-form");

			if ($form_area.is(":visible")) {
				$form_area.slideUp();
				return;
			}
			this.show_fix_form($form_area, vendor);
		});

		$wrap.on("click", ".kyc-save-and-retry", (e) => {
			const $card = $(e.currentTarget).closest(".kyc-card");
			const vendor = $(e.currentTarget).data("vendor");
			if (!vendor || vendor === "undefined") {
				frappe.msgprint(
					__(
						"Could not determine the KYC vendor for this row. Please run a fresh validation."
					)
				);
				return;
			}
			const updates = {};
			$card.find(".kyc-fix-input").each(function () {
				updates[$(this).data("fieldname")] = $(this).val();
			});

			frappe.call({
				method: "frappe.client.set_value",
				args: { doctype: "Supplier", name: this.frm.doc.name, fieldname: updates },
				freeze: true,
				freeze_message: __("Saving corrected details..."),
				callback: () => {
					this.frm.reload_doc();
					this.revalidate([vendor], __("Corrected by user before revalidation"));
				},
			});
		});
	}

	show_fix_form($container, vendor_name) {
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "KYC Vendor", name: vendor_name },
			callback: (r) => {
				const vendor_doc = r.message;
				const rows = (vendor_doc.field_map || [])
					.map(
						(fm) => `
						<div class="form-group">
							<label>${frappe.utils.escape_html(fm.supplier_fieldname)}</label>
							<input type="text" class="form-control input-sm kyc-fix-input"
								data-fieldname="${fm.supplier_fieldname}"
								value="${frappe.utils.escape_html(this.frm.doc[fm.supplier_fieldname] || "")}">
						</div>`
					)
					.join("");

				$container
					.html(
						`
						<div class="kyc-fix-inner">
							${rows}
							<button class="btn btn-xs btn-primary kyc-save-and-retry" data-vendor="${vendor_name}">
								${__("Save & Revalidate")}
							</button>
						</div>
					`
					)
					.slideDown();
			},
		});
	}

	revalidate(vendor_names, remarks) {
		vendor_names = (vendor_names || []).filter((v) => v && v !== "undefined");
		if (!vendor_names.length) {
			frappe.msgprint(__("Could not determine the KYC vendor to revalidate."));
			return;
		}
		if (!this.run_name) {
			// No run to attach to yet (shouldn't normally happen since the
			// preview always sets this.run_name when a prior run exists).
			frappe.msgprint(
				__("No KYC run found to revalidate against. Please run validation first.")
			);
			return;
		}
		const $wrap = this.dialog.$wrapper;
		vendor_names.forEach((v) =>
			$wrap.find(`.kyc-card[data-vendor="${v}"]`).css("opacity", 0.5)
		);

		frappe.call({
			method: "p2p_customization.settlement.api.v1.kyc_validation.revalidate_in_run",
			args: {
				run_name: this.run_name,
				vendors: JSON.stringify(vendor_names),
				remarks: remarks || null,
			},
			callback: (res) => {
				frappe.show_alert({ message: __("Revalidation complete"), indicator: "green" });
				vendor_names.forEach((vendor) => {
					const updated_row = res.message.rows
						.filter((r) => r.vendor === vendor)
						.sort((a, b) => b.attempt_no - a.attempt_no)[0];
					if (updated_row) {
						const $new_card = $(this.render_card(updated_row));
						$wrap.find(`.kyc-card[data-vendor="${vendor}"]`).replaceWith($new_card);
					}
				});
				this.frm.reload_doc();
			},
		});
	}
}

function open_kyc_dialog(frm) {
	new KYCDialog(frm).open();
}
