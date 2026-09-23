// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

frappe.provide("approval_engine.dashboard");

approval_engine.dashboard.CHART_TYPE_MAP = {
	Pie: "pie",
	Donut: "donut",
	Bar: "bar",
	Line: "line",
	Percentage: "percentage",
};

approval_engine.dashboard.COLOR_MAP = {
	Approved: "#28a745",
	Processed: "#28a745",
	Rejected: "#dc3545",
	Failed: "#dc3545",
	Pending: "#ffc107",
};

// 5th color is only used by MSME Ageing's "Overdue" bucket (worse than
// the 31-45 Days bucket, hence a darker red than #dc3545).
approval_engine.dashboard.BUCKET_COLORS = ["#28a745", "#ffc107", "#fd7e14", "#dc3545", "#8b0000"];

approval_engine.dashboard.SECTIONS = [
	{ key: "brn", container: "chart-brn", title: __("BRN Approval Status") },
	{
		key: "payment_order",
		container: "chart-payment-order",
		title: __("Payment Release Status"),
	},
	{
		key: "purchase_order",
		container: "chart-purchase-order",
		title: __("Purchase Order Approval Status"),
	},
	{ key: "msme", container: "chart-msme", title: __("MSME Payment Ageing"), is_bucket: true },
	{
		key: "purchase_invoice",
		container: "chart-purchase-invoice",
		title: __("Purchase Invoice Approval Status"),
	},
	{
		key: "related_party",
		container: "chart-related-party",
		title: __("Related Party Transaction Status"),
		// Card is always in the DOM (built once from this static list
		// before any data exists) and toggled by on_data() based on the
		// payload's enable_related_party_chart flag -- see on_data.
		togglable: true,
	},
];

// frappe-charts does NOT set a `data-point-index` DOM attribute on every
// chart type -- it's only present on Bar/Line elements (rects/circles).
// Pie charts instead fire a bubbling native "data-select" event on the
// chart's container element (see frappe-charts BaseChart/AggregationChart/
// PieChart -- setCurrentDataPoint() -> fire(this.parent, "data-select", ...)),
// and Bar/Line charts (AxisChart) fire the same event. That makes
// "data-select" the one click hook that's common to every chart type this
// dashboard can render *except* Donut and Percentage, which frappe-charts
// does not wire up for click-to-select at all (Donut only binds
// mousemove/mouseleave for its tooltip; Percentage has no click handling
// either). This is a limitation of the frappe-charts library itself, not
// something this controller can fix without patching that library.
const CHART_TYPES_WITHOUT_CLICK_SUPPORT = new Set(["donut", "percentage"]);

const API_MODULE = "approval_engine.approval_settlement.api.v1.procure_to_pay";

