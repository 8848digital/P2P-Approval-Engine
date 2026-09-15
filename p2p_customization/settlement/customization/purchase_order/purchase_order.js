frappe.ui.form.on('Purchase Order',  {
	setup: function(frm){
		frm.set_query("nature_of_service", "items", function() {
			return {
				query: "p2p_customization.settlement.customization.purchase_invoice.api.get_nature_of_service_query",
				filters: {
					supplier: frm.doc.supplier
				}
			};
		});
	},
	refresh(frm){
		if (!frm.is_new()) {
			frm.trigger("send_po_to_vendor");
		}
		make_mandatory(frm)
		setup_vendor_rate_comparison(frm);
	},
	supplier(frm){
		// supplier's legal type (Individual/HUF/etc.) decides which Tax
		// Withholding Category applies, so re-resolve it on any already
		// selected item rows when the supplier changes. Batched into one
		// call for every row instead of one round-trip per row.
		refresh_all_tax_withholding_categories(frm);
	},
	send_po_to_vendor(frm) {
		frm.add_custom_button(__('Send PO to Vendor'), function () {
			frappe.call({
				method: "p2p_customization.settlement.customization.purchase_order.api.send_po_to_vendor",
				args: {
					purchase_order: frm.doc.name,
				},
				callback: function (r) {
					if (r.message) {
						frappe.msgprint(__("Email sent to Vendor"));
					}
				}
			});
		});
	},
	validate: function(frm){
		// validate_brn_dates(frm)
	},
	onload_post_render: function(frm){
		apply_filters_based_on_requisition(frm)
		maybe_auto_show_rate_comparison(frm);
	},
	requisition_type: function(frm){
		make_mandatory(frm)
		apply_filters_based_on_requisition(frm)
	}
});

frappe.ui.form.on("Purchase Order Item", {
	nature_of_service: function(frm, cdt, cdn) {
		set_po_tax_withholding_category(frm, cdt, cdn);
	}
});

function set_po_tax_withholding_category(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row.nature_of_service) {
		frappe.model.set_value(cdt, cdn, "tax_withholding_category", "");
		frappe.model.set_value(cdt, cdn, "apply_tds", 0);
		return;
	}
	// Picks the category auto-created for this nature of service that matches
	// the supplier's legal type (Individual/HUF get their own category where
	// one exists, everyone else falls back to "Others").
	frappe.call({
		method: "p2p_customization.settlement.doc_events.tds_reference.get_tax_withholding_category",
		args: {
			nature_of_service: row.nature_of_service,
			supplier: frm.doc.supplier
		},
		callback: function(r) {
			apply_po_tax_withholding_category(cdt, cdn, r.message);
		}
	});
}

function apply_po_tax_withholding_category(cdt, cdn, category) {
	if (category) {
		frappe.model.set_value(cdt, cdn, "tax_withholding_category", category);
		frappe.model.set_value(cdt, cdn, "apply_tds", 1);
	} else {
		frappe.model.set_value(cdt, cdn, "tax_withholding_category", "");
		frappe.model.set_value(cdt, cdn, "apply_tds", 0);
	}
}

function refresh_all_tax_withholding_categories(frm) {
	const rows = (frm.doc.items || []).filter((row) => row.nature_of_service);
	if (!rows.length) return;

	const nature_of_services = [...new Set(rows.map((row) => row.nature_of_service))];
	frappe.call({
		method: "p2p_customization.settlement.doc_events.tds_reference.get_tax_withholding_categories",
		args: {
			nature_of_services: nature_of_services,
			supplier: frm.doc.supplier
		},
		callback: function(r) {
			const categories = r.message || {};
			rows.forEach((row) => {
				apply_po_tax_withholding_category(row.doctype, row.name, categories[row.nature_of_service]);
			});
		}
	});
}

