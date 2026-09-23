// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

// Renders a "Workflow Activity" section in the form sidebar of any document
// governed by an engine-generated approval workflow. The approver chain and its
// live status come from
// approval_engine.approval_core.api.v1.activity.get_workflow_activity.
//
// Also prompts for approver remarks on every workflow action (mandatory for
// Reject) before Frappe's standard apply_workflow runs — see approval_core/remarks.py.

frappe.provide("approval_engine");

approval_engine.WF_STATUS = {
	approved: { label: __("Approved"), cls: "text-success" },
	pending: { label: __("Pending"), cls: "text-warning" },
	on_hold: { label: __("On Hold"), cls: "text-warning" },
	rejected: { label: __("Rejected"), cls: "text-danger" },
	upcoming: { label: "", cls: "text-muted" },
};

approval_engine.render_workflow_activity = function (frm) {
	const sidebar = frm.$wrapper.find(".form-sidebar");
	const remove = () => sidebar.find(".workflow-activity-section").remove();

	if (frm.is_new() || !sidebar.length) {
		remove();
		return;
	}

	// The endpoint responds in the 8848 envelope (via the after_request hook),
	// so the payload is under r.data — use frappe.call (not xcall, which would
	// resolve to the envelope's `message` string).
	frappe.call({
		method: "approval_engine.approval_core.api.v1.activity.get_workflow_activity",
		args: { doctype: frm.doctype, name: frm.docname },
		callback: (r) => {
			remove();
			const data = r && r.data;
			if (!data || !data.managed || !(data.steps || []).length) {
				return;
			}
			sidebar.append(approval_engine.build_activity_html(data.steps));
		},
		error: () => remove(),
	});
};

approval_engine.build_activity_html = function (steps) {
	const esc = frappe.utils.escape_html;
	const rows = steps
		.map((step) => {
			const meta =
				approval_engine.WF_STATUS[step.status] || approval_engine.WF_STATUS.upcoming;
			const owners = (step.owner || [])
				.filter(Boolean)
				.map((o) => esc(o.full_name || o.user))
				.join(", ");

			const status_line = meta.label
				? `<div>${__("Status")}: <span class="${meta.cls}">${meta.label}</span></div>`
				: `<div>${__("Status")}: <span class="text-muted">&mdash;</span></div>`;

			// Who actually performed the transition (approve/hold/reject), separate
			// from the fixed owner list. Only shown once a tier has been acted on.
			let acted_line = "";
			let time_line = "";
			let remarks_line = "";
			if (step.acted_by) {
				const actor = esc(step.acted_by.full_name || step.acted_by.user);
				const channel = step.via_email_link
					? ` <span class="text-muted small">(${__("via email")})</span>`
					: "";
				acted_line = `<div>${__("Acted by")}: <b>${actor}</b>${channel}</div>`;
				if (step.time) {
					time_line = `<div class="text-muted small">${frappe.datetime.str_to_user(
						step.time
					)}</div>`;
				}
				if (step.remarks) {
					remarks_line = `<div class="wf-activity-remarks">${__("Remarks")}: ${esc(
						step.remarks
					)}</div>`;
				}
			}

			return `
				<div class="wf-activity-step">
					<div>${__("Owner")}: <b>${owners || "&mdash;"}</b></div>
					${status_line}
					${acted_line}
					${remarks_line}
					${time_line}
				</div>`;
		})
		.join("");

	return `
		<div class="workflow-activity-section sidebar-section">
			<div class="sidebar-label">${__("Workflow Activity")}</div>
			<div class="wf-activity-list">${rows}</div>
		</div>`;
};

/**
 * Ask for the approver's remarks before Frappe applies the selected workflow action,
 * and stash them server-side so the transition log records them. Remarks are
 * mandatory for Reject (also enforced on the server). Closing the dialog cancels
 * the action: the returned promise rejects, so apply_workflow never runs.
 *
 * @param {object} frm - The form whose workflow action button was clicked.
 * @returns {Promise<void>} Resolves once remarks are stashed; rejects on cancel.
 */
approval_engine.prompt_workflow_remarks = function (frm) {
	const action = frm.selected_workflow_action;
	const is_reject = action === "Reject";

	// Frappe freezes the page before this hook runs; a frozen page blocks the dialog.
	frappe.dom.unfreeze();

	return new Promise((resolve, reject) => {
		let submitted = false;
		const dialog = new frappe.ui.Dialog({
			title: __("{0}: {1}", [__(action), frm.docname]),
			fields: [
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: is_reject ? __("Reason for Rejection") : __("Remarks (optional)"),
					reqd: is_reject ? 1 : 0,
				},
			],
			primary_action_label: __(action),
			primary_action(values) {
				approval_engine.stash_workflow_remarks(frm, action, values.remarks).then(() => {
					submitted = true;
					dialog.hide();
					// Re-freeze so Frappe's own unfreeze after apply_workflow stays balanced.
					frappe.dom.freeze();
					resolve();
				});
			},
		});
		dialog.onhide = () => {
			if (!submitted) {
				reject(new Error(__("Workflow action cancelled")));
			}
		};
		dialog.show();
	});
};

/**
 * Save the remarks for the action about to be applied (api/v1/workflow.stash_remarks).
 *
 * @param {object} frm - The form being actioned.
 * @param {string} action - Workflow action name (Approve / Hold / Reject).
 * @param {string} remarks - Approver's remarks; may be empty for Approve / Hold.
 * @returns {Promise<object>} Resolves with the server response.
 */
approval_engine.stash_workflow_remarks = function (frm, action, remarks) {
	return frappe.call({
		method: "approval_engine.approval_core.api.v1.workflow.stash_remarks",
		args: { doctype: frm.doctype, name: frm.docname, action: action, remarks: remarks || "" },
		freeze: true,
	});
};

// Register the sidebar renderer and the remarks prompt on every target DocType that
// has an active workflow.
$(document).on("app_ready", function () {
	frappe.call({
		method: "approval_engine.approval_core.api.v1.activity.get_managed_doctypes",
		callback: (r) => {
			const doctypes = (r && r.data) || [];
			doctypes.forEach((dt) => {
				frappe.ui.form.on(dt, {
					refresh(frm) {
						approval_engine.render_workflow_activity(frm);
					},
					before_workflow_action(frm) {
						return approval_engine.prompt_workflow_remarks(frm);
					},
				});
			});
		},
	});
});
