frappe.pages["finance-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Finance Overview",
		single_column: true,
	});
	// The design ships its own header, so hide Frappe's default page head.
	$(wrapper).find(".page-head").hide();
	new FinanceDashboard(page);
};

// Dashboard columns -> target DocType. PO/PI/PE are the standard targets; BRD maps to the
// custom BRN DocType (rename here if your build uses a different name). A column whose DocType
// has no submitted Approval Matrix simply shows zero.
const COLUMNS = [
	{ label: "BRD", doctype: "BRN" },
	{ label: "PO", doctype: "Purchase Order" },
	{ label: "PI", doctype: "Purchase Invoice" },
	{ label: "PE", doctype: "Payment Entry" },
];

class FinanceDashboard {
	constructor(page) {
		this.page = page;
		this.company = null;
		this.range = "today";
		this.render_shell();
		this.load_companies();
	}

	// ---- helpers ----------------------------------------------------------
	// Indian digit grouping, always to the paisa. Do NOT round to whole rupees: amount bands are
	// boundary-sensitive (a band ends at Max, the next starts at Max + 0.01), so a rounded total
	// misrepresents which band a document falls in — 500000.01 would read as 5,00,000 (lower band)
	// and 99999.50 as 1,00,000 (upper band).
	fmt_inr(n) {
		const v = Number(n) || 0;
		const fixed = Math.abs(v).toFixed(2);
		const neg = v < 0 && Number(fixed) !== 0; // never render "-0.00"
		const [whole, paise] = fixed.split(".");
		let s = whole;
		if (s.length > 3) {
			const last3 = s.slice(-3);
			const rest = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
			s = rest + "," + last3;
		}
		return (neg ? "-" : "") + s + "." + paise;
	}

	initials(name) {
		const parts = String(name || "").trim().split(/\s+/);
		const chars = parts.length > 1 ? parts[0][0] + parts[1][0] : (name || "").slice(0, 2);
		return (chars || "?").toUpperCase();
	}

	date_range(key) {
		const m = moment;
		if (key === "today") return [m(), m()];
		if (key === "week") return [m().startOf("week"), m().endOf("week")];
		if (key === "month") return [m().startOf("month"), m().endOf("month")];
		if (key === "lastmonth")
			return [m().subtract(1, "month").startOf("month"), m().subtract(1, "month").endOf("month")];
		return [null, null];
	}

	range_label(key, from, to) {
		const f = (d) => moment(d).format("D MMM YYYY");
		if (key === "today") return `Today · ${moment().format("D MMM YYYY")}`;
		if (key === "week") return `This week · ${moment(from).format("D MMM")} – ${f(to)}`;
		if (key === "month") return `This month · ${moment(from).format("D MMM")} – ${f(to)}`;
		if (key === "lastmonth") return `Last month · ${moment(from).format("D MMM")} – ${f(to)}`;
		return from === to
			? `Custom · ${f(from)}`
			: `Custom · ${moment(from).format("D MMM")} – ${f(to)}`;
	}

