// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

// Zithara loyalty points on invoice forms: balance, OTP and redemption.
// Shared by the Sales Invoice and POS Invoice form scripts.

const LOYALTY_API = "zithara_integration.zithara_core.api.v1.loyalty";

frappe.provide("zithara_integration.loyalty");

/**
 * frappe.call error handler for this app's APIs: validation errors come back as
 * HTTP 400 in the app's response envelope, which Frappe doesn't display itself.
 *
 * @param {object} xhr - Failed request.
 * @returns {void}
 */
zithara_integration.show_call_error = function (xhr) {
	const body = (xhr && xhr.responseJSON) || {};
	if (body.message) {
		frappe.msgprint({ title: __("Zithara"), message: body.message, indicator: "red" });
	}
};

/**
 * Add the Zithara buttons and the redeemed-points note to an invoice form.
 *
 * @param {object} frm - Sales Invoice or POS Invoice form.
 * @returns {void}
 */
zithara_integration.loyalty.setup = function (frm) {
	if (frm.doc.zithara_redemption) {
		frm.dashboard.add_comment(
			__("Zithara: {0} points redeemed = {1} discount ({2})", [
				frm.doc.zithara_redeemed_points,
				format_currency(frm.doc.zithara_redeemed_amount, frm.doc.currency),
				frm.doc.zithara_redemption,
			]),
			"green",
			true
		);
	}
	const enabled = (frappe.boot.zithara || {}).loyalty_redemption;
	if (!enabled || frm.is_new() || !frm.doc.customer || frm.doc.is_return) return;

	frm.add_custom_button(__("Loyalty Points"), () => showBalance(frm), __("Zithara"));
	if (frm.doc.docstatus === 0 && !frm.doc.zithara_redemption) {
		frm.add_custom_button(__("Redeem Points"), () => startRedemption(frm), __("Zithara"));
	}
};

/**
 * Call a loyalty endpoint and hand the envelope to `onDone`; failures are shown.
 *
 * @param {string} method - Endpoint name in the loyalty API.
 * @param {object} args - Endpoint arguments.
 * @param {Function} onDone - Called with the response envelope when status is true.
 * @param {string} [type] - HTTP method, POST by default.
 * @returns {void}
 */
function callLoyalty(method, args, onDone, type = "POST") {
	frappe.call({
		method: `${LOYALTY_API}.${method}`,
		args,
		type,
		freeze: true,
		callback: (r) => {
			if (!r.status) {
				showError(r.message);
				return;
			}
			onDone(r);
		},
		error: zithara_integration.show_call_error,
	});
}

/**
 * Show a Zithara error to the user.
 *
 * @param {string} message - Error text from the server.
 * @returns {void}
 */
function showError(message) {
	frappe.msgprint({ title: __("Zithara"), message, indicator: "red" });
}

/**
 * Describe Zithara's redeem rule, e.g. "1000 points = ₹2,000".
 *
 * @param {object|null} rule - redeem_rule from get_points.
 * @param {string} currency - Invoice currency.
 * @returns {string} Readable rule, or "" when Zithara sent none.
 */
function ruleText(rule, currency) {
	if (!rule || !rule.points) return "";
	let text = __("{0} points = {1}", [rule.points, format_currency(rule.amount, currency)]);
	if (rule.is_min_limit) text += `, ${__("minimum {0}", [rule.min_redeem_limit])}`;
	if (rule.is_max_limit) text += `, ${__("maximum {0}", [rule.max_redeem_limit])}`;
	return text;
}

/**
 * Show the customer's current balance.
 *
 * @param {object} frm - Invoice form.
 * @returns {void}
 */
function showBalance(frm) {
	callLoyalty(
		"get_points",
		{ invoice_doctype: frm.doctype, invoice: frm.doc.name },
		(r) => {
			const rule = ruleText(r.data.redeem_rule, frm.doc.currency);
			frappe.msgprint({
				title: __("Zithara Loyalty Points"),
				message: `<b>${frappe.utils.escape_html(r.data.customer)}</b>: ${
					r.data.points
				} ${__("points")}${rule ? `<br>${__("Redeem rule")}: ${rule}` : ""}`,
			});
		},
		"GET"
	);
}

/**
 * Step 1: show the balance, ask how many points, and send the OTP.
 *
 * @param {object} frm - Draft invoice form.
 * @returns {void}
 */
function startRedemption(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the invoice before redeeming points."));
		return;
	}
	callLoyalty(
		"get_points",
		{ invoice_doctype: frm.doctype, invoice: frm.doc.name },
		(r) => {
			const rule = ruleText(r.data.redeem_rule, frm.doc.currency);
			const dialog = new frappe.ui.Dialog({
				title: __("Redeem Zithara Points"),
				fields: [
					{
						fieldtype: "HTML",
						options: `<p>${__("Available points")}: <b>${r.data.points}</b><br>${__(
							"Most points for this invoice"
						)}: <b>${r.data.max_points}</b>${
							rule ? `<br>${__("Redeem rule")}: ${rule}` : ""
						}</p><p class="text-muted">${__(
							"Zithara will text an OTP to the customer's registered mobile."
						)}</p>`,
					},
					{
						fieldname: "points",
						fieldtype: "Int",
						label: __("Points to Redeem"),
						reqd: 1,
						default: r.data.max_points,
					},
				],
				primary_action_label: __("Send OTP"),
				primary_action: ({ points }) => {
					if (points > r.data.max_points) {
						frappe.msgprint(
							__("At most {0} points can be redeemed on this invoice.", [
								r.data.max_points,
							])
						);
						return;
					}
					callLoyalty(
						"send_otp",
						{ invoice_doctype: frm.doctype, invoice: frm.doc.name, points },
						(sent) => {
							dialog.hide();
							askOtp(frm, sent.data);
						}
					);
				},
			});
			dialog.show();
		},
		"GET"
	);
}

/**
 * Step 2: enter the OTP; on success the invoice gets the discount and reloads.
 *
 * @param {object} frm - Draft invoice form.
 * @param {object} redemption - send_otp data: redemption, points, sent_to.
 * @returns {void}
 */
function askOtp(frm, redemption) {
	const sentTo = redemption.sent_to ? ` ${__("to")} ${redemption.sent_to}` : "";
	const dialog = new frappe.ui.Dialog({
		title: __("Enter OTP"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p>${__("OTP sent{0} for {1} points.", [
					sentTo,
					redemption.points,
				])}</p>`,
			},
			{ fieldname: "otp", fieldtype: "Data", label: __("OTP"), reqd: 1 },
		],
		primary_action_label: __("Verify & Apply"),
		primary_action: ({ otp }) => {
			callLoyalty(
				"verify_otp",
				{
					invoice_doctype: frm.doctype,
					invoice: frm.doc.name,
					redemption: redemption.redemption,
					otp,
				},
				(done) => {
					dialog.hide();
					frappe.show_alert({
						message: __("{0} points redeemed: {1} discount applied", [
							done.data.points,
							format_currency(done.data.amount, frm.doc.currency),
						]),
						indicator: "green",
					});
					frm.reload_doc();
				}
			);
		},
	});
	dialog.show();
}
