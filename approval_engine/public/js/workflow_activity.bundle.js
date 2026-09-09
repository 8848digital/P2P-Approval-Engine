// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

// Renders a "Workflow Activity" section in the form sidebar of any document
// governed by an engine-generated approval workflow. The approver chain and its
// live status come from
// approval_engine.approval_core.api.v1.activity.get_workflow_activity.

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
			const meta = approval_engine.WF_STATUS[step.status] || approval_engine.WF_STATUS.upcoming;
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
			if (step.acted_by) {
				const actor = esc(step.acted_by.full_name || step.acted_by.user);
				acted_line = `<div>${__("Acted by")}: <b>${actor}</b></div>`;
				if (step.time) {
					time_line = `<div class="text-muted small">${frappe.datetime.str_to_user(step.time)}</div>`;
				}
			}

			return `
				<div class="wf-activity-step">
					<div>${__("Owner")}: <b>${owners || "&mdash;"}</b></div>
					${status_line}
					${acted_line}
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

// Register the sidebar renderer on every target DocType that has an active workflow.
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
				});
			});
		},
	});
});
