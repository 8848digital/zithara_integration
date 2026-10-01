# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Local fake of the Zithara POS API, for testing without real credentials.
Standard library only. Not shipped with the app; dev/testing use only.

    python3 scripts/mock_zithara/server.py            # http://127.0.0.1:9099
    python3 scripts/mock_zithara/server.py --store my-id:my-secret --port 9099

Then set Zithara Settings > Base URL to http://127.0.0.1:9099 (developer mode only).

Control endpoints (no auth):
    GET  /__mock/state                     orders and last requests received
    POST /__mock/fail?status=503&count=3   next 3 API calls fail with 503
    POST /__mock/expire-tokens             every token becomes invalid (401)
    POST /__mock/reset                     forget everything

Loyalty: every customer starts with 5000 points; the OTP is 123456 (--otp to change).
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from loyalty import MockLoyalty
from state import MockState

DEFAULT_STORES = ["test-client-1:test-secret-1", "test-client-2:test-secret-2"]
# Shown at / : the mock is an API for the app, there is no login page.
HELP = {
	"message": "Mock Zithara POS API is running. There is no login: the ERPNext app calls it with store credentials.",
	"see_received_orders": "/__mock/state",
	"valid_stores": [pair.split(":")[0] for pair in DEFAULT_STORES],
	"controls": {
		"POST /__mock/fail?status=503&count=2": "next 2 API calls fail",
		"POST /__mock/expire-tokens": "force token refresh",
		"POST /__mock/reset": "forget everything",
	},
	"loyalty": {
		"start_points": 5000,
		"otp": "123456 (change with --otp)",
	},
}