function is_finally_approved(frm) {
	if (frm.doc.docstatus !== 1) return false;
	// frappe.workflow.get_state() -> get_default_state() reads
	// frappe.workflow.workflows[doctype].states without checking that
	// entry exists first -- and setup() only ever populates it when an
	// ACTIVE workflow exists for the doctype, so on a doctype with no
	// active workflow (every Purchase Order workflow on this site is
	// inactive) it throws, uncaught, from inside this function -- which
	// runs on every refresh of a submitted PO. That was silently cutting
	// off whatever ran after it in the same handler chain, including
	// core's own "Create" (Purchase Receipt/Invoice) dropdown. Guard
	// against the missing-workflow case explicitly, and keep the
	// try/catch as a defensive backstop against this same class of bug
	// resurfacing from a future core change.
	if (!frappe.workflow.workflows || !frappe.workflow.workflows[frm.doctype]) return false;
	try {
		// get_state() must run before get_all_transitions() -- it's the one
		// that triggers frappe.workflow.setup(), populating frappe.workflow.workflows.
		const state = frappe.workflow.get_state(frm.doc);
		if (!state) return false;
		const transitions = frappe.workflow.get_all_transitions(frm.doctype);
		return !transitions.some((t) => t.state === state && t.action === "Approve");
	} catch (e) {
		return false;
	}
}

// Cached across the page session -- Vendor Rate Comparison Settings rarely
// changes, and this avoids a round-trip on every form refresh.
let _rate_comparison_config_promise = null;
function fetch_rate_comparison_config() {
	if (!_rate_comparison_config_promise) {
		_rate_comparison_config_promise = new Promise((resolve) => {
			frappe.call({
				method: "p2p_customization.settlement.customization.purchase_order.api.get_vendor_rate_comparison_config",
				callback: (r) => resolve(r.message || { permitted: false, trigger_mode: "Both" })
			});
		});
	}
	return _rate_comparison_config_promise;
}

function can_show_rate_comparison(frm) {
	if (is_finally_approved(frm)) return false;
	const has_service_row = (frm.doc.items || []).some((d) => d.nature_of_service);
	return !!(frm.doc.supplier && frm.doc.company && frm.doc.transaction_date && has_service_row);
}

function setup_vendor_rate_comparison(frm) {
	if (!can_show_rate_comparison(frm)) return;
	fetch_rate_comparison_config().then((config) => {
		if (!config.permitted || config.trigger_mode === "Auto Show on Load") return;
		frm.add_custom_button(__('Vendor Rate Comparison'), () => show_rate_comparison_dialog(frm));
	});
}

// Called once, from onload_post_render, so it doesn't re-pop on every
// refresh (save, field-change re-renders, etc).
function maybe_auto_show_rate_comparison(frm) {
	if (!can_show_rate_comparison(frm)) return;
	fetch_rate_comparison_config().then((config) => {
		if (!config.permitted || config.trigger_mode === "Button Click Only") return;
		show_rate_comparison_dialog(frm, { silent_if_empty: true });
	});
}

function show_rate_comparison_dialog(frm, { silent_if_empty = false } = {}) {
	const nature_of_services = [...new Set((frm.doc.items || [])
		.filter((d) => d.nature_of_service)
		.map((d) => d.nature_of_service))];

	frappe.call({
		method: "p2p_customization.settlement.customization.purchase_order.api.get_vendor_rate_comparison",
		args: {
			supplier: frm.doc.supplier,
			nature_of_services: nature_of_services,
			company: frm.doc.company,
			transaction_date: frm.doc.transaction_date,
			brn: frm.doc.brn,
			exclude_po: (!frm.is_new() && frm.doc.name) ? frm.doc.name : null
		},
		freeze: !silent_if_empty,
		freeze_message: __("Fetching rate comparison..."),
		callback: (r) => {
			const data = r.message || {};
			const rows = data.rows || [];
			if (!rows.length) {
				if (!silent_if_empty) {
					frappe.msgprint(__("No comparable Purchase Orders found for this vendor."));
				}
				return;
			}
			render_rate_comparison_dialog(frm, rows, data.meta || {});
		}
	});
}

