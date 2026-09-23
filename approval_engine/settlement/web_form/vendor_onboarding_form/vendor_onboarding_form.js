// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

frappe.ready(function () {
	frappe.web_form.set_value("is_created_from_webform", 1);
	const urlParams = new URLSearchParams(window.location.search);
	const email = urlParams.get("email_id");
	const reference_docname = urlParams.get("reference_docname");
	if (reference_docname) {
		frappe.web_form.set_value("brn", reference_docname);
	}

	if (email) {
		// Always read-only on this form now (set on the Web Form field
		// itself), regardless of whether it arrived via a valid invite
		// link -- no need to toggle it dynamically here any more, just
		// decode and populate it when it did.
		frappe.call({
			method: "approval_engine.settlement.api.v1.vendor_email.decode_email",
			args: { encoded_email: email },
			callback: function (r) {
				frappe.web_form.set_value("email_id", r.data);
			},
		});
	}
	get_supplier_workflow_state();
});

function get_supplier_workflow_state() {
	let pathParts = window.location.pathname.split("/").filter(Boolean);

	let isEdit = pathParts[pathParts.length - 1] === "edit";
	let supplier = isEdit ? pathParts[pathParts.length - 2] : pathParts[pathParts.length - 1];

	if (supplier && supplier !== "new") {
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Supplier",
				filters: { name: supplier },
				fieldname: "workflow_state",
			},
			callback: function (r) {
				if (r && r.message) {
					let editBtn = document.querySelector(".web-form-actions .edit-button");

					if (r.message.workflow_state !== "Approved") {
						if (editBtn) {
							editBtn.style.display = "inline-block";
						}
					} else {
						if (editBtn) {
							editBtn.style.display = "inline-block";
						}

						if (isEdit) {
							lock_fields_dynamically();
						}
					}
				}
			},
		});
	}
}

function lock_fields_dynamically() {
	const ALWAYS_EDITABLE_FIELDS = ["custom_msa_agreement", "custom_msa_agreement_attachment"];
	const LAYOUT_FIELDTYPES = ["Section Break", "Column Break", "Page Break", "HTML", "Heading"];

	frappe.web_form.fields.forEach(function (field) {
		if (!field.fieldname) return;
		if (LAYOUT_FIELDTYPES.includes(field.fieldtype)) return;
		if (ALWAYS_EDITABLE_FIELDS.includes(field.fieldname)) return;

		frappe.web_form.set_df_property(field.fieldname, "read_only", 1);
	});
}
