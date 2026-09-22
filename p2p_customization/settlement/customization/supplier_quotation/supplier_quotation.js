frappe.ui.form.on("Supplier Quotation", {
	refresh: function (frm) {
		// force_show_existing_vendor_column(frm);
		// hide_create_buttons(frm)
		(frm.doc.comparision_item || []).forEach((row) => {
			refresh_grid_row(frm, row.name);
		});

		block_amend_if_rejected(frm);

		if (!frm.doc.custom_brn && ["Selected", "Rejected"].includes(frm.doc.workflow_state)) {
			frm.add_custom_button(__("Create BRN"), () => {
				call_create_brn(frm);
			});
		}
	},
	custom_requisition_id: function (frm) {
		if (frm.doc.custom_requisition_id === "Existing Requisition") {
			frm.set_query("custom_requisition_no", () => {
				return {
					filters: {
						block_id: 0,
					},
				};
			});
		}
	},

	before_workflow_action: function (frm) {
		if (["Select", "Reject"].includes(frm.selected_workflow_action)) {
			if (!frm.doc.custom_requisition_id || !frm.doc.custom_requisition_no) {
				frappe.throw(
					__(
						"Requisition ID and Requisition No are mandatory before you can {0} this Supplier Quotation.",
						[frm.selected_workflow_action]
					)
				);
			}
		}

		// ---------- REJECT ----------
		if (frm.selected_workflow_action === "Reject") {
			const workflowAction = frm.selected_workflow_action;

			frappe.validated = false;

			frappe.dom.unfreeze();

			let d = new frappe.ui.Dialog({
				title: __("Reject Supplier Quotation"),
				fields: [
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("Reason for Rejection"),
						reqd: 1,
					},
				],
				primary_action_label: __("Reject"),
				primary_action(values) {
					d.set_df_property("reason", "read_only", 1);
					d.get_primary_btn().prop("disabled", true);

					frappe
						.call({
							method: "frappe.client.insert",
							args: {
								doc: {
									doctype: "Comment",
									comment_type: "Comment",
									reference_doctype: frm.doc.doctype,
									reference_name: frm.doc.name,
									content: values.reason,
								},
							},
						})
						.then(() => {
							return frappe.xcall("frappe.model.workflow.apply_workflow", {
								doc: frm.doc,
								action: workflowAction,
							});
						})
						.then((doc) => {
							d.hide();

							frappe.model.sync(doc);
							frm.refresh();

							frappe.show_alert({
								message: __("Supplier Quotation Rejected"),
								indicator: "red",
							});
						})
						.catch((err) => {
							d.set_df_property("reason", "read_only", 0);
							d.get_primary_btn().prop("disabled", false);
							frappe.msgprint({
								title: __("Error"),
								message: __(
									"Something went wrong while rejecting. Please check the browser console for details."
								),
								indicator: "red",
							});
							console.error("Workflow rejection failed:", err);
						});
				},
			});

			d.show();

			setTimeout(() => frappe.dom.unfreeze(), 100);

			return Promise.reject();
		}
	},
});

// ---------------------------------------------------------------------
// Calls create_brn and shows a single, consistent success message
// depending on whether a new BRN was created or an existing one updated.
// Shared by the "Select" workflow action and the "Create BRN" button.
// ---------------------------------------------------------------------
function call_create_brn(frm) {
	if (!frm.doc.custom_requisition_id || !frm.doc.custom_requisition_no.length) {
		frappe.throw(__("Please select a Requisition before selecting this Supplier Quotation."));
	}

	return frappe
		.call({
			method: "p2p_customization.settlement.doc_events.supplier_quotation.create_brn",
			args: {
				supplier_quotation: frm.doc.name,
			},
			freeze: true,
			freeze_message: __("Creating BRN..."),
		})
		.then((r) => {
			if (r.message) {
				const { name, is_new } = r.message;

				frappe.show_alert({
					message: is_new
						? __("BRN '{0}' created successfully.", [name])
						: __("BRN '{0}' updated successfully.", [name]),
					indicator: "green",
				});

				// Hide the "Create BRN" button now that this Supplier
				// Quotation is linked to a BRN.
				frm.doc.custom_brn = name;
				frm.refresh();
			}
		});
}

