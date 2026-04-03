"""inject-tool HTTP server — routes requests to injector handlers."""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import injector


class Handler(BaseHTTPRequestHandler):

    def _send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _require_fields(self, data, *fields):
        missing = [f for f in fields if f not in data]
        if missing:
            self._send_json(400, {"status": "error", "message": f"Missing required fields: {', '.join(missing)}"})
            return False
        return True

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return

        if parsed.path == "/list":
            params = parse_qs(parsed.query)
            ws = params.get("workspace", [None])[0]
            ns = params.get("namespace", [None])[0]
            if not ws or not ns:
                self._send_json(400, {"status": "error", "message": "Missing workspace or namespace query param"})
                return
            try:
                result = injector.handle_list(ns, ws)
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        self._send_json(404, {"status": "error", "message": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)

        try:
            data = self._read_json()
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json(400, {"status": "error", "message": f"Invalid JSON: {e}"})
            return

        if parsed.path == "/inject":
            if not self._require_fields(data, "workspace", "namespace", "tools"):
                return
            try:
                result = injector.handle_inject(data["namespace"], data["workspace"], data["tools"])
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(400, {"status": "error", "message": str(e)})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        if parsed.path == "/remove":
            if not self._require_fields(data, "workspace", "namespace", "tools"):
                return
            try:
                result = injector.handle_remove(data["namespace"], data["workspace"], data["tools"])
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(400, {"status": "error", "message": str(e)})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        if parsed.path == "/init":
            if not self._require_fields(data, "workspace", "namespace", "configs"):
                return
            try:
                result = injector.handle_init(
                    data["namespace"], data["workspace"],
                    data["configs"], data.get("dry_run", False))
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(400, {"status": "error", "message": str(e)})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        self._send_json(404, {"status": "error", "message": "Not found"})

    def log_message(self, fmt, *args):
        print(f"[server] {fmt % args}", file=sys.stderr, flush=True)


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"inject-tool-service listening on :{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
