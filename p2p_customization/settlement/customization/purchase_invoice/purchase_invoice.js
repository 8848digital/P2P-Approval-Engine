frappe.ui.form.on('Purchase Invoice',  {
	setup: function(frm){
		frm.set_query("nature_of_service", "items", function() {
			return {
				query: "p2p_customization.settlement.customization.purchase_invoice.api.get_nature_of_service_query",
				filters: {
					supplier: frm.doc.supplier
				}
			};
		});
	},
	refresh(frm){
		if (!frm.is_new()) {
			frm.trigger("send_pi_to_vendor");
		}
	},
	supplier(frm){
		// supplier's legal type (Individual/HUF/etc.) decides which Tax
		// Withholding Category applies, so re-resolve it on any already
		// selected item rows when the supplier changes. Batched into one
		// call for every row instead of one round-trip per row.
		refresh_all_tax_withholding_categories(frm);
	},
	send_pi_to_vendor(frm) {
		frm.add_custom_button(__('Send PI to Vendor'), function () {
			frappe.call({
				method: "p2p_customization.settlement.customization.purchase_invoice.api.send_po_to_vendor",
				args: {
					purchase_invoice: frm.doc.name,
				},
				callback: function (r) {
					if (r.message) {
						frappe.msgprint(__("Email sent to Vendor"));
					}
				}
			});
		});
	},
})

frappe.ui.form.on("Purchase Invoice Item", {
	nature_of_service: function(frm, cdt, cdn) {
		set_pi_tax_withholding_category(frm, cdt, cdn);
	},
});

function set_pi_tax_withholding_category(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row.nature_of_service) {
		frappe.model.set_value(cdt, cdn, "tax_withholding_category", "");
		frappe.model.set_value(cdt, cdn, "apply_tds", 0);
		return;
	}
	frappe.call({
		method: "p2p_customization.settlement.doc_events.tds_reference.get_tax_withholding_category",
		args: {
			nature_of_service: row.nature_of_service,
			supplier: frm.doc.supplier
		},
		callback: function(r) {
			apply_tax_withholding_category(cdt, cdn, r.message);
		}
	});
}

function apply_tax_withholding_category(cdt, cdn, category) {
	if (category) {
		frappe.model.set_value(cdt, cdn, "tax_withholding_category", category);
		frappe.model.set_value(cdt, cdn, "apply_tds", 1);
	} else {
		frappe.model.set_value(cdt, cdn, "tax_withholding_category", "");
		frappe.model.set_value(cdt, cdn, "apply_tds", 0);
	}
}

function refresh_all_tax_withholding_categories(frm) {
	const rows = (frm.doc.items || []).filter((row) => row.nature_of_service);
	if (!rows.length) return;

	const nature_of_services = [...new Set(rows.map((row) => row.nature_of_service))];
	frappe.call({
		method: "p2p_customization.settlement.doc_events.tds_reference.get_tax_withholding_categories",
		args: {
			nature_of_services: nature_of_services,
			supplier: frm.doc.supplier
		},
		callback: function(r) {
			const categories = r.message || {};
			rows.forEach((row) => {
				apply_tax_withholding_category(row.doctype, row.name, categories[row.nature_of_service]);
			});
		}
	});
}

frappe.ui.form.on('Purchase Invoice', {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frappe.db.get_value(
				"ITC Reversal Log", { purchase_invoice: frm.doc.name },
				["name", "itc_criteria_status", "reversal_status", "invoice_fiscal_year"]
			).then(({ message }) => {
				if (!message || !message.name) return;

				if (message.itc_criteria_status === "Reversed - Prior FY Invoice") {
					const color = message.reversal_status === "Reversed" ? "red" : "orange";
					frm.dashboard.add_indicator(
						__("ITC: {0} ({1})", [message.reversal_status, message.invoice_fiscal_year]),
						color
					);
				} else if (message.itc_criteria_status === "All Other ITC") {
					frm.dashboard.add_indicator(__("ITC Criteria: All Other ITC"), "green");
				}

				frm.add_custom_button(__("View ITC Reversal Log"), () => {
					frappe.set_route("Form", "ITC Reversal Log", message.name);
				});
			});
		}

		update_purchase_invoice_warnings(frm);
	},
	onload(frm){
		update_purchase_invoice_warnings(frm);
	},

	shipping_address(frm) {
		update_purchase_invoice_warnings(frm);
	},

	billing_address(frm) {
		update_purchase_invoice_warnings(frm);
	},

	supplier_address(frm) {
		update_purchase_invoice_warnings(frm);
	},

	brn(frm) {
		update_purchase_invoice_warnings(frm);
	},

	onload_post_render: function(frm){
		if(frm.is_new()){
			frm.trigger("posting_date")
		}
	},
	"posting_date": function(frm){
		if (frm.doc.posting_date){
			frappe.call({
				method: "p2p_customization.settlement.customization.purchase_order.api.get_fiscal_year_and_validity",
				args: {
					date: frm.doc.posting_date,
					brn: frm.doc.brn
				},
				async: false,
				callback: function(r){
					if(r.message){
						frm.set_value("custom_fiscal_year", r.message.fiscal_year)
						frm.set_value("validity_start_date", r.message.validity_start_date)
						frm.set_value("validity_end_date", r.message.validity_end_date)
					}
				}
			})
		}
	}
});

// frm.dashboard.set_headline() is a single slot -- calling it more than
// once just overwrites the previous message, so every top-of-form warning
// for this doctype is built here as one combined banner (an array of
// warning rows) instead of each condition owning its own set_headline call
// and silently clobbering the others.
function update_purchase_invoice_warnings(frm) {
	frm.dashboard.clear_headline();

	const warnings = [];
	const billing = frm.doc.billing_address;

	if (!frm.doc.shipping_address) {
		warnings.push({
			gradient: "linear-gradient(90deg,#e74c3c,#c0392b)",
			text: "Warning: Shipping Address is not set. Please set Shipping Address.",
		});
	} else if (billing && billing !== frm.doc.shipping_address) {
		warnings.push({
			gradient: "linear-gradient(90deg,#f39c12,#e67e22)",
			text: "Warning: Shipping Address does not match Billing Address. Please Verify it.",
		});
	}

	if (!frm.doc.brn) {
		warnings.push({
			gradient: "linear-gradient(90deg,#e74c3c,#c0392b)",
			text: "Warning: BRN is not set for this Purchase Invoice.",
		});
	}

	if (!warnings.length) return;

	const html = warnings
		.map(
			(w) => `
				<div style="background:${w.gradient};color:#fff;padding:10px 15px;border-radius:6px;font-weight:bold;font-size:14px;text-align:center;margin-bottom:4px;">
					<i class="fa fa-exclamation-triangle" style="margin-right:8px;"></i>
					${w.text}
				</div>`
		)
		.join("");

	frm.dashboard.set_headline(html);
}

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
        set_itc_eligibility(frm);
	},
});

frappe.ui.form.on('Purchase Invoice', {
    company_gstin: function(frm) {
        set_itc_eligibility(frm);
    },
    company: function(frm) {
        set_itc_eligibility(frm);
    }
});

function set_itc_eligibility(frm) {
    if (!frm.doc.company || !frm.doc.company_gstin) {
        return;
    }

    frappe.db.get_value(
        'Company GSTIN',
        { company: frm.doc.company },   // filter by company, not by name
        'isd_gstin'
    ).then(r => {
        let isd_gstin = r.message && r.message.isd_gstin;

        if (isd_gstin && frm.doc.company_gstin === isd_gstin) {
            frm.set_value('eligibility_for_itc', 'Input Service Distributor');
        }
    });
}