function rate_comparison_match_note(meta, supplier) {
	const period_desc = meta.period_type
		? `${meta.period_type.toLowerCase()} (${meta.period_months}-month)`
		: "quarterly";
	const brn_desc = meta.brn_based
		? __("this period length comes from the linked BRN's service duration")
		: __("no BRN service duration was available, so the default quarterly window was used");

	return `
		<div class="rate-comparison-note">
			<div class="rate-comparison-note-title">${frappe.utils.icon("info", "sm")} ${__("How this is matched")}</div>
			<ul>
				<li>${__("Rows are grouped by {0} and {1}, showing the most recent rate {2} charged in each period.",
					[`<b>${__("Company")}</b>`, `<b>${__("Nature of Service")}</b>`, `<b>${frappe.utils.escape_html(supplier || "")}</b>`])}</li>
				<li>${__("Current period: {0}. Previous period: {1}.",
					[`<b>${frappe.utils.escape_html(meta.current_period_label || "-")}</b>`, `<b>${frappe.utils.escape_html(meta.previous_period_label || "-")}</b>`])}</li>
				<li>${__("Periods are {0}, fiscal-year aligned (Apr–Mar); {1}.", [period_desc, brn_desc])}</li>
				<li>${__("Cancelled Purchase Orders are excluded; companies with no matching PO in either window are omitted.")}</li>
			</ul>
		</div>
	`;
}

function render_rate_comparison_dialog(frm, rows, meta) {
	const format_rate = (v) => v != null ? format_currency(v) : "<span class=\"text-muted\">–</span>";
	const format_po = (v) => v
		? `<a href="/app/purchase-order/${encodeURIComponent(v)}" target="_blank">${frappe.utils.escape_html(v)}</a>`
		: "<span class=\"text-muted\">–</span>";
	const format_variance = (v) => {
		if (v == null) return `<span class="text-muted">–</span>`;
		if (v === 0) return `<span class="indicator-pill gray">0%</span>`;
		const color = v > 0 ? "red" : "green";
		const arrow = v > 0 ? "↑" : "↓";
		return `<span class="indicator-pill ${color}">${arrow} ${Math.abs(v)}%</span>`;
	};

	const body_rows = rows.map((row) => `
		<tr>
			<td><b>${frappe.utils.escape_html(row.company || "")}</b></td>
			<td>${frappe.utils.escape_html(row.nature_of_service || "")}</td>
			<td>
				<div class="text-muted small">${frappe.utils.escape_html(row.current_period_label || "")}</div>
				<div>${format_rate(row.current_period_rate)}</div>
				<div class="small">${format_po(row.current_period_po)}</div>
			</td>
			<td>
				<div class="text-muted small">${frappe.utils.escape_html(row.previous_period_label || "")}</div>
				<div>${format_rate(row.previous_period_rate)}</div>
				<div class="small">${format_po(row.previous_period_po)}</div>
			</td>
			<td class="text-center">${format_variance(row.variance_percent)}</td>
		</tr>
	`).join("");

	const html = `
		<style>
			.rate-comparison-wrapper .table th { white-space: nowrap; background: var(--subtle-fg, #f5f6f7); }
			.rate-comparison-wrapper .table td, .rate-comparison-wrapper .table th { vertical-align: middle; }
			.rate-comparison-wrapper { overflow-x: auto; }
			.rate-comparison-note {
				margin-top: 14px;
				padding: 10px 14px;
				border-radius: var(--border-radius-md, 6px);
				background: var(--bg-light-gray, #f5f6f7);
				border: 1px solid var(--border-color, #d1d8dd);
				font-size: 12px;
				color: var(--text-muted, #6b7280);
			}
			.rate-comparison-note-title {
				font-weight: 600;
				color: var(--text-color, #1f272e);
				margin-bottom: 6px;
			}
			.rate-comparison-note ul { margin: 0; padding-left: 18px; }
			.rate-comparison-note li { margin-bottom: 3px; }
		</style>
		<div class="rate-comparison-wrapper">
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__("Company")}</th>
						<th>${__("Nature of Service")}</th>
						<th>${__("Current Period")}</th>
						<th>${__("Previous Period")}</th>
						<th class="text-center">${__("Variance")}</th>
					</tr>
				</thead>
				<tbody>${body_rows}</tbody>
			</table>
			${rate_comparison_match_note(meta, frm.doc.supplier)}
		</div>
	`;

	const dialog = new frappe.ui.Dialog({
		title: __("Vendor Rate Comparison"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "rate_comparison_html", options: html }]
	});
	dialog.show();
}

