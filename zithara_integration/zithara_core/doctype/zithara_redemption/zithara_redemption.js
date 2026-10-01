// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

const REDEMPTION_STATUS_COLORS = { Redeemed: "green", "OTP Sent": "blue", Failed: "red" };

frappe.ui.form.on("Zithara Redemption", {
	refresh(frm) {
		frm.page.set_indicator(
			__(frm.doc.status),
			REDEMPTION_STATUS_COLORS[frm.doc.status] || "gray"
		);
	},
});