class PaymentsComplianceDashboard {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.charts = {};
		this.refresh_timer = null;

		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Payments Compliance Dashboard"),
			single_column: true,
		});

		this.check_access_and_init();
	}

	check_access_and_init() {
		frappe.call({
			method: `${API_MODULE}.check_access`,
			callback: () => this.init(),
			error: () => this.render_access_denied(),
		});
	}

	render_access_denied() {
		this.page.body.html(`
			<div class="text-muted text-center" style="padding: 60px 0;">
				<h4>${__("You don't have permission to view this dashboard.")}</h4>
				<p>${__("Contact your administrator if you believe this is a mistake.")}</p>
			</div>
		`);
	}

	init() {
		this.setup_filters();
		this.setup_menu();
		this.setup_layout();
		this.render_placeholder();
	}

	setup_filters() {
		this.company_field = this.page.add_field({
			fieldtype: "Link",
			fieldname: "company",
			label: __("Company"),
			options: "Company",
			reqd: 1,
			change: () => this.on_filter_change(),
		});

		this.from_date_field = this.page.add_field({
			fieldtype: "Date",
			fieldname: "from_date",
			label: __("From Date"),
			reqd: 1,
			change: () => this.on_filter_change(),
		});

		this.to_date_field = this.page.add_field({
			fieldtype: "Date",
			fieldname: "to_date",
			label: __("To Date"),
			reqd: 1,
			change: () => this.on_filter_change(),
		});

		this.restore_filters_from_url();
	}

	// Filters survive a hard reload (F5) or a bookmarked/shared link by
	// living in the URL's query string, not just in-memory field state --
	// frappe.utils.get_url_arg reads window.location.search directly, so
	// this works regardless of how the page was navigated to. Whatever
	// isn't in the URL (e.g. a fresh visit / post-login landing) falls
	// back to a sensible default instead of sitting blank.
	restore_filters_from_url() {
		const company = frappe.utils.get_url_arg("company") || this.get_default_company();

		const to_date = frappe.utils.get_url_arg("to_date") || frappe.datetime.get_today();
		const from_date =
			frappe.utils.get_url_arg("from_date") || frappe.datetime.add_months(to_date, -1);

		if (company) this.company_field.set_value(company);
		if (from_date) this.from_date_field.set_value(from_date);
		if (to_date) this.to_date_field.set_value(to_date);
	}

	// Prefers the logged-in user's actual Company access (User Permission
	// restricting the Company doctype) over the generic system/user
	// default -- a plain default company can point at a company this user
	// has no permission to see. If they're restricted to one or more
	// companies, use the one marked default there, or else the first one
	// in that list. Only when there's NO such restriction (full access to
	// every company) do we fall back to the ordinary default company.
	get_default_company() {
		const company_permissions = frappe.defaults.get_user_permissions()["Company"];
		if (company_permissions && company_permissions.length) {
			const default_row = company_permissions.find((p) => p.is_default);
			return (default_row || company_permissions[0]).doc;
		}
		return frappe.defaults.get_default("company");
	}

	// Mirrors the current filter values into the URL query string via
	// replaceState -- doesn't push a new browser history entry per
	// keystroke/change, just keeps the visible URL (and a reload of it)
	// in sync with what's on screen.
	sync_url_with_filters() {
		const params = {
			company: this.company_field.get_value(),
			from_date: this.from_date_field.get_value(),
			to_date: this.to_date_field.get_value(),
		};
		const query_string = frappe.utils.make_query_string(params);
		const new_url = window.location.pathname + (query_string === "?" ? "" : query_string);
		window.history.replaceState(null, "", new_url);
	}

	// --- Filter validation ---------------------------------------------
	// Company, From Date and To Date are ALL mandatory now. Nothing is
	// fetched/rendered until every one of them has a value.
	get_missing_filters() {
		const missing = [];
		if (!this.company_field.get_value()) missing.push(__("Company"));
		if (!this.from_date_field.get_value()) missing.push(__("From Date"));
		if (!this.to_date_field.get_value()) missing.push(__("To Date"));
		return missing;
	}

	filters_are_valid() {
		const missing = this.get_missing_filters();
		if (missing.length) return false;

		const from_date = this.from_date_field.get_value();
		const to_date = this.to_date_field.get_value();
		if (frappe.datetime.get_diff(to_date, from_date) < 0) {
			frappe.show_alert({
				message: __("'To Date' cannot be before 'From Date'."),
				indicator: "red",
			});
			return false;
		}
		return true;
	}

	on_filter_change() {
		this.sync_url_with_filters();
		if (this.filters_are_valid()) {
			this.render_all();
		} else {
			this.render_placeholder();
		}
	}

	setup_menu() {
		this.page.set_primary_action(
			__("Refresh"),
			() => {
				if (!this.filters_are_valid()) {
					const missing = this.get_missing_filters();
					if (missing.length) {
						frappe.show_alert({
							message: __("Please set {0} before refreshing.", [missing.join(", ")]),
							indicator: "orange",
						});
					}
					this.render_placeholder();
					return;
				}
				// Full refresh: tear down existing chart instances so every
				// section is rebuilt from scratch instead of patched in place.
				this.destroy_all_charts();
				this.render_all();
			},
			"refresh-cw"
		);

		if (frappe.user_roles.includes("System Manager")) {
			this.page.add_menu_item(__("Dashboard Settings"), () => {
				frappe.set_route("Form", "Payments Compliance Settings");
			});
			this.page.add_menu_item(__("Debug Raw Counts"), () => this.show_debug_dialog());
		}
	}

	setup_layout() {
		const fullname = frappe.session.user_fullname || frappe.session.user;
		this.$user_banner = $(`
			<div class="pc-user-banner">
				${frappe.avatar(frappe.session.user, "avatar-medium")}
				<div class="pc-user-banner-text">
					<div class="pc-user-banner-name">${frappe.utils.escape_html(fullname)}</div>
					<div class="pc-user-banner-hint">${__(
						"Showing items you created or that are pending your approval"
					)}</div>
				</div>
			</div>
		`).appendTo(this.page.body);

		const cards_html = approval_engine.dashboard.SECTIONS.map(
			(s) => `
				<div class="chart-card ${s.full_width ? "full-width" : ""}">
					<h5>${s.title}</h5>
					<div id="${s.container}"></div>
					<div id="${s.container}-legend" class="pc-chart-legend"></div>
				</div>`
		).join("");

		this.$layout = $(
			`<div class="pc-dashboard"><div class="pc-grid">${cards_html}</div></div>`
		).appendTo(this.page.body);

		$("<style>")
			.text(
				`
			.pc-user-banner {
				display: flex; align-items: center; gap: 10px;
				margin-top: 12px; padding: 10px 14px;
				background: var(--card-bg, #fff);
				border: 1px solid var(--border-color, #d1d8dd);
				border-radius: 10px;
			}
			.pc-user-banner-name { font-weight: 600; color: var(--text-color, #1f272e); line-height: 1.3; }
			.pc-user-banner-hint { font-size: 12px; color: var(--text-muted, #8d99a6); line-height: 1.3; }
			.pc-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-top: 12px; }
			.pc-dashboard .chart-card {
				background: var(--card-bg, #fff);
				border: 1px solid var(--border-color, #d1d8dd);
				border-radius: 10px;
				padding: 16px 18px 8px;
				box-shadow: 0 1px 3px rgba(0,0,0,0.04);
			}
			.pc-dashboard .chart-card h5 { margin: 0 0 10px; font-weight: 600; color: var(--text-color, #1f272e); }
			.pc-dashboard .full-width { grid-column: 1 / -1; }
			@media (max-width: 900px) { .pc-grid { grid-template-columns: 1fr; } }
			.pc-dashboard .chart-card svg [data-point-index] { transition: opacity 0.15s; cursor: pointer; }
			.pc-dashboard .chart-card svg [data-point-index]:hover { opacity: 0.75; }
			.pc-dashboard .chart-card.pc-clickable svg .slice,
			.pc-dashboard .chart-card.pc-clickable svg .pie-arc,
			.pc-dashboard .chart-card.pc-clickable svg path { cursor: pointer; }
			.pc-chart-legend { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 8px; }
			.pc-chart-legend .pc-legend-item {
				display: inline-flex; align-items: center; gap: 6px;
				padding: 3px 10px 3px 8px; border-radius: 999px; cursor: pointer;
				background: var(--bg-color, #f4f5f6); border: 1px solid var(--border-color, #d1d8dd);
				font-size: 12px; color: var(--text-color, #1f272e); transition: background 0.12s, box-shadow 0.12s;
			}
			.pc-chart-legend .pc-legend-item:hover,
			.pc-chart-legend .pc-legend-item:focus-visible {
				background: var(--fg-hover-color, #eaecee); box-shadow: 0 0 0 1px var(--primary, #2490ef) inset;
				outline: none;
			}
			.pc-chart-legend .pc-legend-item.pc-legend-empty { cursor: default; opacity: 0.55; }
			.pc-chart-legend .pc-legend-item.pc-legend-empty:hover { background: var(--bg-color, #f4f5f6); box-shadow: none; }
			.pc-chart-legend .pc-legend-swatch { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
			.pc-chart-legend .pc-legend-count { font-weight: 600; }
			.pc-debug-tabs { display: flex; gap: 6px; margin-bottom: 10px; border-bottom: 1px solid var(--border-color, #d1d8dd); }
			.pc-debug-tabs .pc-tab-btn {
				border: none; background: none; padding: 6px 12px; cursor: pointer;
				border-bottom: 2px solid transparent; font-weight: 500; color: var(--text-muted, #8d99a6);
			}
			.pc-debug-tabs .pc-tab-btn.active { color: var(--text-color, #1f272e); border-bottom-color: var(--primary, #2490ef); }
			.pc-debug-pane { display: none; }
			.pc-debug-pane.active { display: block; }
			.pc-log-summary { cursor: pointer; }
			.pc-log-full { display: none; white-space: pre-wrap; font-size: 11px; max-height: 260px; overflow: auto; background: #1f272e; color: #f5f5f5; padding: 8px; border-radius: 4px; margin-top: 4px; }
			.pc-debug-scroll { max-height: 420px; overflow: auto; }
			.pc-badge-mapping { background: #d1e7dd; color: #0f5132; padding: 1px 6px; border-radius: 4px; font-size: 11px; }
			.pc-badge-fallback { background: #fff3cd; color: #664d03; padding: 1px 6px; border-radius: 4px; font-size: 11px; }
			.pc-badge-docstatus { background: #e2e3e5; color: #41464b; padding: 1px 6px; border-radius: 4px; font-size: 11px; }
		`
			)
			.appendTo(this.$layout);

		this.$placeholder = $(`
			<div class="text-muted text-center" style="padding: 60px 0;">
				<h4>${__("Select Filters")}</h4>
				<p>${__(
					"Choose a Company, From Date and To Date above to load the compliance dashboard. All three are required."
				)}</p>
			</div>
		`).appendTo(this.page.body);
	}

	render_placeholder() {
		if (this.refresh_timer) clearInterval(this.refresh_timer);
		this.$layout.hide();
		this.$placeholder.show();
	}

	colors_for(labels, is_bucket) {
		if (is_bucket) return approval_engine.dashboard.BUCKET_COLORS.slice(0, labels.length);
		return labels.map((l) => approval_engine.dashboard.COLOR_MAP[l] || "#007bff");
	}

	// Always tear down and rebuild rather than calling chart.update().
	// frappe.Chart.update() can leave stale labels/colors/bars behind when
	// the underlying label set or chart type changes between calls (e.g.
	// after switching Company/date range, or a workflow state appearing/
	// disappearing) -- rebuilding guarantees what's on screen always
	// matches the data just fetched.
	//
	// doctype + bucket_filters come from the server (see get_dashboard_data)
	// because only the server knows, per bucket, whether it was built from
	// workflow_state values or a plain docstatus -- the frontend can't
	// reconstruct that filter on its own.
	render_chart(container_id, labels, values, chart_type, is_bucket, doctype, bucket_filters) {
		const data = { labels, datasets: [{ values }] };
		const type = approval_engine.dashboard.CHART_TYPE_MAP[chart_type] || "bar";
		const colors = this.colors_for(labels, is_bucket);

		this.destroy_chart(container_id);

		this.charts[container_id] = new frappe.Chart(`#${container_id}`, {
			data,
			type,
			height: 220,
			colors,
		});

		const $card = $(`#${container_id}`).closest(".chart-card");
		$card.toggleClass("pc-clickable", !CHART_TYPES_WITHOUT_CLICK_SUPPORT.has(type));

		const open = (label) => {
			const idx = labels.indexOf(label);
			if (idx === -1) return;
			this.open_bucket_list(doctype, label, values[idx], (bucket_filters || {})[label]);
		};

		// Click-through to the underlying list -- direct-on-chart path.
		//
		// frappe-charts fires a bubbling native "data-select" event on the
		// chart's own container element whenever a data point is clicked --
		// this is the one hook that works for Bar, Line AND Pie charts alike
		// (unlike the `[data-point-index]` attribute below, which
		// frappe-charts only ever sets on Bar/Line elements, so it silently
		// never fired for Pie -- the previous implementation used that
		// selector and so pie charts never opened a filtered list).
		// Donut and Percentage charts don't support click-to-select in
		// frappe-charts at all (no equivalent event is fired), so clicking
		// directly on those two never does anything here -- see
		// CHART_TYPES_WITHOUT_CLICK_SUPPORT above and render_legend() below,
		// which covers those two (and gives every chart type a second,
		// always-reliable click target).
		$(`#${container_id}`)
			.off("data-select")
			.on("data-select", (e) => open((e.originalEvent || e).label));

		// Kept as a fallback for any chart type/version of frappe-charts
		// that *does* set `data-point-index` (older Bar/Line renders did,
		// and some custom builds still do) so clicking still works there
		// even if "data-select" isn't fired for some reason.
		$(`#${container_id}`)
			.off("click", "[data-point-index]")
			.on("click", "[data-point-index]", (e) =>
				open(labels[$(e.currentTarget).attr("data-point-index")])
			);

		this.render_legend(container_id, labels, values, colors, open);
	}

	// Chart-type-agnostic click target. frappe-charts only exposes a click
	// hook (the "data-select" event used above) for Bar, Line and Pie --
	// Donut and Percentage charts never fire anything on click, and there's
	// no supported way to hook into their SVG hit-testing from outside the
	// library. Rendering our own small legend row of plain HTML buttons
	// underneath every chart sidesteps that entirely: it doesn't depend on
	// frappe-charts' internals or chart type, so "click a bucket -> open the
	// filtered list" works identically for all five chart types.
	render_legend(container_id, labels, values, colors, open) {
		const $legend = $(`#${container_id}-legend`);
		const rows = labels
			.map((label, idx) => {
				const count = values[idx] || 0;
				const empty = count === 0;
				return `
					<span
						class="pc-legend-item ${empty ? "pc-legend-empty" : ""}"
						data-label="${frappe.utils.escape_html(label)}"
						${empty ? "" : 'tabindex="0" role="button"'}
					>
						<span class="pc-legend-swatch" style="background:${colors[idx] || "#007bff"}"></span>
						${frappe.utils.escape_html(String(label))}
						<span class="pc-legend-count">${count}</span>
					</span>`;
			})
			.join("");

		$legend.html(rows);
		$legend
			.off("click", ".pc-legend-item")
			.on("click", ".pc-legend-item", (e) => open($(e.currentTarget).attr("data-label")))
			.off("keydown", ".pc-legend-item")
			.on("keydown", ".pc-legend-item", (e) => {
				if (e.key === "Enter" || e.key === " ") {
					e.preventDefault();
					open($(e.currentTarget).attr("data-label"));
				}
			});
	}

	open_bucket_list(doctype, label, count, filters) {
		if (!doctype) return;
		if (!count) {
			frappe.show_alert({ message: __("No records in {0}.", [label]), indicator: "orange" });
			return;
		}
		frappe.route_options = filters || {};
		frappe.set_route("List", doctype);
	}

	destroy_chart(container_id) {
		if (this.charts[container_id]) {
			delete this.charts[container_id];
		}
		$(`#${container_id}`).off("data-select").off("click", "[data-point-index]");
		$(`#${container_id}`).empty();
		$(`#${container_id}-legend`)
			.off("click", ".pc-legend-item")
			.off("keydown", ".pc-legend-item");
		$(`#${container_id}-legend`).empty();
	}

	destroy_all_charts() {
		Object.keys(this.charts).forEach((id) => this.destroy_chart(id));
	}

	render_all() {
		if (!this.filters_are_valid()) {
			this.render_placeholder();
			return;
		}

		const args = {
			company: this.company_field.get_value(),
			from_date: this.from_date_field.get_value(),
			to_date: this.to_date_field.get_value(),
		};

		frappe.call({
			method: `${API_MODULE}.get_dashboard_data`,
			args,
			freeze: true,
			callback: (r) => this.on_data(r.message),
			error: (r) => {
				console.error("Payments Compliance Dashboard: failed to load data", r);
				frappe.msgprint({
					title: __("Couldn't load dashboard data"),
					indicator: "red",
					message:
						(r && r.exc) || __("Check the browser console and Error Log for details."),
				});
			},
		});
	}

	on_data(d) {
		if (!d) return;
		this.$placeholder.hide();
		this.$layout.show();

		const chart_types = d.chart_types || {};

		approval_engine.dashboard.SECTIONS.forEach((s) => {
			if (s.togglable) {
				const enabled = s.key === "related_party" ? d.enable_related_party_chart : true;
				$(`#${s.container}`).closest(".chart-card").toggle(!!enabled);
				if (!enabled) return;
			}
			const section = d[s.key] || { counts: {}, bucket_filters: {}, doctype: null };
			this.render_chart(
				s.container,
				Object.keys(section.counts),
				Object.values(section.counts),
				chart_types[s.key],
				s.is_bucket,
				section.doctype,
				section.bucket_filters || {}
			);
		});

		this.setup_auto_refresh(d.auto_refresh_seconds);
	}

	setup_auto_refresh(seconds) {
		if (this.refresh_timer) clearInterval(this.refresh_timer);
		if (seconds > 0) {
			this.refresh_timer = setInterval(() => {
				if (!this.filters_are_valid()) {
					clearInterval(this.refresh_timer);
					return;
				}
				this.destroy_all_charts();
				this.render_all();
			}, seconds * 1000);
		}
	}

	// --- Debug tool ---------------------------------------------------
	show_debug_dialog() {
		const default_to = frappe.datetime.get_today();
		const default_from = frappe.datetime.add_days(default_to, -7);

		const dialog = new frappe.ui.Dialog({
			title: __("Debug: Raw Counts / Line Items / Error Log"),
			size: "extra-large",
			fields: [
				{
					fieldtype: "Select",
					fieldname: "doctype",
					label: __("Doctype"),
					options: ["BRN", "Payment Order", "Purchase Order", "Purchase Invoice"],
					default: "Purchase Invoice",
					reqd: 1,
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Link",
					fieldname: "company",
					label: __("Company (optional)"),
					options: "Company",
					default: this.company_field.get_value(),
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Date",
					fieldname: "from_date",
					label: __("From Date"),
					default: this.from_date_field.get_value() || default_from,
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Date",
					fieldname: "to_date",
					label: __("To Date"),
					default: this.to_date_field.get_value() || default_to,
				},
				{ fieldtype: "Section Break" },
				{ fieldtype: "HTML", fieldname: "result_html" },
			],
			primary_action_label: __("Run"),
			primary_action: () => this.run_debug(dialog, this.get_debug_filter_values(dialog)),
		});

		dialog.fields_dict.result_html.$wrapper.html(`
			<div class="pc-debug-tabs">
				<button class="pc-tab-btn active" data-tab="raw">${__("Raw Counts")}</button>
				<button class="pc-tab-btn" data-tab="lines">${__("Line Items")}</button>
				${
					can_view_error_log()
						? `<button class="pc-tab-btn" data-tab="logs">${__("Error Log")}</button>`
						: ""
				}
			</div>
			<div class="pc-debug-pane active" data-pane="raw"><p class="text-muted">${__(
				"Click Run to load."
			)}</p></div>
			<div class="pc-debug-pane" data-pane="lines"></div>
			<div class="pc-debug-pane" data-pane="logs"></div>
		`);

		dialog.$wrapper.on("click", ".pc-tab-btn", (e) => {
			const tab = $(e.currentTarget).data("tab");
			dialog.$wrapper.find(".pc-tab-btn").removeClass("active");
			$(e.currentTarget).addClass("active");
			dialog.$wrapper.find(".pc-debug-pane").removeClass("active");
			dialog.$wrapper.find(`.pc-debug-pane[data-pane="${tab}"]`).addClass("active");
		});

		dialog.show();
		// Give the dialog one tick to finish applying field defaults before
		// reading them -- reading immediately after show() can return
		// undefined values and silently send an empty request.
		setTimeout(() => {
			const values = this.get_debug_filter_values(dialog);
			if (!values.doctype) return;
			this.run_debug(dialog, values);
		}, 0);
	}

	get_debug_filter_values(dialog) {
		return {
			doctype: dialog.get_value("doctype"),
			company: dialog.get_value("company"),
			from_date: dialog.get_value("from_date"),
			to_date: dialog.get_value("to_date"),
		};
	}

	run_debug(dialog, values) {
		if (!values || !values.doctype) {
			frappe.msgprint({
				title: __("Missing Doctype"),
				indicator: "orange",
				message: __("Please select a Doctype before running the debug tool."),
			});
			return;
		}

		const args = {
			doctype: values.doctype,
			company: values.company,
			from_date: values.from_date,
			to_date: values.to_date,
		};

		frappe.call({
			method: `${API_MODULE}.debug_raw_counts`,
			args,
			freeze: true,
			callback: (r) => this.render_raw_counts(dialog, r.message),
			error: (r) => this.render_call_error(dialog, "raw", r),
		});

		frappe.call({
			method: `${API_MODULE}.debug_line_items`,
			args,
			callback: (r) => this.render_line_items(dialog, r.message),
			error: (r) => this.render_call_error(dialog, "lines", r),
		});

		if (!can_view_error_log()) return;

		frappe.call({
			method: `${API_MODULE}.get_error_logs`,
			args: {
				doctype: values.doctype,
				from_date: values.from_date,
				to_date: values.to_date,
			},
			callback: (r) => this.render_error_logs(dialog, r.message),
			error: (r) => this.render_call_error(dialog, "logs", r),
		});
	}

	render_call_error(dialog, pane, r) {
		dialog.$wrapper
			.find(`.pc-debug-pane[data-pane="${pane}"]`)
			.html(
				`<p class="text-danger">${frappe.utils.escape_html(
					(r && r.exc) || __("Request failed.")
				)}</p>`
			);
	}

	badge_for_source(source) {
		if (source === "mapping") return `<span class="pc-badge-mapping">${__("mapped")}</span>`;
		if (source === "unmapped_fallback_to_docstatus")
			return `<span class="pc-badge-fallback">${__("unmapped -> docstatus")}</span>`;
		if (source === "status_field")
			return `<span class="pc-badge-mapping">${__("native status field")}</span>`;
		if (source === "cancelled_override")
			return `<span class="pc-badge-fallback">${__("cancelled overrides status")}</span>`;
		if (source === "unrecognised_status_fallback_to_docstatus")
			return `<span class="pc-badge-fallback">${__(
				"unrecognised status -> docstatus"
			)}</span>`;
		return `<span class="pc-badge-docstatus">${__("docstatus only")}</span>`;
	}

	render_raw_counts(dialog, data) {
		if (!data) return;
		const rows = data.raw_counts
			.map(
				(r) => `
				<tr>
					<td>${frappe.utils.escape_html(String(r.workflow_state))}</td>
					<td>${r.docstatus}</td>
					<td>${r.count}</td>
					<td>${frappe.utils.escape_html(r.resolved_bucket || "")}</td>
					<td>${this.badge_for_source(r.bucket_source)}</td>
				</tr>`
			)
			.join("");

		dialog.$wrapper.find('.pc-debug-pane[data-pane="raw"]').html(`
			<div style="margin-top: 8px;">
				<p><b>${__("Filters applied")}:</b> <code>${frappe.utils.escape_html(
			JSON.stringify(data.filters_applied)
		)}</code></p>
				<p>
					<b>${__("Has workflow_state field")}:</b> ${data.has_workflow_state_field ? __("Yes") : __("No")}
					&nbsp;|&nbsp; <b>${__("Active Workflow")}:</b> ${data.workflow_active ? __("Yes") : __("No")}
					&nbsp;|&nbsp; <b>${__("Mapping rows for this doctype")}:</b> ${data.mapping_rows_for_doctype}
					&nbsp;|&nbsp; <b>${__("Using mapping")}:</b> ${
			data.using_mapping ? __("Yes") : __("No, using plain docstatus")
		}
					${
						data.using_native_status_field
							? `&nbsp;|&nbsp; <b>${__("Using native status field")}:</b> ${__(
									"Yes"
							  )}`
							: ""
					}
				</p>
				<p><b>${__("Total matching documents")}:</b> ${data.total_matching_documents}</p>
				<p class="text-muted">${__(
					"If 'resolved_bucket' doesn't match what you expect, check 'bucket_source' -- an 'unmapped -> docstatus' badge means this workflow_state needs a row in Payments Compliance Settings > Workflow State Mapping."
				)}</p>
				<table class="table table-bordered" style="margin-top: 10px;">
					<thead><tr><th>${__("Workflow State")}</th><th>${__("Docstatus")}</th><th>${__(
			"Count"
		)}</th><th>${__("Resolved Bucket")}</th><th>${__("Source")}</th></tr></thead>
					<tbody>${
						rows ||
						`<tr><td colspan="5" class="text-muted text-center">${__(
							"No matching documents"
						)}</td></tr>`
					}</tbody>
				</table>
			</div>
		`);
	}

	render_line_items(dialog, data) {
		if (!data) return;
		const has_wf = data.has_workflow_state_field;

		const rows = data.rows
			.map(
				(r) => `
				<tr>
					<td>
						<a href="/app/${frappe.router.slug(data.doctype)}/${encodeURIComponent(
					r.name
				)}" target="_blank">${frappe.utils.escape_html(r.name)}</a>
						${r.pending_on_me ? ` <span class="pc-badge-fallback">${__("pending on me")}</span>` : ""}
					</td>
					${has_wf ? `<td>${frappe.utils.escape_html(String(r.workflow_state || "(blank)"))}</td>` : ""}
					<td>${r.docstatus}</td>
					<td>${frappe.utils.escape_html(r.resolved_bucket || "")}</td>
					<td>${this.badge_for_source(r.bucket_source)}</td>
					<td>${frappe.utils.escape_html(r.creation || "")}</td>
					<td>${frappe.utils.escape_html(r.modified_by || "")}</td>
				</tr>`
			)
			.join("");

		dialog.$wrapper.find('.pc-debug-pane[data-pane="lines"]').html(`
			<div style="margin-top: 8px;">
				<p>
					<b>${__("Rows returned")}:</b> ${data.row_count}${
			data.hit_limit
				? ` <span class="text-warning">(${__(
						"limit reached, narrow the date range"
				  )})</span>`
				: ""
		}
					&nbsp;|&nbsp; <b>${__("Using mapping")}:</b> ${
			data.using_mapping ? __("Yes") : __("No, using plain docstatus")
		}
					${
						data.using_native_status_field
							? `&nbsp;|&nbsp; <b>${__("Using native status field")}:</b> ${__(
									"Yes"
							  )}`
							: ""
					}
				</p>
				<div class="pc-debug-scroll">
					<table class="table table-bordered">
						<thead>
							<tr>
								<th>${__("Name")}</th>
								${has_wf ? `<th>${__("Workflow State")}</th>` : ""}
								<th>${__("Docstatus")}</th>
								<th>${__("Resolved Bucket")}</th>
								<th>${__("Source")}</th>
								<th>${__("Created")}</th>
								<th>${__("Modified By")}</th>
							</tr>
						</thead>
						<tbody>${
							rows ||
							`<tr><td colspan="7" class="text-muted text-center">${__(
								"No matching documents in this range"
							)}</td></tr>`
						}</tbody>
					</table>
				</div>
			</div>
		`);
	}

	render_error_logs(dialog, data) {
		if (!data) return;

		const rows = data.rows
			.map(
				(log, idx) => `
				<tr class="pc-log-summary" data-idx="${idx}">
					<td>${frappe.utils.escape_html(log.creation)}</td>
					<td>${frappe.utils.escape_html(log.method || "-")}</td>
					<td>${frappe.utils.escape_html(log.summary)}</td>
					<td>${log.line_count}</td>
				</tr>
				<tr>
					<td colspan="4" style="padding: 0;">
						<pre class="pc-log-full" data-idx="${idx}">${frappe.utils.escape_html(log.full_text)}</pre>
					</td>
				</tr>`
			)
			.join("");

		dialog.$wrapper.find('.pc-debug-pane[data-pane="logs"]').html(`
			<div style="margin-top: 8px;">
				<p><b>${__("Log entries found")}:</b> ${data.row_count}${
			data.hit_limit
				? ` <span class="text-warning">(${__(
						"limit reached, narrow the date range"
				  )})</span>`
				: ""
		}</p>
				<div class="pc-debug-scroll">
					<table class="table table-bordered">
						<thead><tr><th>${__("Time")}</th><th>${__("Method")}</th><th>${__(
			"Summary (last line)"
		)}</th><th>${__("# Lines")}</th></tr></thead>
						<tbody>${
							rows ||
							`<tr><td colspan="4" class="text-muted text-center">${__(
								"No error log entries in this range"
							)}</td></tr>`
						}</tbody>
					</table>
				</div>
			</div>
		`);

		dialog.$wrapper.find(".pc-log-summary").on("click", (e) => {
			const idx = $(e.currentTarget).data("idx");
			dialog.$wrapper.find(`.pc-log-full[data-idx="${idx}"]`).toggle();
		});
	}
}

approval_engine.dashboard.PaymentsComplianceDashboard = PaymentsComplianceDashboard;

frappe.pages["procure-to-pay"].on_page_load = function (wrapper) {
	new approval_engine.dashboard.PaymentsComplianceDashboard(wrapper);
};

/**
 * Whether the current user may see the Error Log tab. The server allows
 * System Manager only, so the tab and its call are skipped for others.
 *
 * @returns {boolean} True for System Managers.
 */
function can_view_error_log() {
	return frappe.user.has_role("System Manager");
}
