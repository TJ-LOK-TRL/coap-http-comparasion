# coap-demo/module_b_discovery/server.py

"""
Module B — CoAP Sensor Server (Realistic / WSL)
Binds to a unique IP address on a dummy network interface (simulating a real
IoT device with its own IP on a Wi-Fi network). Joins the CoAP multicast group
224.0.1.187 so it can be discovered via multicast GET /.well-known/core.

Each instance represents a physically separate IoT device. All instances use
the standard CoAP port 5683, differentiated only by IP — exactly as in a real
Wi-Fi deployment with ESP32s or Raspberry Pis.

Must be run inside WSL or Linux. Requires the dummy interface to already exist
(created by setup.sh or run_demo.py).

Usage:
    python3 server.py --ip 192.168.100.1 --device temperature
    python3 server.py --ip 192.168.100.2 --device humidity
    python3 server.py --ip 192.168.100.3 --device led
"""

import asyncio
import argparse
import random
import socket
import struct
from typing import Any

import aiocoap
import aiocoap.resource as resource


# ── Constants ─────────────────────────────────────────────────────────────────

COAP_PORT:            int = 5683
COAP_MULTICAST_ADDR:  str = '224.0.1.187'   # RFC 7252 — CoAP all-nodes multicast


# ── Multicast join ────────────────────────────────────────────────────────────

def join_multicast_group(local_ip: str) -> None:
    """
    Join the CoAP multicast group 224.0.1.187 on the interface with the given IP.
    This makes the server respond to multicast discovery requests sent to that address.
    Uses a raw socket to issue the IP_ADD_MEMBERSHIP socket option.
    """
    sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # IP_ADD_MEMBERSHIP requires: multicast group IP + local interface IP (both as 4-byte packed)
    group:     bytes = socket.inet_aton(COAP_MULTICAST_ADDR)
    interface: bytes = socket.inet_aton(local_ip)
    mreq:      bytes = struct.pack('4s4s', group, interface)

    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.close()
    print(f'  Joined multicast group {COAP_MULTICAST_ADDR} on interface {local_ip}')


# ── Resources ─────────────────────────────────────────────────────────────────

class TemperatureResource(resource.Resource):
    """Simulates a temperature sensor. rt=sensor.temperature"""

    def get_link_description(self) -> dict[str, Any]:
        """Advertise resource type and content format in .well-known/core."""
        desc: dict[str, Any] = super().get_link_description()
        desc['rt'] = 'sensor.temperature'
        desc['if'] = 'sensor'
        desc['ct'] = '0'
        return desc

    async def render_get(self, request: aiocoap.Message) -> aiocoap.Message:
        value: float = round(random.uniform(18.0, 35.0), 1)
        payload: bytes = f'temperature={value}C'.encode()
        return aiocoap.Message(payload=payload)


class HumidityResource(resource.Resource):
    """Simulates a humidity sensor. rt=sensor.humidity"""

    def get_link_description(self) -> dict[str, Any]:
        """Advertise resource type and content format in .well-known/core."""
        desc: dict[str, Any] = super().get_link_description()
        desc['rt'] = 'sensor.humidity'
        desc['if'] = 'sensor'
        desc['ct'] = '0'
        return desc

    async def render_get(self, request: aiocoap.Message) -> aiocoap.Message:
        value: float = round(random.uniform(30.0, 90.0), 1)
        payload: bytes = f'humidity={value}%'.encode()
        return aiocoap.Message(payload=payload)


class LedResource(resource.ObservableResource):
    """Simulates a controllable LED (GET + PUT). rt=actuator.led"""

    def __init__(self) -> None:
        super().__init__()
        self.state: str = 'off'

    def get_link_description(self) -> dict[str, Any]:
        """Advertise resource type and content format in .well-known/core."""
        desc: dict[str, Any] = super().get_link_description()
        desc['rt'] = 'actuator.led'
        desc['if'] = 'actuator'
        desc['ct'] = '0'
        return desc

    async def render_get(self, request: aiocoap.Message) -> aiocoap.Message:
        payload: bytes = f'led={self.state}'.encode()
        return aiocoap.Message(payload=payload)

    async def render_put(self, request: aiocoap.Message) -> aiocoap.Message:
        value: str = request.payload.decode().strip().lower()
        if value in ('on', 'off'):
            self.state = value
            return aiocoap.Message(code=aiocoap.CHANGED, payload=f'led={self.state}'.encode())
        return aiocoap.Message(code=aiocoap.BAD_REQUEST, payload=b'use on or off')


class UptimeResource(resource.Resource):
    """Returns a fake device uptime in seconds. rt=device.uptime"""

    def get_link_description(self) -> dict[str, Any]:
        """Advertise resource type and content format in .well-known/core."""
        desc: dict[str, Any] = super().get_link_description()
        desc['rt'] = 'device.uptime'
        desc['if'] = 'info'
        desc['ct'] = '0'
        return desc

    async def render_get(self, request: aiocoap.Message) -> aiocoap.Message:
        value: int = random.randint(100, 99999)
        payload: bytes = f'uptime={value}s'.encode()
        return aiocoap.Message(payload=payload)


# ── Types ─────────────────────────────────────────────────────────────────────

DeviceProfile = dict[str, Any]

# ── Device profiles ───────────────────────────────────────────────────────────

DEVICE_PROFILES: dict[str, DeviceProfile] = {
    'temperature': {
        'resources': {
            'sensors/temperature': TemperatureResource(),
            'device/uptime':       UptimeResource(),
        },
        'label': 'Temperature Sensor Node',
    },
    'humidity': {
        'resources': {
            'sensors/humidity': HumidityResource(),
            'device/uptime':    UptimeResource(),
        },
        'label': 'Humidity Sensor Node',
    },
    'led': {
        'resources': {
            'actuators/led':       LedResource(),
            'sensors/temperature': TemperatureResource(),
            'device/uptime':       UptimeResource(),
        },
        'label': 'LED + Temp Node',
    },
}


# ── Main ─────────────────────────────────────────────────────────────────────

async def main(ip: str, device: str) -> None:
    """Start a CoAP server on a unique IP, joining the CoAP multicast group."""
    profile: DeviceProfile | None = DEVICE_PROFILES.get(device)
    if not profile:
        print(f'Unknown device \'{device}\'. Choose: {list(DEVICE_PROFILES.keys())}')
        return

    root: resource.Site = resource.Site()

    root.add_resource(
        ['.well-known', 'core'],
        resource.WKCResource(root.get_resources_as_linkheader),
    )

    res_map: dict[str, resource.Resource] = profile['resources']
    for path, res in res_map.items():
        root.add_resource(path.split('/'), res)

    print(f'[{device.upper()}] Starting — {profile["label"]}')
    print(f'[{device.upper()}] Binding to coap://{ip}:{COAP_PORT}')
    print(f'[{device.upper()}] Resources: {list(res_map.keys())}')

    # Join multicast group so this server responds to 224.0.1.187:5683
    join_multicast_group(ip)

    # Bind to the unique IP on standard CoAP port 5683
    await aiocoap.Context.create_server_context(root, bind=(ip, COAP_PORT))
    await asyncio.get_event_loop().create_future()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CoAP Sensor Server (Realistic)')
    parser.add_argument('--ip',     type=str, required=True,          help='IP address to bind to (e.g. 192.168.100.1)')
    parser.add_argument('--device', type=str, default='temperature',  help='Device profile: temperature | humidity | led')
    args = parser.parse_args()

    asyncio.run(main(args.ip, args.device))