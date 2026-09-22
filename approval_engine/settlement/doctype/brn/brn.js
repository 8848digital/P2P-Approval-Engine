// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

frappe.ui.form.on("BRN", {
	setup: function (frm) {
		frm.set_query("item_code", "items", function () {
			let filters = { disabled: 0 };
			if (frm.doc.requisition_type === "Fixed Asset") {
				filters.is_fixed_asset = 1;
			}
			return { filters: filters };
		});
		frm.set_query("expense_gl", "items", function () {
			return {
				filters: {
					company: frm.doc.company,
					disabled: 0,
					is_group: 0,
				},
			};
		});
	},

	refresh: function (frm) {
		add_onboard_vendor_button(frm);
		create_purchase_order_button(frm);
		// frm.trigger("is_new_vendor");
		// frm.trigger("is_existing_vendor");
		frm.trigger("requisition_type");
	},

	// is_new_vendor: function(frm){
	// 	if(frm.doc.is_new_vendor){
	// 		frm.set_df_property("is_existing_vendor", "hidden", 1);
	// 		frm.set_value("existing_vendor", "");
	// 	}
	// 	else{
	// 		frm.set_df_property("is_existing_vendor", "hidden", 0);
	// 	}
	// },

	// is_existing_vendor: function(frm){
	// 	if(frm.doc.is_existing_vendor){
	// 		frm.set_df_property("is_new_vendor", "hidden", 1);
	// 		frm.set_value("new_vendor", "");
	// 	}
	// 	else{
	// 		frm.set_df_property("is_new_vendor", "hidden", 0);
	// 	}
	// },

	// existing_vendor: function(frm){
	// 	if(frm.doc.existing_vendor){
	// 		msa_agreement(frm);
	// 	}
	// },

	requisition_type: function (frm) {
		if (frm.doc.requisition_type != "Service") {
			frm.fields_dict.items.grid.toggle_reqd("qty", true);
			frm.fields_dict.items.grid.toggle_reqd("uom", true);
		} else {
			frm.fields_dict.items.grid.toggle_reqd("qty", false);
			frm.fields_dict.items.grid.toggle_reqd("uom", false);
		}
	},

	duration_of_service_months: function (frm) {
		get_expiry_date(frm);
	},

	service_start_date: function (frm) {
		get_expiry_date(frm);
	},

	multi: function (frm) {
		frm.set_value("comparision", []);
		if (frm.doc.multi) {
			add_empty_comparision_rows(frm, 3);
		}
	},

	rpt: function (frm) {
		// Triggers the multi handler above (which clears/repopulates the
		// Comparision table), since RPT drives Multi, not the other way round.
		frm.set_value("multi", frm.doc.rpt ? 1 : 0);
	},

	single: function (frm) {
		frm.set_value("comparision", []);
		if (frm.doc.single) {
			add_empty_comparision_rows(frm, 1);
		}
	},
});

function add_empty_comparision_rows(frm, count) {
	for (let i = 0; i < count; i++) {
		frm.add_child("comparision");
	}
	frm.refresh_field("comparision");
}

// function msa_agreement(frm) {
// 	frappe.db.get_value(
// 		"Supplier",
// 		frm.doc.existing_vendor,
// 		"custom_msa_agreement"
// 	).then((r) => {

// 		if (r.message.custom_msa_agreement === "Yes") {
// 			frm.set_value("msa_agreement", 1);
// 		} else {
// 			frm.set_value("msa_agreement", 0);
// 		}
// 	});
// }

frappe.ui.form.on("BRN Item", {
	qty: function (frm, cdt, cdn) {
		calculate_amount(frm, cdt, cdn);
	},
	rate: function (frm, cdt, cdn) {
		calculate_amount(frm, cdt, cdn);
	},
});

// 🔹 Add "On Board Vendor" button
function add_onboard_vendor_button(frm) {
	if (frm.doc.status == "Closed") return;

	const preferred_row = get_preferred_comparison_row(frm) || {};
	if (frm.doc.docstatus == 1 && preferred_row.is_new_vendor) {
		frm.add_custom_button(__("On Board Vendor"), function () {
			send_onboard_invitation(frm);
		});
	}
}

function get_preferred_comparison_row(frm) {
	return (frm.doc.comparision || []).find((row) => row.preferred);
}

// Preferred is only for the new-vendor onboarding flow (see
// add_onboard_vendor_button) -- it has nothing to do with which existing
// vendor a PO/Invoice gets created against, so this looks at every
// Comparision row that has an existing_vendor set, not just the
// preferred one.
function get_comparison_vendor_rows(frm) {
	return (frm.doc.comparision || []).filter((row) => row.existing_vendor);
}

function create_purchase_order_button(frm) {
	if (frm.doc.status == "Closed") return;
	if (frm.doc.docstatus != 1) return;

	const vendor_rows = get_comparison_vendor_rows(frm);
	if (!vendor_rows.length) return;

	let button_added = false;

	if (frm.doc.po_type == "PO Based") {
		frm.add_custom_button(
			__("Purchase Order"),
			function () {
				pick_vendor_and_create(vendor_rows, (vendor) =>
					create_purchase_order(frm, vendor)
				);
			},
			__("Create")
		);
		button_added = true;
	}

	if (frm.doc.po_type == "YEXP Proposal") {
		frm.add_custom_button(
			__("Purchase Invoice"),
			function () {
				pick_vendor_and_create(vendor_rows, (vendor) =>
					create_purchase_invoice(frm, vendor)
				);
			},
			__("Create")
		);
		button_added = true;
	}

	if (button_added) {
		frm.page.set_inner_btn_group_as_primary(__("Create"));
	}
}

