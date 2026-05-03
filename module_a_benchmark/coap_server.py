# coap-demo/module_a_benchmark/coap_server.py

"""
Module A — CoAP Benchmark Server

Endpoints:
    /sensor          → real JSON sensor payload (fixed)
    /data?size=<n>   → synthetic payload of exactly n bytes

Usage:
    python coap_server.py --port 5683
    python coap_server.py --port 5683 --host 0.0.0.0
"""

import asyncio
import argparse
import json
import os
from typing import Any

import aiocoap
import aiocoap.resource as resource


# ── Sensor data ───────────────────────────────────────────────────────────────

SENSOR_PAYLOAD: dict[str, Any] = {
    'device':      'sensor-node-01',
    'temperature': 22.5,
    'humidity':    58.3,
    'uptime':      3600,
    'unit_temp':   'C',
    'unit_hum':    '%',
}


# ── Resources ─────────────────────────────────────────────────────────────────

class SensorResource(resource.Resource):
    """Returns fixed JSON sensor data on GET /sensor."""

    def get_link_description(self) -> dict[str, Any]:
        desc: dict[str, Any] = super().get_link_description()
        desc['rt'] = 'sensor.combined'
        desc['ct'] = '50'
        return desc

    async def render_get(self, request: aiocoap.Message) -> aiocoap.Message:
        client = getattr(request.remote, 'hostinfo', str(request.remote))
        print(f'[CoAP] ← GET /sensor from {client}', flush=True)

        payload: bytes = json.dumps(SENSOR_PAYLOAD).encode('utf-8')
        return aiocoap.Message(payload=payload, content_format=50)


class DataResource(resource.Resource):
    """Returns a synthetic payload of exactly n bytes on GET /data?size=<n>.

    Uses b'x' * size (not os.urandom) to guarantee the payload is exactly
    size bytes without any encoding or JSON overhead.
    """

    async def render_get(self, request: aiocoap.Message) -> aiocoap.Message:
        client = getattr(request.remote, 'hostinfo', str(request.remote))

        # Parse ?size= from the URI query string
        size = 64  # default
        if request.opt.uri_query:
            for param in request.opt.uri_query:
                if param.startswith('size='):
                    try:
                        size = int(param.split('=', 1)[1])
                    except ValueError:
                        pass

        print(f'[CoAP] ← GET /data?size={size} from {client}', flush=True)
        payload: bytes = b'x' * size  # pure fixed bytes — no encoding overhead
        return aiocoap.Message(payload=payload, content_format=42)  # 42 = application/octet-stream


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(host: str, port: int) -> None:
    root: resource.Site = resource.Site()

    root.add_resource(['.well-known', 'core'],
                      resource.WKCResource(root.get_resources_as_linkheader))
    root.add_resource(['sensor'], SensorResource())
    root.add_resource(['data'],   DataResource())

    await aiocoap.Context.create_server_context(root, bind=(host, port))

    print(f'[CoAP] Listening on coap://{host}:{port}', flush=True)
    print(f'[CoAP]   /sensor        → fixed JSON sensor payload', flush=True)
    print(f'[CoAP]   /data?size=N   → synthetic N-byte payload', flush=True)
    print(f'[CoAP] Waiting for requests...', flush=True)

    await asyncio.get_event_loop().create_future()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CoAP Benchmark Server')
    parser.add_argument('--port', type=int, default=5683)
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='Bind address (use 0.0.0.0 to accept external connections)')
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port))