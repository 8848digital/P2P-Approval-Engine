frappe.listview_settings['Purchase Invoice'] = frappe.listview_settings['Purchase Invoice'] || {};

frappe.listview_settings['Purchase Invoice'].add_fields =
    frappe.listview_settings['Purchase Invoice'].add_fields || [];
frappe.listview_settings['Purchase Invoice'].add_fields.push("msme_applicable");

frappe.listview_settings['Purchase Invoice'].formatters =
    frappe.listview_settings['Purchase Invoice'].formatters || {};

frappe.listview_settings['Purchase Invoice'].formatters.msme_applicable = function (value) {
    if (value === "Yes") {
        return `<span style="color: #e03131; font-weight: 600;">Priority Payment</span>`;
    }
    return "";
};