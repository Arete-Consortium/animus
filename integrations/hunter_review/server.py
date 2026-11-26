"""Bounded local review service. No source writes, approvals, or publication endpoints."""

from __future__ import annotations

import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from integrations.hunter_review.review import ReviewStore, SourceUnavailableError


def make_server(store: ReviewStore, token: str, host: str, port: int) -> HTTPServer:
    if len(token) < 32:
        raise ValueError("A private connector credential is required")

    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def log_message(self, *_args: object) -> None:
            pass  # Never log request headers or payloads.

        def send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self) -> bool:
            if self.headers.get("Origin"):
                self.send(403, {"error": "Browser-origin calls are not allowed"})
                return False
            candidate = self.headers.get("Authorization", "")
            if not hmac.compare_digest(candidate.encode(), f"Bearer {token}".encode()):
                self.send(401, {"error": "Unauthorized"})
                return False
            return True

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self.send(200, {"status": "ok", "mode": "review_only"})
            elif self.authorized():
                if self.path == "/v1/reviews/latest":
                    packet = store.latest()
                    self.send(200 if packet else 404, packet or {"error": "No review has run"})
                else:
                    self.send(404, {"error": "Unknown endpoint"})

        def do_POST(self) -> None:
            if not self.authorized():
                return
            if self.path != "/v1/reviews":
                self.send(404, {"error": "Unknown endpoint"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 or self.headers.get("Transfer-Encoding"):
                    self.send(413, {"error": "A bounded JSON request is required"})
                    return
                body = json.loads(self.rfile.read(length))
                if (
                    not isinstance(body, dict)
                    or set(body) != {"request_id"}
                    or not isinstance(body["request_id"], str)
                ):
                    self.send(
                        400,
                        {"error": "Only request_id is accepted; sources are operator-configured"},
                    )
                    return
                packet = store.review(body["request_id"])
                self.send(200, packet)
            except SourceUnavailableError:
                self.send(503, {"error": "Source inspection failed; previous baseline retained"})
            except (ValueError, TypeError, UnicodeError):
                self.send(400, {"error": "Invalid request or source format"})
            except Exception:
                self.send(503, {"error": "Review unavailable; inspect local service configuration"})

    return HTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    token = args.token_file.read_text().strip()
    store = ReviewStore(args.sources, args.state)
    with make_server(store, token, args.host, args.port) as server:
        print(f"Hunter review service listening on {args.host}:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