	// ---- shell ------------------------------------------------------------
	render_shell() {
		const head = COLUMNS.map((c) => `<th class="doc-col">${c.label}</th>`).join("");
		this.page.main.html(`
			<div class="fin-dash">
			<div class="shell">
				<div class="fd-header">
					<div class="header-left">
						<div class="logo">FN</div>
						<div class="header-titles">
							<h1>Finance Overview</h1>
							<p>Pending &amp; on-hold value across ${COLUMNS.map((c) => c.label).join(", ")}</p>
						</div>
					</div>
					<div class="header-right">
						<div class="company-select" data-el="companySelect">
							<button class="company-btn" data-el="companyBtn">
								<div class="company-avatar">–</div>
								<div class="company-meta">
									<span class="name">Loading…</span>
									<span class="id"></span>
								</div>
								<svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
							</button>
							<div class="company-dropdown" data-el="companyDropdown"></div>
						</div>
					</div>
				</div>

				<div class="section-head">
					<div class="section-head-group">
						<h2>Company overview</h2>
						<span class="sub" data-el="overviewSub">All-time totals</span>
					</div>
				</div>
				<div class="matrix-card">
					<table class="matrix">
						<thead><tr><th></th>${head}</tr></thead>
						<tbody data-el="overviewBody"></tbody>
					</table>
				</div>

				<div class="section-head">
					<div class="section-head-group">
						<h2>Detailed view</h2>
						<span class="sub">Approved value by date range</span>
					</div>
				</div>
				<div class="filter-bar">
					<div class="filter-pills" data-el="filterPills">
						<button class="filter-pill active" data-range="today">Today</button>
						<button class="filter-pill" data-range="week">This week</button>
						<button class="filter-pill" data-range="month">This month</button>
						<button class="filter-pill" data-range="lastmonth">Last month</button>
						<button class="filter-pill" data-range="custom">Custom range</button>
					</div>
					<div class="custom-range" data-el="customRange">
						<input type="date" data-el="dateFrom">
						<span class="to">→</span>
						<input type="date" data-el="dateTo">
						<button class="apply-btn" data-el="applyRange">Apply</button>
					</div>
					<div class="range-readout" data-el="rangeReadout">Showing <span>Today</span></div>
				</div>
				<div class="matrix-card">
					<table class="matrix">
						<thead><tr><th></th>${head}</tr></thead>
						<tbody data-el="detailBody"></tbody>
					</table>
					<div class="footnote" style="padding:0 20px 18px;">
						<div class="legend"><span class="dot" style="background:var(--approved)"></span>Approved — cleared for processing, totals reflect the selected date range</div>
					</div>
				</div>
			</div>
			</div>
		`);

		this.$ = (name) => this.page.main.find(`[data-el="${name}"]`);
		this.bind_events();
	}

	bind_events() {
		const $sel = this.$("companySelect");
		this.$("companyBtn").on("click", (e) => {
			e.stopPropagation();
			$sel.toggleClass("open");
		});
		$(document).on("click.findash", () => $sel.removeClass("open"));

		this.$("filterPills").on("click", ".filter-pill", (e) => {
			const $pill = $(e.currentTarget);
			this.$("filterPills").find(".filter-pill").removeClass("active");
			$pill.addClass("active");
			this.range = $pill.data("range");
			if (this.range === "custom") {
				this.$("customRange").addClass("show");
				// Prefill with today so Apply works immediately without forcing a pick first,
				// and so the two inputs never sit empty next to each other.
				const $from = this.$("dateFrom");
				const $to = this.$("dateTo");
				const today = moment().format("YYYY-MM-DD");
				if (!$from.val()) $from.val(today);
				if (!$to.val()) $to.val(today);
				this.$("rangeReadout").html(`Showing <span>Custom range — pick dates and Apply</span>`);
			} else {
				this.$("customRange").removeClass("show");
				this.load_detail();
			}
		});

		this.$("applyRange").on("click", () => {
			const from = this.$("dateFrom").val();
			const to = this.$("dateTo").val();
			if (!from || !to) {
				frappe.show_alert({ message: __("Pick both a from and to date"), indicator: "orange" });
				return;
			}
			if (from > to) {
				frappe.show_alert({ message: __("From date must be before To date"), indicator: "orange" });
				return;
			}
			this.load_detail(from, to);
		});
	}

	// ---- data -------------------------------------------------------------
	load_companies() {
		// Approver roles are granted real Company:Read by generator.ensure_company_read
		// (a normal Custom DocPerm, admin-visible/editable in Role Permission Manager) --
		// so a plain client-side list call works for any approver, not just business roles.
		frappe.db
			.get_list("Company", { fields: ["name", "abbr", "tax_id"], limit: 0, order_by: "name asc" })
			.then((companies) => {
				this.companies = companies || [];
				this.render_company_dropdown();
				const preferred =
					frappe.defaults.get_user_default("Company") ||
					(this.companies[0] && this.companies[0].name);
				if (preferred) this.select_company(preferred);
			});
	}

