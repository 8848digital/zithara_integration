# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Canned Zithara replies for Test Mode: no network, no token call. Shapes follow
the replies Zithara returned on its dev sandbox.
"""

import frappe

from zithara_integration.zithara_core.services.client_response import ZitharaError

TOKEN = "test-mode-token"
TEST_POINTS = 5000
TEST_OTP = "123456"


def reply(method: str, path: str, payload: dict | None = None) -> dict | list:
	"""
	Return the reply Zithara would give for this call.

	Parameters:
	        method (str, required): "GET" or "POST".
	        path (str, required): Endpoint path.
	        payload (dict, optional): JSON body.

	Returns:
	        dict | list: Fake Zithara reply.
	"""
	payload = payload or {}
	if path.endswith("/order/cancel"):
		return __cancel_reply()
	if method == "POST" and path.endswith("/order"):
		return {
			"status": 201,
			"message": "order created",
			"orderId": f"TEST-{frappe.generate_hash(length=8)}",
		}
	if "/loyalty-points" in path or "redemption" in path:
		return __loyalty_reply(path, payload)
	if method == "GET" and "/order/" in path:
		return [{"platform_order_id": path.rsplit("/", 1)[-1], "status": "paid", "points_credited": 0}]
	return {"success": True}


def __cancel_reply() -> dict:
	"""
	Fake Cancel Order reply (points reversed and re-credited).

	Returns:
	        dict: Zithara-shaped cancel reply.
	"""
	return {
		"success": True,
		"message": "order cancelled",
		"addedResult": {"success": True},
		"deductedResult": {"success": True, "data": {"amount": 0}, "remainingPoints": 0},
		"points_deducted": 0,
	}


def __loyalty_reply(path: str, payload: dict) -> dict:
	"""
	Fake loyalty replies: 5000 points, 1 point = 1 rupee, OTP is always 123456.

	Parameters:
	        path (str, required): Endpoint path.
	        payload (dict, required): JSON body.

	Returns:
	        dict: Zithara-shaped loyalty reply.
	"""
	if "/loyalty-points" in path:
		rule = {"points": 1, "amount": 1, "is_min_limit": False, "is_max_limit": False}
		data = {
			"points": TEST_POINTS,
			"customer_id": "TEST",
			"config": {"conversion": [{"redeem": rule}]},
		}
		return {"success": True, "status": 200, "data": data}
	if "initiate" in path:
		data = {"message": "OTP sent successfully", "sentTo": "test", "sessionId": "test-session"}
		return {"success": True, "status": 200, "data": data}
	if payload.get("otp") != TEST_OTP:
		reply = {"success": False, "status": 400, "message": "Invalid OTP"}
		raise ZitharaError(400, reply["message"], reply)
	return {"success": True, "status": 200, "data": {"amount": payload.get("points")}}
