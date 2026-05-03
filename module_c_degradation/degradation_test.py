# coap-demo/module_c_degradation/degradation_test.py

"""
Module C — CoAP Network Degradation Test (WSL / Linux)
Uses 'tc netem' to apply real UDP packet loss at the kernel level on the
loopback interface, then measures CON vs NON message resilience.

CON (Confirmable / Reliable): aiocoap retransmits automatically until ACK.
  - Up to 4 retransmissions with exponential backoff (RFC 7252 sec 4.2)
  - Should stay near 100% success even under moderate loss
NON (Non-confirmable / Unreliable): fire-and-forget, no retransmission.
  - Success rate degrades linearly with packet loss

Must be run inside WSL or Linux with sudo privileges for tc netem.

Usage:
    python3 degradation_test.py --requests 20 --port 5690
"""

import asyncio
import argparse
import csv
import os
import subprocess
import sys
import time

import aiocoap


# ── Types ─────────────────────────────────────────────────────────────────────

DegradationRecord = dict[str, str | float | int]

# ── Config ────────────────────────────────────────────────────────────────────

LOSS_LEVELS:     list[float] = [0.0, 0.05, 0.10, 0.20, 0.30]
COAP_HOST:       str         = '127.0.0.1'
COAP_PORT:       int         = 5690
STARTUP_WAIT:    float       = 5.0

# CON retransmission timeout: RFC 7252 default ACK_TIMEOUT=2s, up to 4 retries
# Max theoretical wait = 2 + 4 + 8 + 16 = 30s. We use 35s to be safe.
CON_TIMEOUT: float = 35.0
NON_TIMEOUT: float = 3.0    # NON never retransmits — short timeout is fine

TC_INTERFACE: str = 'lo'    # loopback — where localhost traffic flows

RESULTS_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results')
RESULTS_CSV: str = os.path.join(RESULTS_DIR, 'degradation_results.csv')


# ── tc netem helpers ──────────────────────────────────────────────────────────

def tc_apply_loss(loss_rate: float) -> None:
    """Apply packet loss to the loopback interface using tc netem.
    At 0% loss, does nothing — avoids disrupting the loopback interface."""
    if loss_rate <= 0.0:
        return  # never touch the interface at 0% — del/add breaks WSL loopback

    # Remove any existing qdisc before adding a new one
    subprocess.run(
        ['sudo', 'tc', 'qdisc', 'del', 'dev', TC_INTERFACE, 'root'],
        capture_output=True,
    )

    loss_pct: str = f'{loss_rate * 100:.0f}%'
    result = subprocess.run(
        ['sudo', 'tc', 'qdisc', 'add', 'dev', TC_INTERFACE, 'root',
         'netem', 'loss', loss_pct],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f'  [tc ERROR] {result.stderr.strip()}')
        sys.exit(1)


def tc_clear_loss() -> None:
    """Remove all tc netem rules from the loopback interface."""
    subprocess.run(
        ['sudo', 'tc', 'qdisc', 'del', 'dev', TC_INTERFACE, 'root'],
        capture_output=True,
    )


# ── Single request ────────────────────────────────────────────────────────────

async def send_con(context: aiocoap.Context, uri: str, loss_pct: int) -> DegradationRecord:
    """
    Send one CON (Reliable / Confirmable) request.
    aiocoap will retransmit automatically if no ACK is received.
    Uses transport_tuning=aiocoap.Reliable (new API, replaces mtype=CON).
    """
    request: aiocoap.Message = aiocoap.Message(
        code=aiocoap.GET,
        uri=uri,
        transport_tuning=aiocoap.Reliable,
    )
    start: float = time.perf_counter()
    try:
        response: aiocoap.Message = await asyncio.wait_for(
            context.request(request).response,
            timeout=CON_TIMEOUT,
        )
        rtt_ms: float = round((time.perf_counter() - start) * 1000, 3)
        return {'msg_type': 'CON', 'loss_pct': loss_pct, 'success': 1, 'rtt_ms': rtt_ms, 'note': 'ok'}
    except asyncio.TimeoutError:
        return {'msg_type': 'CON', 'loss_pct': loss_pct, 'success': 0, 'rtt_ms': -1, 'note': 'timeout'}
    except Exception as exc:
        return {'msg_type': 'CON', 'loss_pct': loss_pct, 'success': 0, 'rtt_ms': -1, 'note': f'error:{exc}'}


async def send_non(context: aiocoap.Context, uri: str, loss_pct: int) -> DegradationRecord:
    """
    Send one NON (Unreliable / Non-confirmable) request.
    No retransmission — if the packet is dropped by tc netem, the request fails.
    Uses transport_tuning=aiocoap.Unreliable (new API, replaces mtype=NON).
    """
    request: aiocoap.Message = aiocoap.Message(
        code=aiocoap.GET,
        uri=uri,
        transport_tuning=aiocoap.Unreliable,
    )
    start: float = time.perf_counter()
    try:
        response: aiocoap.Message = await asyncio.wait_for(
            context.request(request).response,
            timeout=NON_TIMEOUT,
        )
        rtt_ms: float = round((time.perf_counter() - start) * 1000, 3)
        return {'msg_type': 'NON', 'loss_pct': loss_pct, 'success': 1, 'rtt_ms': rtt_ms, 'note': 'ok'}
    except asyncio.TimeoutError:
        return {'msg_type': 'NON', 'loss_pct': loss_pct, 'success': 0, 'rtt_ms': -1, 'note': 'timeout'}
    except Exception as exc:
        return {'msg_type': 'NON', 'loss_pct': loss_pct, 'success': 0, 'rtt_ms': -1, 'note': f'error:{exc}'}


