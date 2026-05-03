# coap-demo/module_a_benchmark/coap_server.py

"""
Module A — CoAP Benchmark Server
Serves identical sensor data as the HTTP server for fair comparison.

Usage:
    python coap_server.py --port 5683
    python coap_server.py --port 5683 --host 0.0.0.0   # aceita ligações externas
"""

import asyncio
import argparse
import json
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
    """Returns JSON sensor data on GET."""

    def get_link_description(self) -> dict[str, Any]:
        desc: dict[str, Any] = super().get_link_description()
        desc['rt'] = 'sensor.combined'
        desc['ct'] = '50'
        return desc

    async def render_get(self, request: aiocoap.Message) -> aiocoap.Message:
        client = getattr(request.remote, 'hostinfo', str(request.remote))
        print(f'[CoAP] ← GET /sensor from {client}', flush=True)

        payload: bytes = json.dumps(SENSOR_PAYLOAD).encode('utf-8')
        return aiocoap.Message(
            payload=payload,
            content_format=50,
        )


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(host: str, port: int) -> None:
    root: resource.Site = resource.Site()

    root.add_resource(
        ['.well-known', 'core'],
        resource.WKCResource(root.get_resources_as_linkheader),
    )
    root.add_resource(['sensor'], SensorResource())

    await aiocoap.Context.create_server_context(root, bind=(host, port))

    print(f'[CoAP] Listening on coap://{host}:{port}/sensor', flush=True)
    print(f'[CoAP] Waiting for requests...', flush=True)

    await asyncio.get_event_loop().create_future()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CoAP Benchmark Server')
    parser.add_argument('--port', type=int, default=5683)
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='Bind address (use 0.0.0.0 to accept external connections)')
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port))