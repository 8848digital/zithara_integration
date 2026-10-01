# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Mock loyalty points: balance lookup and OTP redemption. Every customer starts
with START_POINTS; the OTP is always the one given on the command line. As on
real Zithara (per the previous backend's notes), a wrong OTP uses up the session.
"""

import secrets
import threading

START_POINTS = 5000
REDEEM_RULE = {
	"points": 100,
	"amount": 100,
	"is_min_limit": True,
	"min_redeem_limit": 100,
	"is_max_limit": True,
	"max_redeem_limit": 5000,
}
# Zithara's identity keys per endpoint (the casing really differs).
IDENTITY_KEYS = {
	"points": ("phone", "platformCustomerId", "email", "customerId"),
	"initiate": ("phone_number", "platform_Customer_Id", "email", "customer_id"),
	"complete": ("phone_number", "platform_customer_id", "email", "customer_id"),
}


class MockLoyalty:
	"""Points balances and OTP sessions, per store."""

	def __init__(self, otp: str):
		"""
		Start with no balances or sessions.

		Parameters:
		        otp (str, required): The OTP every redemption accepts.

		Returns:
		        None
		"""
		self.otp = otp
		self.lock = threading.Lock()
		self.balances = {}  # (client_id, identity) -> points
		self.sessions = {}  # session_id -> session dict

	def points(self, client_id: str, query: dict) -> tuple[int, dict]:
		"""
		GET /v1/customer/loyalty-points.

		Parameters:
		        client_id (str, required): Calling store.
		        query (dict, required): Query parameters (one identity key).

		Returns:
		        tuple[int, dict]: HTTP status and reply.
		"""
		identity = self.__identity(query, "points")
		if not identity:
			return 200, self.__error("one of phone, platformCustomerId, email, customerId is required")
		points = self.balances.get((client_id, identity), START_POINTS)
		data = {
			"points": points,
			"customer_id": identity,
			"config": {"conversion": [{"redeem": REDEEM_RULE}]},
		}
		return 200, {"success": True, "status": 200, "data": data}

	def initiate(self, client_id: str, body: dict) -> tuple[int, dict]:
		"""
		POST /v1/initiate-redemption: validate and "send" an OTP.

		Parameters:
		        client_id (str, required): Calling store.
		        body (dict, required): {points, one identity key}.

		Returns:
		        tuple[int, dict]: HTTP status and reply.
		"""
		identity = self.__identity(body, "initiate")
		if not identity:
			return 200, self.__error("phone_number or platform_Customer_Id is required")
		points = int(body.get("points") or 0)
		balance = self.balances.get((client_id, identity), START_POINTS)
		if points < REDEEM_RULE["min_redeem_limit"] or points > REDEEM_RULE["max_redeem_limit"]:
			return 200, self.__error(
				f"points must be between {REDEEM_RULE['min_redeem_limit']} and {REDEEM_RULE['max_redeem_limit']}"
			)
		if points > balance:
			return 200, self.__error(f"insufficient points: balance {balance}")
		session_id = secrets.token_hex(8)
		with self.lock:
			self.sessions[session_id] = {
				"client_id": client_id,
				"identity": identity,
				"points": points,
				"status": "otp_sent",
			}
		data = {"message": "OTP sent successfully", "sentTo": identity, "sessionId": session_id}
		return 200, {"success": True, "status": 200, "data": data}

	def complete(self, client_id: str, body: dict) -> tuple[int, dict]:
		"""
		POST /v1/complete-redemption: check the OTP, deduct points, return the value.

		Parameters:
		        client_id (str, required): Calling store.
		        body (dict, required): {points, otp, sessionId?, one identity key}.

		Returns:
		        tuple[int, dict]: HTTP status and reply.
		"""
		identity = self.__identity(body, "complete")
		with self.lock:
			session = self.__open_session(client_id, identity, body.get("sessionId"))
			if not session:
				return 200, self.__error("no pending redemption; initiate again")
			if int(body.get("points") or 0) != session["points"]:
				return 200, self.__error("points differ from the initiated redemption")
			if str(body.get("otp") or "") != self.otp:
				session["status"] = "otp_failed"
				return 200, self.__error("Invalid OTP; initiate again")
			session["status"] = "redeemed"
			key = (client_id, identity)
			self.balances[key] = self.balances.get(key, START_POINTS) - session["points"]
		amount = session["points"] * REDEEM_RULE["amount"] / REDEEM_RULE["points"]
		return 200, {"success": True, "status": 200, "data": {"amount": amount}}

	def snapshot(self) -> dict:
		"""
		Balances and sessions for /__mock/state.

		Returns:
		        dict: {"balances": [...], "sessions": {...}}.
		"""
		balances = [
			{"client_id": key[0], "customer": key[1], "points": points}
			for key, points in self.balances.items()
		]
		return {"balances": balances, "sessions": self.sessions}

	def __open_session(
		self, client_id: str, identity: str | None, session_id: str | None
	) -> dict | None:
		"""
		The session to complete: by id when given, else the customer's latest open one.

		Parameters:
		        client_id (str, required): Calling store.
		        identity (str, optional): Customer identity.
		        session_id (str, optional): sessionId from initiate.

		Returns:
		        dict | None: Open session, or None.
		"""
		if session_id:
			session = self.sessions.get(session_id)
			return (
				session
				if session and session["status"] == "otp_sent" and session["client_id"] == client_id
				else None
			)
		for session in reversed(list(self.sessions.values())):
			if (session["client_id"], session["identity"], session["status"]) == (
				client_id,
				identity,
				"otp_sent",
			):
				return session
		return None

	@staticmethod
	def __identity(source: dict, endpoint: str) -> str | None:
		"""
		The first identity value present, using that endpoint's key names.

		Parameters:
		        source (dict, required): Query or body.
		        endpoint (str, required): "points", "initiate" or "complete".

		Returns:
		        str | None: Identity value.
		"""
		for key in IDENTITY_KEYS[endpoint]:
			if source.get(key):
				return str(source[key])
		return None

	@staticmethod
	def __error(message: str) -> dict:
		"""
		Zithara-style business error (HTTP 200, success false).

		Parameters:
		        message (str, required): Error text.

		Returns:
		        dict: Error reply.
		"""
		return {"success": False, "status": 400, "message": message}
