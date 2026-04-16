# coap-demo/module_c_degradation/server.py

"""
Module C — CoAP Degradation Test Server
Serves sensor data for CON and NON message type resilience tests.

Usage:
    python server.py --port 5683
"""

import asyncio
import argparse
import json
from typing import Any

import aiocoap
import aiocoap.resource as resource


# ── Sensor data ───────────────────────────────────────────────────────────────

SENSOR_PAYLOAD: dict[str, Any] = {
    'device':      'degradation-node-01',
    'temperature': 22.5,
    'humidity':    58.3,
    'uptime':      3600,
}


# ── Resources ─────────────────────────────────────────────────────────────────

class SensorResource(resource.Resource):
    """Returns JSON sensor data on GET. Used for both CON and NON tests."""

    def get_link_description(self) -> dict[str, Any]:
        """Advertise resource type in .well-known/core."""
        desc: dict[str, Any] = super().get_link_description()
        desc['rt'] = 'sensor.combined'
        desc['ct'] = '50'
        return desc

    async def render_get(self, request: aiocoap.Message) -> aiocoap.Message:
        payload: bytes = json.dumps(SENSOR_PAYLOAD).encode('utf-8')
        return aiocoap.Message(
            payload=payload,
            content_format=50,
        )


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(port: int) -> None:
    """Start the CoAP degradation test server on the given port."""
    root: resource.Site = resource.Site()

    root.add_resource(
        ['.well-known', 'core'],
        resource.WKCResource(root.get_resources_as_linkheader),
    )
    root.add_resource(['sensor'], SensorResource())

    print(f'[CoAP-C] Degradation server listening on coap://127.0.0.1:{port}/sensor')

    await aiocoap.Context.create_server_context(root, bind=('127.0.0.1', port))
    await asyncio.get_event_loop().create_future()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CoAP Degradation Test Server')
    parser.add_argument('--port', type=int, default=5690, help='UDP port to listen on')
    args = parser.parse_args()

    asyncio.run(main(args.port))