function apply_filters_based_on_requisition(frm){
	frm.set_query("item_code", "items", function() {
		let filters = { supplier: frm.doc.supplier };

		if (frm.doc.requisition_type === "Fixed Asset") {
			filters["is_fixed_asset"] = 1;
		}

		if (frm.doc.is_subcontracted) {
			if (frm.doc.is_old_subcontracting_flow) {
				filters["is_sub_contracted_item"] = 1;
			} else {
				filters["is_stock_item"] = 0;
			}
		} else {
			filters["is_purchase_item"] = 1;
			filters["has_variants"] = 0;
		}

		return {
			query: "erpnext.controllers.queries.item_query",
			filters: filters
		};
	});
}

function make_mandatory(frm){
	if (frm.doc.requisition_type == "Service") {
			frm.fields_dict.items.grid.toggle_reqd("qty", false)
			frm.fields_dict.items.grid.toggle_reqd("uom", false)
			frm.fields_dict.items.grid.toggle_reqd("rate", true)
			frm.fields_dict.items.grid.toggle_reqd("amount", true)
		}
	else{
		frm.fields_dict.items.grid.toggle_reqd("qty", true)
		frm.fields_dict.items.grid.toggle_reqd("uom", true)
		frm.fields_dict.items.grid.toggle_reqd("rate", false)
		frm.fields_dict.items.grid.toggle_reqd("amount", false)
	}
}

function validate_brn_dates(frm){
	if (frm.skip_brn_validation) {
		frm.skip_brn_validation = false;
		return;
	}

	if (!frm.doc.brn || !frm.doc.transaction_date) return;

	frappe.call({
		method: "p2p_customization.settlement.customization.purchase_order.api.validate_transaction_date_with_brn_dates",
		args: {
			brn: frm.doc.brn,
			transaction_date: frm.doc.transaction_date
		},
		async: false,
		callback: function(r) {
			if (!r.message) return;

			let msg = '';
			if (r.message.status === "before_start") {
				msg = `The BRN <b>${frm.doc.brn}</b> starts on <b>${r.message.start_date}</b>.<br>
					Your transaction date <b>${frm.doc.transaction_date}</b> is before that.<br><br>
					Do you still want to continue?`;
			} else if (r.message.status === "expired") {
				msg = `The BRN <b>${frm.doc.brn}</b> expired on <b>${r.message.expiry_date}</b>.<br>
					Your transaction date <b>${frm.doc.transaction_date}</b> is after expiry.<br><br>
					Do you still want to continue?`;
			}
			if(frm.is_dirty()){
				if (msg) {
					frappe.validated = false;
					frappe.confirm(msg,
						() => {
							frm.skip_brn_validation = true;
							frm.save();
						},
						() => {
							frappe.validated = false;
						}
					);
				}
			}
		}
	});
}

frappe.ui.form.on('Purchase Order', {
	onload_post_render: function(frm){
		if(frm.is_new()){
			frm.trigger("transaction_date")
		}
	},
	"transaction_date": function(frm){
		if (frm.doc.transaction_date){
			frappe.call({
				method: "p2p_customization.settlement.customization.purchase_order.api.get_fiscal_year_and_validity",
				args: {
					date: frm.doc.transaction_date,
					brn: frm.doc.brn
				},
				async: false,
				callback: function(r){
					if(r.message){
						frm.set_value("custom_fiscal_year", r.message.fiscal_year)
						frm.set_value("validity_start_date", r.message.validity_start_date)
						frm.set_value("validity_end_date", r.message.validity_end_date)
					}
				}
			})
		}
	}
});
