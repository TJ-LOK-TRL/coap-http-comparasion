# coap-demo/module_a_benchmark/http_server.py

"""
Module A — HTTP Benchmark Server

Endpoints:
    /sensor          → real JSON sensor payload (fixed)
    /data?size=<n>   → synthetic payload of exactly n bytes

Usage:
    python http_server.py --port 8080
    python http_server.py --port 8080 --host 0.0.0.0
"""

import argparse
import json
import os
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
    """Return fixed JSON sensor data on GET /sensor."""
    print(f'[HTTP] ← GET /sensor from {request.remote}', flush=True)
    return web.Response(
        text=json.dumps(SENSOR_PAYLOAD),
        content_type='application/json',
    )


async def handle_data(request: web.Request) -> web.Response:
    """Return a synthetic payload of exactly n bytes on GET /data?size=<n>.

    Uses b'x' * size (not os.urandom) to guarantee the payload is exactly
    size bytes without any encoding or JSON overhead.
    """
    try:
        size = int(request.rel_url.query.get('size', 64))
    except ValueError:
        size = 64

    print(f'[HTTP] ← GET /data?size={size} from {request.remote}', flush=True)
    payload: bytes = b'x' * size  # pure fixed bytes — no encoding overhead
    return web.Response(body=payload, content_type='application/octet-stream')


# ── Main ──────────────────────────────────────────────────────────────────────

def build_app() -> web.Application:
    app: web.Application = web.Application()
    app.router.add_get('/sensor', handle_sensor)
    app.router.add_get('/data',   handle_data)
    return app


def main(host: str, port: int) -> None:
    print(f'[HTTP] Listening on http://{host}:{port}', flush=True)
    print(f'[HTTP]   /sensor        → fixed JSON sensor payload', flush=True)
    print(f'[HTTP]   /data?size=N   → synthetic N-byte payload', flush=True)
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