"""Vercel serverless proxy for Open-Meteo.

Why: Render's free-tier shared egress IPs get 429s from Open-Meteo, which
would 502 every trip plan. This tiny forwarder runs on Vercel's clean
egress and returns Open-Meteo's JSON untouched — all risk logic stays
in the Django backend.

POST /api/weather  {"latitude": "1.0,2.0", "longitude": "3.0,4.0"}
-> 200 with Open-Meteo's forecast JSON
"""
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import urllib.request

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            params = {
                "latitude": body["latitude"],
                "longitude": body["longitude"],
                "hourly": "wind_speed_10m,precipitation,snowfall",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "temperature_unit": "fahrenheit",
                "forecast_days": 3,
                "timezone": "UTC",
            }
            url = OPEN_METEO + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": "HaulSafe-Proxy/1.0"})
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
            self.wfile.write(json.dumps({"error": f"weather proxy failed: {e}"}).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *args):  # keep Vercel logs quiet
        pass
