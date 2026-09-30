// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

const STORE_API = "zithara_integration.zithara_core.api.v1.store";
const STORE_STATUS_COLORS = {
	Active: "green",
	"Pending Approval": "orange",
	"Not Verified": "yellow",
	"Awaiting Credentials": "blue",
	"Invalid Credentials": "red",
	Disabled: "gray",
};

frappe.ui.form.on("Zithara Store", {
	refresh(frm) {
		frm.page.set_indicator(__(frm.doc.status), STORE_STATUS_COLORS[frm.doc.status] || "gray");
		if (frm.is_new()) return;

		if (frm.doc.client_id) {
			frm.add_custom_button(__("Test Connection"), () =>
				callStoreApi(frm, "test_connection")
			);
		}
		if (frm.doc.status === "Pending Approval") {
			frm.add_custom_button(__("Approve"), () => callStoreApi(frm, "approve")).addClass(
				"btn-primary"
			);
		}
		if (["Awaiting Credentials", "Invalid Credentials"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Request Credentials"), () =>
				callStoreApi(frm, "request_credentials")
			);
		}
	},
});

/**
 * Call a store action, show Zithara's answer and reload the form.
 *
 * @param {object} frm - The Zithara Store form.
 * @param {string} method - API method in the store module, e.g. "test_connection".
 * @returns {void}
 */
function callStoreApi(frm, method) {
	frappe.call({
		method: `${STORE_API}.${method}`,
		args: { store: frm.doc.name },
		freeze: true,
		callback: (r) => {
			const data = r.data || {};
			const note = data.last_error ? `<br>${frappe.utils.escape_html(data.last_error)}` : "";
			frappe.msgprint({
				title: __("Zithara"),
				indicator: r.status ? "green" : "red",
				message: `${r.message || ""}${note}`,
			});
			frm.reload_doc();
		},
	});
}