// One candidate vendor -> create against it directly. Two or three ->
// ask which one instead of guessing.
function pick_vendor_and_create(vendor_rows, on_vendor_chosen) {
	if (vendor_rows.length === 1) {
		on_vendor_chosen(vendor_rows[0].existing_vendor);
		return;
	}

	const option_map = {};
	const options = vendor_rows.map((row) => {
		const label = `${row.vendor_name || row.existing_vendor} (${row.existing_vendor})`;
		option_map[label] = row.existing_vendor;
		return label;
	});

	const dialog = new frappe.ui.Dialog({
		title: __("Select Vendor"),
		fields: [
			{
				fieldname: "vendor_label",
				fieldtype: "Select",
				label: __("Vendor"),
				reqd: 1,
				options: options,
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			dialog.hide();
			on_vendor_chosen(option_map[values.vendor_label]);
		},
	});
	dialog.show();
}

function send_onboard_invitation(frm) {
	const preferred_row = get_preferred_comparison_row(frm) || {};
	approval_engine.vendor.send_vendor_invitation_mail(
		frm.doc.doctype,
		frm.doc.name,
		preferred_row.email_id || null,
		preferred_row.vendor_name || null,
		frm.doc.company || null
	);
}

// 🔹 Calculate item amount
function calculate_amount(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	row.amount = (row.qty || 0) * (row.rate || 0);
	frm.refresh_field("items");
}

// 🔹 Create Purchase Order from BRN
function create_purchase_order(frm, vendor) {
	frappe.model.open_mapped_doc({
		method: "approval_engine.settlement.api.v1.brn.create_purchase_order_from_brn",
		frm: frm,
		args: { vendor: vendor },
		run_link_triggers: true,
	});
}

// 🔹 Create Purchase Invoice from BRN
function create_purchase_invoice(frm, vendor) {
	frappe.model.open_mapped_doc({
		method: "approval_engine.settlement.api.v1.brn.create_purchase_invoice_from_brn",
		frm: frm,
		args: { vendor: vendor },
		run_link_triggers: true,
	});
}

// duration_of_service_months and service_start_date both trigger a recompute,
// and the date picker widget can itself fire more than one change event per
// user interaction (e.g. an intermediate/incomplete value while typing a
// date manually). Without debouncing, an earlier trigger's async response --
// or its synchronous "clear expiry_date" fallback below, when a field was
// momentarily empty mid-interaction -- can land AFTER a later, correct one
// and stomp it. Debounce so only the final state within a short window
// actually runs, always reading frm.doc fresh at that point.
let _expiry_date_debounce_timer = null;

function get_expiry_date(frm) {
	clearTimeout(_expiry_date_debounce_timer);
	_expiry_date_debounce_timer = setTimeout(() => recompute_expiry_date(frm), 400);
}

function recompute_expiry_date(frm) {
	if (!frm.doc.duration_of_service_months || !frm.doc.service_start_date) {
		frm.set_value("expiry_date", "");
		return;
	}

	frappe.call({
		method: "approval_engine.settlement.api.v1.brn.get_expiry_date",
		args: {
			date: frm.doc.service_start_date,
			months: frm.doc.duration_of_service_months,
		},
		callback: function (r) {
			// approval_engine's after_request hook replaces the entire response
			// body with its envelope -- for an endpoint that just returns a raw
			// value (not api_response(...)), that envelope IS what frappe.call's
			// callback receives as `r` (Frappe's own {"message": ...} wrapper
			// gets consumed and replaced, not nested inside). The payload is
			// r.data directly; r.message is the envelope's own human-readable
			// string, not the payload.
			const expiry_date = r?.data;
			if (expiry_date) {
				frm.set_value("expiry_date", expiry_date);
			}
		},
	});
}

frappe.ui.form.on("BRN Comparision", {
	pan(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (!row.pan) {
			return;
		}

		frappe.db.get_value("Supplier", { pan: row.pan }, "name").then((r) => {
			const supplier = r.message?.name;

			if (supplier) {
				frappe.model.set_value(cdt, cdn, "is_existing_vendor", 1);
				frappe.model.set_value(cdt, cdn, "is_new_vendor", 0);
				frappe.model.set_value(cdt, cdn, "existing_vendor", supplier);
			} else {
				frappe.model.set_value(cdt, cdn, "is_new_vendor", 1);
				frappe.model.set_value(cdt, cdn, "is_existing_vendor", 0);
			}
		});
	},

	existing_vendor(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (!row.existing_vendor) {
			frappe.model.set_value(cdt, cdn, "msa_agreement", 0);
			return;
		}

		frappe.db.get_value("Supplier", row.existing_vendor, "custom_msa_agreement").then((r) => {
			const value = r.message?.custom_msa_agreement;

			frappe.model.set_value(cdt, cdn, "msa_agreement", value === "Yes" ? 1 : 0);
		});
	},
});