class ZitharaHandler(BaseHTTPRequestHandler):
	"""Routes Zithara endpoints and the /__mock control endpoints."""

	state: MockState
	loyalty: MockLoyalty

	def do_GET(self):
		"""Handle a GET request."""
		self.__route("GET")

	def do_POST(self):
		"""Handle a POST request."""
		self.__route("POST")

	def __route(self, method: str) -> None:
		"""
		Dispatch one request to the token, order, cancel or control handler.

		Parameters:
		        method (str, required): "GET" or "POST".

		Returns:
		        None
		"""
		url = urlparse(self.path)
		path = url.path.rstrip("/")
		if path in ("", "/__mock"):
			return self.__send(200, HELP)
		if path.startswith("/__mock"):
			return self.__control(method, path, parse_qs(url.query))
		body = self.__body()

		if method == "GET" and path == "/v1/generate-access-token":
			status, reply = self.state.issue_token(
				self.headers.get("client_id", ""), self.headers.get("client_secret", "")
			)
			return self.__reply(status, reply, method, path)

		fault = self.state.take_fault()
		if fault:
			return self.__reply(fault, {"success": False, "message": f"injected {fault}"}, method, path)

		authorization = self.headers.get("Authorization", "")
		client_id = self.state.client_for(authorization)
		if not client_id:
			hint = (
				" (send the raw token, not 'Bearer <token>')" if authorization.startswith("Bearer") else ""
			)
			return self.__reply(401, {"success": False, "message": f"Unauthorized{hint}"}, method, path)

		warnings = []
		if method == "POST" and path == "/v1/order":
			status, reply, warnings = self.state.create_order(client_id, body)
		elif method == "POST" and path == "/v1/order/cancel":
			status, reply = self.state.cancel_order(client_id, body)
		elif method == "GET" and path == "/v1/customer/loyalty-points":
			query = {key: values[0] for key, values in parse_qs(url.query).items()}
			status, reply = self.loyalty.points(client_id, query)
		elif method == "POST" and path == "/v1/initiate-redemption":
			status, reply = self.loyalty.initiate(client_id, body)
		elif method == "POST" and path == "/v1/complete-redemption":
			status, reply = self.loyalty.complete(client_id, body)
		elif method == "GET" and path.startswith("/v1/order/"):
			status, reply = self.state.get_order(client_id, unquote(path[len("/v1/order/") :]))
		else:
			status, reply = 404, {"success": False, "message": f"No mock for {method} {path}"}
		self.__reply(status, reply, method, path, client_id, body, warnings)

	def __control(self, method: str, path: str, query: dict) -> None:
		"""
		Handle /__mock/* endpoints (state, fault injection, token expiry, reset).

		Parameters:
		        method (str, required): HTTP method.
		        path (str, required): Request path.
		        query (dict, required): Parsed query string.

		Returns:
		        None
		"""
		if path == "/__mock/state":
			return self.__send(200, {**self.state.snapshot(), "loyalty": self.loyalty.snapshot()})
		if method != "POST":
			return self.__send(405, {"message": "use POST"})
		if path == "/__mock/fail":
			status = int(query.get("status", ["503"])[0])
			count = int(query.get("count", ["1"])[0])
			self.state.add_fault(status, count)
			return self.__send(200, {"message": f"next {count} call(s) fail with {status}"})
		if path == "/__mock/expire-tokens":
			self.state.expire_tokens()
			return self.__send(200, {"message": "all tokens expired"})
		if path == "/__mock/reset":
			self.state.reset()
			self.loyalty.__init__(self.loyalty.otp)
			return self.__send(200, {"message": "reset"})
		self.__send(404, {"message": "unknown control endpoint"})

	def __body(self) -> dict:
		"""
		Read the JSON request body.

		Returns:
		        dict: Parsed body, {} when empty or not JSON.
		"""
		length = int(self.headers.get("Content-Length") or 0)
		if not length:
			return {}
		try:
			return json.loads(self.rfile.read(length))
		except ValueError:
			return {}

	def __reply(self, status, reply, method, path, client_id="", body=None, warnings=()) -> None:
		"""
		Log the call (console + /__mock/state) and send the reply.

		Parameters:
		        status (int, required): HTTP status.
		        reply (dict | list, required): JSON reply.
		        method (str, required): HTTP method.
		        path (str, required): Request path.
		        client_id (str, optional): Store the call was made as.
		        body (dict, optional): Request body, kept for inspection.
		        warnings (list, optional): Payload warnings to report.

		Returns:
		        None
		"""
		entry = {
			"at": time.strftime("%H:%M:%S"),
			"call": f"{method} {path}",
			"client_id": client_id or self.headers.get("client_id", ""),
			"status": status,
			"reply": reply,
			"warnings": list(warnings),
		}
		if body:
			entry["body"] = body
		self.state.log.append(entry)
		print(f"[{entry['at']}] {method} {path} -> {status}", flush=True)
		if isinstance(reply, dict) and (status >= 400 or reply.get("success") is False):
			print(f"    error: {reply.get('message')}", flush=True)
		for warning in warnings:
			print(f"    warning: {warning}", flush=True)
		self.__send(status, reply)

	def __send(self, status: int, reply) -> None:
		"""
		Write a JSON response.

		Parameters:
		        status (int, required): HTTP status.
		        reply (dict | list, required): JSON body.

		Returns:
		        None
		"""
		data = json.dumps(reply, indent=1, default=str).encode()
		self.send_response(status)
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(data)))
		self.end_headers()
		self.wfile.write(data)

	def log_message(self, *args):
		"""Silence the default access log; __reply prints a shorter one."""


def main() -> None:
	"""Parse arguments and serve the mock until Ctrl+C."""
	parser = argparse.ArgumentParser(description="Local fake Zithara POS API")
	parser.add_argument("--host", default="127.0.0.1")
	parser.add_argument("--port", type=int, default=9099)
	parser.add_argument("--store", action="append", help="valid client_id:client_secret (repeatable)")
	parser.add_argument("--token-ttl", type=int, default=3600, help="expires_in seconds")
	parser.add_argument("--otp", default="123456", help="OTP accepted by complete-redemption")
	args = parser.parse_args()

	credentials = dict(pair.split(":", 1) for pair in (args.store or DEFAULT_STORES))
	ZitharaHandler.state = MockState(credentials, args.token_ttl)
	ZitharaHandler.loyalty = MockLoyalty(args.otp)
	server = ThreadingHTTPServer((args.host, args.port), ZitharaHandler)
	print(
		f"Mock Zithara on http://{args.host}:{args.port}  stores: {', '.join(credentials)}", flush=True
	)
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		pass


if __name__ == "__main__":
	main()
