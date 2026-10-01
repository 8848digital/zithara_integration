// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

// Zithara loyalty points on the Sales Invoice form (logic in zithara_integration.bundle.js).
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		zithara_integration.loyalty.setup(frm);
	},
});
