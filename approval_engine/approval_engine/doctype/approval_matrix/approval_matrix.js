// Copyright (c) 2026, 8848 Digital and contributors
// For license information, please see license.txt

frappe.ui.form.on("Approval Matrix", {
	setup(frm) {
		// Company is chosen at the top of the matrix; a row's Department must belong to it.
		// Restrict the picker so a wrong-company department can't be selected in the first place
		// (the server re-checks on save — see approval_matrix.py).
		frm.set_query("department", "detail", () => {
			// No company yet -> match nothing (the query fn runs on every keystroke, so no
			// msgprint here); the mandatory Company field already nudges the user.
			if (!frm.doc.company) {
				return { filters: { name: ["in", []] } };
			}
			return { filters: { company: frm.doc.company, is_group: 0 } };
		});
	},
	refresh(frm) {
		show_amount_field_hint(frm);
	},
	document_type(frm) {
		show_amount_field_hint(frm);
	},
	company(frm) {
		// Changing Company invalidates any row department picked for the old one. Drop the
		// stale values so they can't be carried into a submit.
		const rows = (frm.doc.detail || []).filter((row) => row.department);
		if (!rows.length) {
			return;
		}
		frappe.db
			.get_list("Department", {
				filters: { company: frm.doc.company },
				pluck: "name",
				limit: 0,
			})
			.then((valid) => {
				let cleared = 0;
				rows.forEach((row) => {
					if (!valid.includes(row.department)) {
						row.department = null;
						cleared += 1;
					}
				});
				if (cleared) {
					frm.refresh_field("detail");
					frappe.show_alert({
						message: __("Cleared {0} row department(s) that don't belong to {1}.", [
							cleared,
							frm.doc.company,
						]),
						indicator: "orange",
					});
				}
			});
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
