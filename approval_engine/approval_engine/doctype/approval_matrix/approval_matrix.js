// Copyright (c) 2026, 8848 Digital and contributors
// For license information, please see license.txt

frappe.ui.form.on("Approval Matrix", {
	refresh(frm) {
		show_amount_field_hint(frm);
	},
	document_type(frm) {
		show_amount_field_hint(frm);
	},
});

// Surface WHICH amount field the bands will compare against, before the matrix is submitted
// (it is baked into the generated workflow conditions at submit time). Resolved from Approval
// Settings, falling back to a per-DocType default.
function show_amount_field_hint(frm) {
	frm.set_intro("");
	if (!frm.doc.document_type) {
		return;
	}
	frappe.call({
		method: "approval_engine.generator.get_amount_field_info",
		args: { document_type: frm.doc.document_type },
		callback: (r) => {
			const info = r.message;
			if (!info || !info.amount_field) {
				return;
			}
			const dt = frappe.utils.escape_html(frm.doc.document_type);
			const field = `<b>${frappe.utils.escape_html(info.amount_field)}</b>`;
			if (!info.exists) {
				frm.set_intro(
					__("Amount field {0} does not exist on {1}. Set the correct field in Approval Settings before submitting — the bands need it.", [field, dt]),
					"red"
				);
			} else {
				const src = info.is_explicit
					? __("configured in Approval Settings")
					: __("default — change in Approval Settings if needed");
				frm.set_intro(
					__("Amount bands for {0} compare against {1} ({2}).", [dt, field, src]),
					info.is_explicit ? "blue" : "orange"
				);
			}
		},
	});
}
