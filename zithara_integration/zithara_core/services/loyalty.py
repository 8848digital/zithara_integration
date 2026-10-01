# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Zithara loyalty-points lookup and the customer identity sent with loyalty calls.
Zithara's field casing differs per endpoint, so each call builds its own keys.
"""

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import cint, flt

from zithara_integration.zithara_core.services.client import ZitharaClient
from zithara_integration.zithara_core.services.client_response import ZitharaError
from zithara_integration.zithara_core.services.value_format import normalize_phone

LOYALTY_POINTS_PATH = "/v1/customer/loyalty-points"
INITIATE_REDEMPTION_PATH = "/v1/initiate-redemption"
COMPLETE_REDEMPTION_PATH = "/v1/complete-redemption"

# Zithara's key for each identity, per endpoint (it really differs).
IDENTITY_KEYS = {
	"points": {"phone": "phone", "platform_customer_id": "platformCustomerId"},
	"initiate": {"phone": "phone_number", "platform_customer_id": "platform_Customer_Id"},
	"complete": {"phone": "phone_number", "platform_customer_id": "platform_customer_id"},
}


def customer_identity(customer: str) -> dict:
	"""
	How loyalty calls identify the customer on Zithara. The phone is used when
	the customer has one: it matches Zithara customers created by any system,
	while the platform customer id only matches customers our orders created.

	Parameters:
	        customer (str, required): Customer name.

	Returns:
	        dict: {"phone": "91..."} or {"platform_customer_id": customer}.
	"""
	mobile = frappe.db.get_value("Customer", customer, "mobile_no")
	country_code = frappe.get_cached_doc("Zithara Settings").phone_country_code
	phone = normalize_phone(mobile, country_code)
	return {"phone": phone} if phone else {"platform_customer_id": customer}


def identity_fields(identity: dict, endpoint: str) -> dict:
	"""
	Rename the identity to the keys one endpoint expects.

	Parameters:
	        identity (dict, required): From customer_identity().
	        endpoint (str, required): "points", "initiate" or "complete".

	Returns:
	        dict: Identity with Zithara's keys for that endpoint.
	"""
	keys = IDENTITY_KEYS[endpoint]
	return {keys[key]: value for key, value in identity.items()}


def redemption_enabled() -> bool:
	"""
	Loyalty features are opt-in: Zithara enabled and Enable Points Redemption on.

	Returns:
	        bool: True when points can be looked up and redeemed.
	"""
	settings = frappe.get_cached_doc("Zithara Settings")
	return bool(settings.enabled and settings.enable_loyalty_redemption)


def ensure_redemption_enabled() -> None:
	"""
	Refuse loyalty calls when points redemption is switched off.

	Returns:
	        None
	"""
	if not redemption_enabled():
		frappe.throw(_("Zithara points redemption is not enabled in Zithara Settings"))


def get_points(customer: str, store: str) -> dict:
	"""
	Read a customer's points balance and redeem rule from Zithara (no side effects).

	Parameters:
	        customer (str, required): Customer name.
	        store (str, required): Zithara Store whose credentials are used.

	Returns:
	        dict: {"customer", "store", "points", "zithara_customer_id", "redeem_rule"}.
	"""
	ensure_redemption_enabled()
	query = urlencode(identity_fields(customer_identity(customer), "points"))
	reply = ZitharaClient.for_store(store).call("GET", f"{LOYALTY_POINTS_PATH}?{query}")
	data = (reply.get("data") if isinstance(reply, dict) else None) or {}
	return {
		"customer": customer,
		"store": store,
		"points": data.get("points") or 0,
		"zithara_customer_id": data.get("customer_id"),
		"redeem_rule": redeem_rule(data.get("config")),
	}


def redeem_rule(config: dict | None) -> dict | None:
	"""
	The merchant's redeem rule from Zithara's config, passed through for display
	(Zithara enforces it; we don't guess its meaning).

	Parameters:
	        config (dict, optional): data.config from the loyalty-points reply.

	Returns:
	        dict | None: Zithara's "redeem" block, or None when absent.
	"""
	for conversion in (config or {}).get("conversion") or []:
		if conversion.get("redeem"):
			return conversion["redeem"]
	return None


def points_value(points: int, rule: dict | None) -> float | None:
	"""
	Rupee value of some points by the merchant's rule ("points" points = "amount").

	Parameters:
	        points (int, required): Points.
	        rule (dict, optional): Redeem rule from Zithara.

	Returns:
	        float | None: Value, or None when Zithara sent no usable rule.
	"""
	if not rule or not flt(rule.get("points")):
		return None
	return flt(points) * flt(rule.get("amount")) / flt(rule["points"])


def max_points_for(amount: float, rule: dict | None) -> int | None:
	"""
	Most points whose value fits in an amount (the invoice total).

	Parameters:
	        amount (float, required): Amount the discount must not exceed.
	        rule (dict, optional): Redeem rule from Zithara.

	Returns:
	        int | None: Points, or None when Zithara sent no usable rule.
	"""
	if not rule or not flt(rule.get("amount")) or not flt(rule.get("points")):
		return None
	return int(flt(amount) * flt(rule["points"]) / flt(rule["amount"]))


def ensure_points_fit(customer: str, store: str, points: int, payable: float) -> None:
	"""
	Before any OTP: the customer must have the points, and their value must fit
	in the invoice. Points redeemed beyond the invoice total would be deducted
	on Zithara but could not be given as a discount.

	Parameters:
	        customer (str, required): Customer name.
	        store (str, required): Zithara Store to ask as.
	        points (int, required): Points to redeem.
	        payable (float, required): Invoice grand total.

	Returns:
	        None
	"""
	try:
		balance = get_points(customer, store)
	except ZitharaError as error:
		frappe.throw(_("Could not read the customer's points from Zithara: {0}").format(error))
	if points > cint(balance["points"]):
		frappe.throw(_("The customer has only {0} points").format(balance["points"]))
	value = points_value(points, balance["redeem_rule"])
	if value is not None and value > flt(payable) + 0.01:
		frappe.throw(
			_("{0} points are worth {1}, more than this invoice ({2}). Redeem at most {3} points.").format(
				points,
				frappe.format(value, {"fieldtype": "Currency"}),
				frappe.format(payable, {"fieldtype": "Currency"}),
				max_points_for(payable, balance["redeem_rule"]),
			)
		)


def active_store(store: str | None) -> str:
	"""
	The store to act as: the given one, else the default store. Must be Active.

	Parameters:
	        store (str, optional): Zithara Store name.

	Returns:
	        str: Active Zithara Store name.
	"""
	store = store or frappe.get_cached_doc("Zithara Settings").default_store
	if not store or frappe.db.get_value("Zithara Store", store, "status") != "Active":
		frappe.throw(_("No active Zithara Store to check loyalty points with"))
	return store
