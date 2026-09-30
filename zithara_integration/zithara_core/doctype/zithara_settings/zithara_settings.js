// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

const ZITHARA_BASE_URLS = {
	Sandbox: "https://dev-pos-api.zithara.com",
	Production: "https://pos-api.zithara.com",
};

frappe.ui.form.on("Zithara Settings", {
	environment(frm) {
		const known = Object.values(ZITHARA_BASE_URLS);
		if (!frm.doc.base_url || known.includes(frm.doc.base_url)) {
			frm.set_value("base_url", ZITHARA_BASE_URLS[frm.doc.environment]);
		}
	},
});
