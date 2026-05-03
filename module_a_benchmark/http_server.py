# coap-demo/module_a_benchmark/http_server.py

"""
Module A — HTTP Benchmark Server
Serves identical sensor data as the CoAP server for fair comparison.

Usage:
    python http_server.py --port 8080
    python http_server.py --port 8080 --host 0.0.0.0   # aceita ligações externas
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
    client = request.remote
    print(f'[HTTP] ← GET /sensor from {client}', flush=True)

    return web.Response(
        text=json.dumps(SENSOR_PAYLOAD),
        content_type='application/json',
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def build_app() -> web.Application:
    app: web.Application = web.Application()
    app.router.add_get('/sensor', handle_sensor)
    return app


def main(host: str, port: int) -> None:
    print(f'[HTTP] Listening on http://{host}:{port}/sensor', flush=True)
    print(f'[HTTP] Waiting for requests...', flush=True)
    app: web.Application = build_app()
    web.run_app(app, host=host, port=port, print=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HTTP Benchmark Server')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='Bind address (use 0.0.0.0 to accept external connections)')
    args = parser.parse_args()

    main(args.host, args.port)