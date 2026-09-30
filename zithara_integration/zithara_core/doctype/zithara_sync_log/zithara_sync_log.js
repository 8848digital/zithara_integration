// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

const SYNC_API = "zithara_integration.zithara_core.api.v1.sync";
const SYNC_STATUS_COLORS = {
	Success: "green",
	Duplicate: "green",
	Queued: "blue",
	Failed: "red",
	Skipped: "orange",
};

frappe.ui.form.on("Zithara Sync Log", {
	refresh(frm) {
		frm.page.set_indicator(__(frm.doc.status), SYNC_STATUS_COLORS[frm.doc.status] || "gray");

		if (["Failed", "Skipped"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Retry Now"), () => retrySync(frm)).addClass("btn-primary");
		}
		if (frm.doc.store && ["Success", "Duplicate"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Check on Zithara"), () => checkOrder(frm));
		}
	},
});

/**
 * Send the sync again and reload the log.
 *
 * @param {object} frm - The Zithara Sync Log form.
 * @returns {void}
 */
function retrySync(frm) {
	frappe.call({
		method: `${SYNC_API}.retry`,
		args: { log: frm.doc.name },
		freeze: true,
		callback: (r) => {
			frappe.show_alert({ message: r.message, indicator: r.status ? "green" : "red" });
			frm.reload_doc();
		},
	});
}

/**
 * Show the order as Zithara stored it (read-only).
 *
 * @param {object} frm - The Zithara Sync Log form.
 * @returns {void}
 */
function checkOrder(frm) {
	frappe.call({
		method: `${SYNC_API}.check_order`,
		args: { log: frm.doc.name },
		type: "GET",
		freeze: true,
		callback: (r) => {
			const order = (r.data || {}).order;
			frappe.msgprint({
				title: r.message,
				indicator: r.status ? "green" : "orange",
				message: order
					? `<pre>${frappe.utils.escape_html(JSON.stringify(order, null, 2))}</pre>`
					: "",
			});
		},
	});
}