// ---------------------------------------------------------------------
// Block "Amend" once a Supplier Quotation has been rejected & cancelled
// ---------------------------------------------------------------------
// Assumes the workflow sets `workflow_state` to "Rejected" and the
// document is then cancelled (docstatus === 2). Adjust the field name /
// value below if your workflow uses a different state field or label.
function block_amend_if_rejected(frm) {
	const is_rejected_and_cancelled =
		frm.doc.docstatus === 2 && frm.doc.workflow_state === "Rejected";

	if (!is_rejected_and_cancelled) {
		return;
	}

	// 1. Hide the standard "Amend" button (it renders as the primary
	//    button on cancelled documents).
	if (frm.page.btn_primary) {
		frm.page.btn_primary.hide();
	}
	// Some Frappe versions also expose it as a page action / menu item.
	frm.page.remove_inner_button(__("Amend"));

	// 2. Defense in depth: if amend is still triggered some other way
	//    (keyboard shortcut, custom code, etc.), block it explicitly.
	frm.amend_doc = function () {
		frappe.throw(
			__(
				"This Supplier Quotation was rejected and cannot be amended. Please create a new Supplier Quotation instead."
			)
		);
	};

	// 3. Make the reason visible on the form so users understand why
	//    amend is unavailable, instead of just silently disappearing.
	frm.dashboard.clear_headline();
	frm.dashboard.set_headline_alert(
		__(
			"This Supplier Quotation was rejected. Amend is disabled — please create a new Supplier Quotation instead."
		),
		"red"
	);
}

function hide_create_buttons(frm) {
	if (frm.doc.docstatus !== 1) {
		return;
	}

	// remove the two standard "Create" dropdown items
	frm.page.remove_inner_button(__("Purchase Order"), __("Create"));
	frm.page.remove_inner_button(__("Quotation"), __("Create"));

	// the "Create" group toggle stays visible even when empty -
	// hide it explicitly so no dead dropdown is left behind
	frm.page.get_inner_group_button(__("Create")).hide();
}

frappe.ui.form.on("BRN Comparision", {
	is_existing_vendor: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (row.is_existing_vendor) {
			frappe.model.set_value(cdt, cdn, "is_new_vendor", 0);
			frappe.model.set_value(cdt, cdn, "new_vendor", "");
		} else {
			frappe.model.set_value(cdt, cdn, "existing_vendor", "");
		}

		refresh_grid_row(frm, cdn);
	},

	is_new_vendor: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (row.is_new_vendor) {
			frappe.model.set_value(cdt, cdn, "is_existing_vendor", 0);
			frappe.model.set_value(cdt, cdn, "existing_vendor", "");
			frappe.model.set_value(cdt, cdn, "new_vendor", "");
		}

		refresh_grid_row(frm, cdn);
	},

	existing_vendor: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (row.existing_vendor) {
			frappe.db.get_value("Supplier", row.existing_vendor, "supplier_name").then((r) => {
				if (r.message) {
					frappe.model.set_value(cdt, cdn, "new_vendor", r.message.supplier_name);
				}
			});
		}
	},
});

// Finds the grid field for the "BRN Comparision" child table on the
// parent form automatically, instead of relying on a hardcoded fieldname
function get_brn_comparision_grid_field(frm) {
	return Object.values(frm.fields_dict).find(
		(f) => f.df && f.df.fieldtype === "Table" && f.df.options === "BRN Comparision"
	);
}

// Forces the grid to re-evaluate read_only_depends_on for this row
// immediately, without requiring the user to open/edit it
function refresh_grid_row(frm, cdn) {
	const field = get_brn_comparision_grid_field(frm);

	if (!field) {
		console.error("Could not find grid field for BRN Comparision table on this form.");
		return;
	}

	const grid = field.grid;
	const grid_row = grid.grid_rows_by_docname[cdn];

	if (grid_row) {
		grid_row.refresh();
	}

	grid.refresh();
}
