"""Tiny JSON API for the ai-workspace demo (Python standard library only)."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

VERSION = "1.4.0"


def route(path):
    if path == "/health":
        return 200, {"ok": True}
    return 404, {"error": "not found"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, body = route(self.path)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