	render_company_dropdown() {
		const $dd = this.$("companyDropdown").empty();
		if (!this.companies.length) {
			$dd.append(`<div class="company-option"><div class="company-meta"><span class="name">No companies</span></div></div>`);
			return;
		}
		this.companies.forEach((c) => {
			const idline = c.tax_id ? `Tax · ${c.tax_id}` : c.abbr ? `Abbr · ${c.abbr}` : "";
			$dd.append(`
				<div class="company-option" data-company="${frappe.utils.escape_html(c.name)}">
					<div class="company-avatar">${this.initials(c.name)}</div>
					<div>
						<span class="name">${frappe.utils.escape_html(c.name)}</span>
						<span class="id">${frappe.utils.escape_html(idline)}</span>
					</div>
					<span class="check-slot"></span>
				</div>`);
		});
		$dd.find(".company-option").on("click", (e) => {
			this.select_company($(e.currentTarget).data("company"));
			this.$("companySelect").removeClass("open");
		});
	}

	select_company(company) {
		this.company = company;
		const c = (this.companies || []).find((x) => x.name === company) || { name: company };
		const idline = c.tax_id ? `Tax · ${c.tax_id}` : c.abbr ? `Abbr · ${c.abbr}` : "";
		const $btn = this.$("companyBtn");
		$btn.find(".company-avatar").text(this.initials(c.name));
		$btn.find(".name").text(c.name);
		$btn.find(".id").text(idline);
		this.$("overviewSub").text(`All-time totals for ${c.name}`);
		// active tick
		const $dd = this.$("companyDropdown");
		$dd.find(".company-option").removeClass("active").find(".check-slot").html("");
		$dd.find(`.company-option[data-company="${company}"]`)
			.addClass("active")
			.find(".check-slot")
			.html('<span class="check">✓</span>');

		this.load_overview();
		this.load_detail();
	}

	cells(get_metric, cls) {
		return COLUMNS.map((col) => {
			const m = get_metric(col.doctype) || { records: 0, amount: 0 };
			return `<td>
				<div class="cell-metric ${cls}">
					<span class="amt"><span class="cur">₹</span>${this.fmt_inr(m.amount)}</span>
					<span class="count-pill">Docs <span class="num">${m.records || 0}</span></span>
				</div>
			</td>`;
		}).join("");
	}

	load_overview() {
		if (!this.company) return;
		const $body = this.$("overviewBody").addClass("is-loading");
		frappe.call({
			method: "approval_engine.dashboard.get_dashboard_summary",
			args: { company: this.company },
			callback: (r) => {
				const data = r.message || {};
				const pending = this.cells((dt) => (data[dt] || {}).pending, "is-pending");
				const onhold = this.cells((dt) => (data[dt] || {}).on_hold, "is-onhold");
				$body.removeClass("is-loading").html(`
					<tr><td><span class="row-tag pending"><span class="dot"></span>Pending</span></td>${pending}</tr>
					<tr><td><span class="row-tag onhold"><span class="dot"></span>On hold</span></td>${onhold}</tr>`);
			},
		});
	}

	load_detail(custom_from, custom_to) {
		if (!this.company) return;
		let from, to, label;
		if (this.range === "custom") {
			from = custom_from;
			to = custom_to;
			if (!from || !to) return;
			label = this.range_label("custom", from, to);
		} else {
			const [f, t] = this.date_range(this.range);
			from = f.format("YYYY-MM-DD");
			to = t.format("YYYY-MM-DD");
			label = this.range_label(this.range, f, t);
		}
		this.$("rangeReadout").html(`Showing <span>${frappe.utils.escape_html(label)}</span>`);
		const $body = this.$("detailBody").addClass("is-loading");
		frappe.call({
			method: "approval_engine.dashboard.get_approved_summary",
			args: { company: this.company, from_date: from, to_date: to },
			callback: (r) => {
				const data = r.message || {};
				const approved = this.cells((dt) => data[dt], "is-approved");
				$body.removeClass("is-loading").html(
					`<tr><td><span class="row-tag approved"><span class="dot"></span>Approved</span></td>${approved}</tr>`
				);
			},
		});
	}
}
