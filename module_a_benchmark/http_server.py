# coap-demo/module_a_benchmark/http_server.py

"""
Module A — HTTP Benchmark Server
Serves identical sensor data as the CoAP server for fair comparison.

Usage:
    python http_server.py --port 8080
"""

import argparse
import json
from typing import Any

from aiohttp import web


# ── Sensor data ───────────────────────────────────────────────────────────────

SENSOR_PAYLOAD: dict[str, Any] = {
    'device':      'sensor-node-01',
    'temperature': 22.5,
    'humidity':    58.3,
    'uptime':      3600,
    'unit_temp':   'C',
    'unit_hum':    '%',
}


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_sensor(request: web.Request) -> web.Response:
    """Return JSON sensor data on GET /sensor."""
    return web.Response(
        text=json.dumps(SENSOR_PAYLOAD),
        content_type='application/json',
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def build_app() -> web.Application:
    """Create and configure the aiohttp application."""
    app: web.Application = web.Application()
    app.router.add_get('/sensor', handle_sensor)
    return app


def main(port: int) -> None:
    """Start the HTTP benchmark server on the given port."""
    print(f'[HTTP] Benchmark server listening on http://127.0.0.1:{port}/sensor')
    app: web.Application = build_app()
    web.run_app(app, host='127.0.0.1', port=port, print=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HTTP Benchmark Server')
    parser.add_argument('--port', type=int, default=8080, help='TCP port to listen on')
    args = parser.parse_args()

    main(args.port)