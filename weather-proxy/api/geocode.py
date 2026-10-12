"""Vercel serverless proxy for Nominatim (geocoding).

Render's free-tier shared egress IPs get 429s from Nominatim; this
forwarder runs on Vercel's clean egress and returns Nominatim's JSON
untouched.

POST /api/geocode  {"q": "Chicago, IL"}  -> 200 with Nominatim JSON list
"""
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import urllib.request


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            params = {"q": body["q"], "format": "json", "limit": 1}
            url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(
                url, headers={"User-Agent": "HaulSafe-Proxy/1.0 (candidate project)"}
            )
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:  # noqa: BLE001 - proxy must never leak tracebacks
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"geocode proxy failed: {e}"}).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *args):
        pass
