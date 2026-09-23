// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

frappe.listview_settings["Supplier"] = {
	refresh: function (listview) {
		listview.page.add_inner_button("On Board Vendor", function () {
			send_onboard_invitation();
		});
	},
};

function send_onboard_invitation() {
	approval_engine.vendor.send_vendor_invitation_mail("Supplier");
}
