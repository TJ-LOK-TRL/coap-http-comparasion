# coap-demo/module_b_discovery/run_demo.py

"""
Module B — Run Demo (Realistic / WSL)
Orchestrates the full realistic CoAP service discovery demo:

  1. Creates 3 dummy network interfaces with unique IPs (simulating 3 IoT devices)
  2. Adds multicast routing so multicast traffic flows through dummy0
  3. Starts 3 CoAP servers, each on a unique IP and standard port 5683
  4. Runs the multicast discovery client (sends to 224.0.1.187:5683)
  5. All 3 servers respond — client prints the discovery table
  6. Cleans up: terminates servers, removes interfaces and routes

This setup is functionally identical to a real Wi-Fi IoT deployment where
each device (ESP32, Raspberry Pi, etc.) has its own IP on the network.

Must be run inside WSL or Linux with sudo privileges.

Usage:
    python3 run_demo.py
"""

import asyncio
import os
import subprocess
import sys
import time


# ── Types ─────────────────────────────────────────────────────────────────────

DeviceConfig = dict[str, str]

# ── Network config ────────────────────────────────────────────────────────────

# Each device gets a unique IP on a /24 subnet — exactly like a real Wi-Fi network
DEVICES: list[DeviceConfig] = [
    {'ip': '192.168.100.1', 'device': 'temperature', 'iface': 'dummy0'},
    {'ip': '192.168.100.2', 'device': 'humidity',    'iface': 'dummy1'},
    {'ip': '192.168.100.3', 'device': 'led',         'iface': 'dummy2'},
]

MULTICAST_ROUTE:  str   = '224.0.0.0/4'
MULTICAST_VIA:    str   = 'dummy0'          # multicast traffic goes through first interface
STARTUP_WAIT:     float = 3.0
COAP_PORT:        int   = 5683


# ── Network setup / teardown ──────────────────────────────────────────────────

def run_sudo(*args: str) -> bool:
    """Run a sudo command. Returns True on success."""
    result = subprocess.run(
        ['sudo'] + list(args),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def setup_network() -> None:
    """Create dummy interfaces with unique IPs and multicast route."""
    print('  Setting up virtual network interfaces...')

    for dev in DEVICES:
        iface: str = dev['iface']
        ip:    str = dev['ip']

        # Remove if already exists (clean state)
        run_sudo('ip', 'link', 'del', iface)

        run_sudo('ip', 'link', 'add', iface, 'type', 'dummy')
        run_sudo('ip', 'addr', 'add', f'{ip}/24', 'dev', iface)
        run_sudo('ip', 'link', 'set', iface, 'up')
        print(f'    [NET] {iface} → {ip}/24  (simulates IoT device)')

    # Add multicast route through dummy0
    run_sudo('ip', 'route', 'del', MULTICAST_ROUTE)   # remove if exists
    run_sudo('ip', 'route', 'add', MULTICAST_ROUTE, 'dev', MULTICAST_VIA)
    print(f'    [NET] Multicast route {MULTICAST_ROUTE} → {MULTICAST_VIA}')
    print()


def teardown_network() -> None:
    """Remove dummy interfaces and multicast route."""
    print('  Tearing down virtual network interfaces...')
    run_sudo('ip', 'route', 'del', MULTICAST_ROUTE)
    for dev in DEVICES:
        run_sudo('ip', 'link', 'del', dev['iface'])
    print('  Network cleaned up.')


# ── Server management ─────────────────────────────────────────────────────────

def server_script() -> str:
    """Absolute path to server.py."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.py')


def discovery_script() -> str:
    """Absolute path to client_discovery.py."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'client_discovery.py')


def start_servers() -> list[subprocess.Popen[str]]:
    """Start one CoAP server per device on its unique IP."""
    processes: list[subprocess.Popen[str]] = []

    print('  Starting CoAP servers...')
    for dev in DEVICES:
        proc: subprocess.Popen[str] = subprocess.Popen(
            [sys.executable, server_script(),
             '--ip',     dev['ip'],
             '--device', dev['device']],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        print(f'    [SERVER] {dev["device"]:<15} coap://{dev["ip"]}:{COAP_PORT}  (pid {proc.pid})')
        processes.append(proc)

    return processes


async def wait_for_servers() -> None:
    """Probe each server until it responds or timeout."""
    import aiocoap

    print(f'\n  Waiting for servers to be ready...', end=' ', flush=True)
    context: aiocoap.Context = await aiocoap.Context.create_client_context()

    for dev in DEVICES:
        uri: str = f'coap://{dev["ip"]}:{COAP_PORT}/.well-known/core'
        for _ in range(20):
            try:
                req: aiocoap.Message = aiocoap.Message(code=aiocoap.GET, uri=uri)
                await asyncio.wait_for(context.request(req).response, timeout=2.0)
                break
            except Exception:
                await asyncio.sleep(0.3)

    await context.shutdown()
    print('ready.')


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    """Full demo: setup network → start servers → discover → teardown."""
    print()
    print('=' * 60)
    print('  MODULE B — CoAP Multicast Service Discovery Demo')
    print('  Realistic simulation with unique IPs + RFC 7252 multicast')
    print('=' * 60)
    print()

    setup_network()

    processes: list[subprocess.Popen[str]] = start_servers()

    await wait_for_servers()

    print()
    print('  Running multicast discovery client...')
    print()

    try:
        subprocess.run(
            [sys.executable, discovery_script(),
             '--interface', DEVICES[0]['ip']],
            text=True,
            check=False,
        )
    finally:
        print()
        print('  Shutting down servers...')
        for proc in processes:
            proc.terminate()

        teardown_network()
        print()
        print('  Demo complete.')
        print()


if __name__ == '__main__':
    asyncio.run(main())