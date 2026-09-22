frappe.listview_settings["Supplier"] = {
	refresh: function (listview) {
		listview.page.add_inner_button("On Board Vendor", function () {
			send_onboard_invitation();
		});
	},
};

function send_onboard_invitation() {
	p2p_customization.vendor.send_vendor_invitation_mail("Supplier");
}
