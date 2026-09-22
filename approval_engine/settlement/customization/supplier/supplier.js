// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

frappe.ui.form.on("Supplier", {
	setup: function (frm) {
		frm.set_query("nature_of_service", function () {
			return {
				query: "approval_engine.settlement.api.v1.supplier.get_nature_of_service_query",
			};
		});
	},
	before_workflow_action: async function (frm) {
		const action = frm.selected_workflow_action;

		if (["Comment", "Update", "Reject", "Cancel"].includes(action)) {
			await handle_comment_or_reject(frm, action);
		} else if (action === "Approve") {
			await handle_approve_action(frm);
		}
	},
	validate: function (frm) {
		msa_agreement(frm);
	},
});

async function handle_comment_or_reject(frm, action) {
	frappe.dom.unfreeze();

	const label = action === "Reject" ? "Reason" : "Comment";

	return new Promise((resolve, reject) => {
		frappe.prompt(
			[
				{
					label: label,
					fieldname: "message",
					fieldtype: "Small Text",
					reqd: 1,
				},
			],
			(values) => {
				send_supplier_message(frm, values.message, action);
				resolve();
			},
			`Please provide ${label.toLowerCase()} for <b>${action}</b>:`,
			"Submit"
		);
	});
}

async function handle_approve_action(frm) {
	if (frm.doc.email_id) {
		send_approval_mail(frm);
	} else {
		frappe.msgprint(__("Supplier email not found"));
	}
}

function send_supplier_message(frm, message, action) {
	frappe.call({
		method: "approval_engine.settlement.api.v1.supplier.send_supplier_message",
		args: {
			supplier: frm.doc.name,
			reason: message,
			action: action,
		},
		callback: function (r) {
			if (r.data === "sent") {
				frappe.msgprint(__("Message sent to supplier successfully."));
			} else {
				frappe.msgprint(__("Supplier email not found."));
			}
		},
	});
}

function send_approval_mail(frm) {
	frappe.call({
		method: "approval_engine.settlement.api.v1.supplier.send_approval_mail",
		args: {
			supplier_name: frm.doc.supplier_name,
			email_id: frm.doc.email_id,
		},
		callback: function (r) {
			if (r.data === "sent") {
				frappe.msgprint(__("Approval mail sent to supplier successfully."));
			}
		},
	});
}

function msa_agreement(frm) {
	if (frm.doc.custom_msa_agreement === "Yes") {
		frm.set_df_property("custom_msa_agreement", "read_only", 1);
	} else {
		frm.set_df_property("custom_msa_agreement", "read_only", 0);
	}
}
