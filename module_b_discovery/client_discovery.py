# coap-demo/module_b_discovery/client_discovery.py

"""
Module B — CoAP Multicast Discovery Client (Realistic / WSL)
Sends a single GET /.well-known/core to the CoAP multicast address 224.0.1.187
on port 5683. All CoAP servers that have joined the multicast group respond
with their resource descriptions in CoRE Link Format (RFC 6690).

This is exactly how a real IoT gateway or controller would discover devices
on a Wi-Fi network — no prior knowledge of device IPs is required.

Must be run inside WSL or Linux with the dummy interfaces set up.

Usage:
    python3 client_discovery.py --interface 192.168.100.1
"""

import asyncio
import argparse
import socket
import struct
import time
from typing import Any

import aiocoap
import aiocoap.resource as resource


# ── Constants ─────────────────────────────────────────────────────────────────

COAP_PORT:           int   = 5683
COAP_MULTICAST_ADDR: str   = '224.0.1.187'
DISCOVERY_TIMEOUT:   float = 3.0    # seconds to wait for all devices to respond

# URIs injected automatically by aiocoap — not actual device resources
_AIOCOAP_META_PREFIXES: tuple[str, ...] = (
    'https://christian.amsuess.com',
)


# ── Types ─────────────────────────────────────────────────────────────────────

ParsedResource  = dict[str, str | bool]
DiscoveryResult = dict[str, Any]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_meta_resource(uri: str) -> bool:
    """Return True if the URI is an aiocoap internal metadata entry."""
    return any(uri.startswith(prefix) for prefix in _AIOCOAP_META_PREFIXES)


def parse_link_format(payload: str) -> list[ParsedResource]:
    """Parse CoRE Link Format (RFC 6690) into a list of resource dicts."""
    resources: list[ParsedResource] = []

    for entry in payload.split(','):
        entry = entry.strip()
        if not entry:
            continue

        parts: list[str] = entry.split(';')
        uri: str = parts[0].strip('<>')

        if _is_meta_resource(uri):
            continue

        attrs: ParsedResource = {'uri': uri}
        for attr in parts[1:]:
            attr = attr.strip()
            if '=' in attr:
                k, v = attr.split('=', 1)
                attrs[k.strip()] = v.strip().strip('"')
            else:
                attrs[attr] = True

        resources.append(attrs)

    return resources


def format_table(results: list[DiscoveryResult]) -> None:
    """Pretty-print all discovered devices and their resources."""
    print()
    print('=' * 70)
    print('  CoAP MULTICAST SERVICE DISCOVERY — 224.0.1.187:5683')
    print('  GET /.well-known/core  (RFC 7252 + RFC 6690)')
    print('=' * 70)

    for r in results:
        resources: list[ParsedResource] = r.get('resources', [])
        print()
        print(f'  Device  : {r["remote_ip"]}:{r["remote_port"]}')
        print(f'  RTT     : {r["rtt_ms"]} ms')
        print(f'  Raw     : {r["raw"]}')
        print(f'  Resources ({len(resources)}):')
        for res in resources:
            uri:   str = str(res.get('uri',  '?'))
            rt:    str = str(res.get('rt',   '—'))
            iface: str = str(res.get('if',   '—'))
            ct:    str = str(res.get('ct',   '—'))
            obs:   str = ' (observable)' if res.get('obs') else ''
            print(f'    • {uri:<35} rt={rt:<22} if={iface:<10} ct={ct}{obs}')

    print()
    print('=' * 70)
    print(f'  Discovery complete: {len(results)} device(s) responded.')
    print('=' * 70)
    print()


# ── Multicast discovery ───────────────────────────────────────────────────────

class MulticastDiscovery:
    """
    Sends a CoAP multicast GET /.well-known/core and collects all responses
    within DISCOVERY_TIMEOUT seconds.

    Unlike unicast requests (one request → one response), multicast produces
    multiple responses from different source IPs. We collect them all.
    """

    def __init__(self, local_ip: str) -> None:
        self._local_ip:  str                    = local_ip
        self._results:   list[DiscoveryResult]  = []
        self._start:     float                  = 0.0

    async def run(self) -> list[DiscoveryResult]:
        """Send multicast discovery request and collect responses."""
        context: aiocoap.Context = await aiocoap.Context.create_client_context()

        # Build multicast request — NON (non-confirmable) as required by RFC 7252 sec 8.1
        uri: str = f'coap://{COAP_MULTICAST_ADDR}:{COAP_PORT}/.well-known/core'
        request: aiocoap.Message = aiocoap.Message(
            code=aiocoap.GET,
            uri=uri,
            transport_tuning=aiocoap.Unreliable,   # multicast MUST use NON
        )

        print(f'  Sending multicast GET to {COAP_MULTICAST_ADDR}:{COAP_PORT}/.well-known/core')
        print(f'  Collecting responses for {DISCOVERY_TIMEOUT}s...')
        print()

        self._start = time.perf_counter()

        # aiocoap multicast: observe the request for multiple responses
        requester = context.request(request)

        try:
            # Collect all responses within the timeout window
            async def collect() -> None:
                async for response in requester.responses_and_notifications:
                    rtt_ms: float = round((time.perf_counter() - self._start) * 1000, 2)
                    remote: tuple[str, int] = response.remote.hostinfo_local  # type: ignore[attr-defined]

                    # Extract the remote IP from the response
                    remote_ip:   str = str(response.remote.hostinfo).split(':')[0]
                    remote_port: int = COAP_PORT

                    payload: str = response.payload.decode('utf-8')
                    resources: list[ParsedResource] = parse_link_format(payload)

                    self._results.append({
                        'remote_ip':   remote_ip,
                        'remote_port': remote_port,
                        'rtt_ms':      rtt_ms,
                        'resources':   resources,
                        'raw':         payload,
                    })
                    print(f'  → Response from {remote_ip} in {rtt_ms}ms')

            await asyncio.wait_for(collect(), timeout=DISCOVERY_TIMEOUT)

        except asyncio.TimeoutError:
            pass  # expected — timeout means we've collected all responses
        except Exception as exc:
            print(f'  [ERROR] {exc}')

        await context.shutdown()
        return self._results


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(local_ip: str) -> None:
    """Run multicast CoAP discovery and print results."""
    print()
    print('CoAP Multicast Discovery Client')
    print(f'Local interface: {local_ip}')
    print()

    discovery: MulticastDiscovery = MulticastDiscovery(local_ip)
    results: list[DiscoveryResult] = await discovery.run()

    if not results:
        print('  No devices responded to multicast discovery.')
        print('  Make sure servers are running and have joined the multicast group.')
        return

    format_table(results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CoAP Multicast Discovery Client')
    parser.add_argument('--interface', type=str, default='192.168.100.1',
                        help='Local IP to send multicast from (default: 192.168.100.1)')
    args = parser.parse_args()

    asyncio.run(main(args.interface))