# ── Loss level runner ─────────────────────────────────────────────────────────

async def run_loss_level(n: int, loss_rate: float) -> list[DegradationRecord]:
    """Apply tc netem loss, run n CON + n NON requests, then clear the rule."""
    loss_pct: int = int(loss_rate * 100)
    coap_uri: str = f'coap://{COAP_HOST}:{COAP_PORT}/sensor'

    print(f'  [{loss_pct:>3}% loss] Applying tc netem...', end=' ', flush=True)
    tc_apply_loss(loss_rate)

    context: aiocoap.Context = await aiocoap.Context.create_client_context()
    records: list[DegradationRecord] = []

    print(f'Sending {n} CON + {n} NON...', end=' ', flush=True)

    for _ in range(n):
        records.append(await send_con(context, coap_uri, loss_pct))
        records.append(await send_non(context, coap_uri, loss_pct))

    await context.shutdown()
    tc_clear_loss()

    con_ok: int = sum(1 for r in records if r['msg_type'] == 'CON' and r['success'] == 1)
    non_ok: int = sum(1 for r in records if r['msg_type'] == 'NON' and r['success'] == 1)
    print(f'CON {con_ok}/{n}  NON {non_ok}/{n}')

    return records


# ── CSV + summary ─────────────────────────────────────────────────────────────

def save_csv(records: list[DegradationRecord]) -> None:
    """Write all degradation records to CSV."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    fields: list[str] = ['msg_type', 'loss_pct', 'success', 'rtt_ms', 'note']
    with open(RESULTS_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    print(f'\n[CSV] Results saved to {RESULTS_CSV}')


def print_summary(records: list[DegradationRecord], n: int) -> None:
    """Print success rate + avg RTT + std dev per loss level and message type."""
    print()
    print('=' * 78)
    print('  DEGRADATION SUMMARY (real tc netem packet loss)')
    print('=' * 78)
    print(f'  {"Loss %":<8} {"CON ok":<10} {"CON RTT avg":<15} {"CON RTT std":<15} {"NON ok":<10} {"NON RTT avg":<15} {"NON RTT std"}')
    print('-' * 78)

    for loss_pct in [int(l * 100) for l in LOSS_LEVELS]:
        for msg_type in ['CON', 'NON']:
            subset = [
                r for r in records
                if r['msg_type'] == msg_type and r['loss_pct'] == loss_pct
            ]
            ok_rtts = [float(r['rtt_ms']) for r in subset if r['success'] == 1]
            ok_count = len(ok_rtts)
            avg_rtt = round(sum(ok_rtts) / ok_count, 1) if ok_rtts else -1
            std_rtt = round((sum((x - avg_rtt) ** 2 for x in ok_rtts) / ok_count) ** 0.5, 1) if len(ok_rtts) > 1 else 0.0

            if msg_type == 'CON':
                con_ok, con_avg, con_std = ok_count, avg_rtt, std_rtt
            else:
                print(f'  {loss_pct:<8} {con_ok}/{n:<8} {con_avg:<15} {con_std:<15} {ok_count}/{n:<8} {avg_rtt:<15} {std_rtt}')

    print('=' * 78)
    print()


# ── Server launcher ───────────────────────────────────────────────────────────

def start_server(port: int) -> subprocess.Popen[str]:
    """Start the degradation server as a background process."""
    script: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.py')
    return subprocess.Popen(
        [sys.executable, script, '--port', str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(n_requests: int, port: int) -> None:
    """Run real degradation tests across all loss levels using tc netem."""
    global COAP_PORT
    COAP_PORT = port

    print()
    print('=' * 58)
    print('  MODULE C — CoAP Degradation Test (tc netem / WSL)')
    print('=' * 58)
    print(f'  Requests per level : {n_requests} CON + {n_requests} NON')
    print(f'  Loss levels        : {[int(l * 100) for l in LOSS_LEVELS]}%')
    print(f'  Interface          : {TC_INTERFACE} (loopback)')
    print(f'  CON timeout        : {CON_TIMEOUT}s (covers 4 retransmissions)')
    print(f'  NON timeout        : {NON_TIMEOUT}s (no retransmit)')
    print()

    proc: subprocess.Popen[str] = start_server(port)
    print(f'  Server started (pid {proc.pid})')
    print('  Probing server until ready...', end=' ', flush=True)

    coap_uri_probe: str = f'coap://{COAP_HOST}:{port}/sensor'
    probe_ctx: aiocoap.Context = await aiocoap.Context.create_client_context()
    for _attempt in range(20):
        try:
            probe_req: aiocoap.Message = aiocoap.Message(code=aiocoap.GET, uri=coap_uri_probe)
            await asyncio.wait_for(probe_ctx.request(probe_req).response, timeout=2.0)
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        print('FAILED — server did not respond.')
        proc.terminate()
        return
    await probe_ctx.shutdown()
    print('ready.\n')

    all_records: list[DegradationRecord] = []
    try:
        for loss_rate in LOSS_LEVELS:
            records = await run_loss_level(n_requests, loss_rate)
            all_records.extend(records)
    finally:
        tc_clear_loss()
        proc.terminate()

    print_summary(all_records, n_requests)
    save_csv(all_records)
    print('  Done. Run plot_degradation.py to generate charts.\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CoAP Degradation Test (tc netem)')
    parser.add_argument('--requests', type=int, default=20,   help='Requests per loss level per message type (default 20)')
    parser.add_argument('--port',     type=int, default=5690, help='CoAP server port')
    args = parser.parse_args()

    asyncio.run(main(args.requests, args.port))