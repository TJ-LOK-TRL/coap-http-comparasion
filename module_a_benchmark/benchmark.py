# coap-demo/module_a_benchmark/benchmark.py

"""
Module A — CoAP vs HTTP Benchmark
Measures latency (RTT) and response payload size for both protocols.
Saves results to results/benchmark_results.csv.

Usage:
    Local:
        python benchmark.py --requests 100
    Two PCs:
        python benchmark.py --coap-uri coap://192.168.1.10:5683/sensor \
                            --http-uri http://192.168.1.10:8080/sensor \
                            --no-start-local-servers
    With payload sweep:
        python benchmark.py --payload-sweep
"""

import asyncio
import argparse
import csv
import os
import subprocess
import sys
import time

import aiocoap
import aiohttp


# ── Types ─────────────────────────────────────────────────────────────────────

BenchmarkRecord = dict[str, str | float | int]

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_COAP_URI: str = 'coap://127.0.0.1:5683/sensor'
DEFAULT_HTTP_URI: str = 'http://127.0.0.1:8080/sensor'
RESULTS_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results')
RESULTS_CSV: str = os.path.join(RESULTS_DIR, 'benchmark_results.csv')
SWEEP_DIR:   str = os.path.join(RESULTS_DIR, 'payload_sweep')

STARTUP_WAIT: float = 2.0

# Payload sizes for the sweep (bytes). Split into two scenarios:
#   - Below UDP MTU (~1500 B): no fragmentation, direct comparison.
#   - Above UDP MTU: CoAP requires block-wise transfer (RFC 7959); results
#     are intentionally kept separate so the report can discuss the boundary.
SWEEP_SIZES_NO_FRAG:   list[int] = [64, 256, 512, 1024]
SWEEP_SIZES_WITH_FRAG: list[int] = [2048, 4096, 8192]
SWEEP_SIZES: list[int] = SWEEP_SIZES_NO_FRAG + SWEEP_SIZES_WITH_FRAG


# ── CoAP benchmark ────────────────────────────────────────────────────────────

async def run_coap_benchmark(
    n: int,
    coap_uri: str,
    payload_size: int | None = None,
) -> list[BenchmarkRecord]:
    """Send n GET requests to the CoAP server and record RTT + payload size."""
    uri = _coap_sweep_uri(coap_uri, payload_size) if payload_size is not None else coap_uri
    context: aiocoap.Context = await aiocoap.Context.create_client_context()
    records: list[BenchmarkRecord] = []

    label = f'{payload_size}B' if payload_size is not None else 'sensor'
    print(f'[CoAP] Sending {n} requests ({label}) to {uri}...')

    for i in range(n):
        request: aiocoap.Message = aiocoap.Message(code=aiocoap.GET, uri=uri)
        start: float = time.perf_counter()
        try:
            response: aiocoap.Message = await asyncio.wait_for(
                context.request(request).response,
                timeout=10.0,
            )
            rtt_ms: float = round((time.perf_counter() - start) * 1000, 3)
            payload_bytes: int = len(response.payload)

            # Approximate on-wire CoAP size:
            #   4 bytes fixed header + token + option TLVs + payload marker
            options_size: int = sum(
                1 + len(opt.encode())
                for opt in response.opt.option_list()
            )
            payload_marker: int = 1 if payload_bytes > 0 else 0
            header_bytes: int = 4 + len(response.token) + options_size + payload_marker
            total_bytes: int = header_bytes + payload_bytes

            records.append({
                'protocol':      'CoAP',
                'request_num':   i + 1,
                'rtt_ms':        rtt_ms,
                'payload_bytes': payload_bytes,
                'header_bytes':  header_bytes,
                'total_bytes':   total_bytes,
                'status':        'ok',
            })
        except Exception as exc:
            records.append({
                'protocol':      'CoAP',
                'request_num':   i + 1,
                'rtt_ms':        -1,
                'payload_bytes': 0,
                'header_bytes':  0,
                'total_bytes':   0,
                'status':        f'error: {exc}',
            })

    await context.shutdown()
    ok: int = sum(1 for r in records if r['status'] == 'ok')
    print(f'[CoAP] Done. {ok}/{n} successful.')
    return records


# ── HTTP benchmark ────────────────────────────────────────────────────────────

async def run_http_benchmark(
    n: int,
    http_uri: str,
    payload_size: int | None = None,
) -> list[BenchmarkRecord]:
    """Send n GET requests to the HTTP server and record RTT + payload size."""
    uri = _http_sweep_uri(http_uri, payload_size) if payload_size is not None else http_uri
    records: list[BenchmarkRecord] = []

    label = f'{payload_size}B' if payload_size is not None else 'sensor'
    print(f'[HTTP] Sending {n} requests ({label}) to {uri}...')

    async with aiohttp.ClientSession() as session:
        for i in range(n):
            start: float = time.perf_counter()
            try:
                async with session.get(uri) as response:
                    body: bytes = await response.read()
                    rtt_ms: float = round((time.perf_counter() - start) * 1000, 3)

                    payload_bytes: int = len(body)

                    # Approximate HTTP header size from parsed headers.
                    # Accounts for "Key: Value\r\n" per field plus the
                    # status line ("HTTP/1.1 200 OK\r\n") and final CRLF.
                    status_line = f'HTTP/1.1 {response.status} {response.reason}\r\n'
                    header_bytes: int = len(status_line.encode('utf-8'))
                    header_bytes += sum(
                        len(k.encode('utf-8')) + 2 + len(v.encode('utf-8')) + 2  # "K: V\r\n"
                        for k, v in response.headers.items()
                    )
                    header_bytes += 2  # final blank line CRLF
                    total_bytes: int = header_bytes + payload_bytes

                    records.append({
                        'protocol':      'HTTP',
                        'request_num':   i + 1,
                        'rtt_ms':        rtt_ms,
                        'payload_bytes': payload_bytes,
                        'header_bytes':  header_bytes,
                        'total_bytes':   total_bytes,
                        'status':        'ok',
                    })
            except Exception as exc:
                records.append({
                    'protocol':      'HTTP',
                    'request_num':   i + 1,
                    'rtt_ms':        -1,
                    'payload_bytes': 0,
                    'header_bytes':  0,
                    'total_bytes':   0,
                    'status':        f'error: {exc}',
                })

    ok: int = sum(1 for r in records if r['status'] == 'ok')
    print(f'[HTTP] Done. {ok}/{n} successful.')
    return records


# ── URI helpers ───────────────────────────────────────────────────────────────

def _coap_sweep_uri(base_uri: str, size: int) -> str:
    """Build CoAP URI for the /data endpoint with a given payload size."""
    host = base_uri.split('coap://')[1].rsplit('/', 1)[0]
    return f'coap://{host}/data?size={size}'


def _http_sweep_uri(base_uri: str, size: int) -> str:
    """Build HTTP URI for the /data endpoint with a given payload size."""
    host = base_uri.split('/sensor')[0]
    return f'{host}/data?size={size}'


# ── CSV export ────────────────────────────────────────────────────────────────

def save_csv(records: list[BenchmarkRecord], path: str) -> None:
    """Write benchmark records to a CSV file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fields: list[str] = [
        'protocol', 'request_num', 'rtt_ms',
        'payload_bytes', 'header_bytes', 'total_bytes', 'status',
    ]

    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    print(f'[CSV] Saved: {path}')


# ── Statistics ────────────────────────────────────────────────────────────────

def calc_std(rtts: list[float]) -> float:
    """Population standard deviation of RTT values."""
    if len(rtts) < 2:
        return 0.0
    mean = sum(rtts) / len(rtts)
    return round((sum((x - mean) ** 2 for x in rtts) / len(rtts)) ** 0.5, 3)


def calc_jitter(rtts: list[float]) -> float:
    """Mean absolute difference between consecutive RTTs (RFC 3550 definition)."""
    if len(rtts) < 2:
        return 0.0
    return round(sum(abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))) / (len(rtts) - 1), 3)


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(records: list[BenchmarkRecord], label: str = '') -> None:
    """Print a human-readable summary table of average metrics per protocol."""
    protocols: list[str] = ['CoAP', 'HTTP']
    title = f'BENCHMARK SUMMARY{" — " + label if label else ""}'

    print()
    print('=' * 80)
    print(f'  {title}')
    print('=' * 80)
    print(f'  {"Protocol":<10} {"Avg RTT (ms)":<16} {"Std Dev (ms)":<16} {"Jitter (ms)":<14} {"Avg Total (B)"}')
    print('-' * 80)

    for proto in protocols:
        ok_records = [r for r in records if r['protocol'] == proto and r['status'] == 'ok']
        if not ok_records:
            print(f'  {proto:<10} {"N/A":<16} {"N/A":<16} {"N/A":<14} {"N/A"}')
            continue

        rtts: list[float] = [float(r['rtt_ms']) for r in ok_records]
        avg_rtt:   float = round(sum(rtts) / len(rtts), 3)
        std_dev:   float = calc_std(rtts)
        jitter:    float = calc_jitter(rtts)
        avg_total: float = round(sum(float(r['total_bytes']) for r in ok_records) / len(ok_records), 1)

        print(f'  {proto:<10} {avg_rtt:<16} {std_dev:<16} {jitter:<14} {avg_total}')

    print('=' * 80)
    print()


# ── Sweep summary CSV ─────────────────────────────────────────────────────────

SweepRow = dict[str, str | float | int]


def build_sweep_summary(sweep_results: dict[int, list[BenchmarkRecord]]) -> list[SweepRow]:
    """Build a flat summary table from sweep results for plotting."""
    rows: list[SweepRow] = []
    for size, records in sweep_results.items():
        for proto in ['CoAP', 'HTTP']:
            ok = [r for r in records if r['protocol'] == proto and r['status'] == 'ok']
            if not ok:
                continue
            rtts = [float(r['rtt_ms']) for r in ok]
            rows.append({
                'payload_size':    size,
                'protocol':        proto,
                'fragmented':      'yes' if size in SWEEP_SIZES_WITH_FRAG else 'no',
                'avg_rtt_ms':      round(sum(rtts) / len(rtts), 3),
                'std_dev_ms':      calc_std(rtts),
                'jitter_ms':       calc_jitter(rtts),
                'avg_total_bytes': round(
                    sum(float(r['total_bytes']) for r in ok) / len(ok), 1
                ),
                'n_ok': len(ok),
            })
    return rows


def save_sweep_summary(rows: list[SweepRow]) -> None:
    """Write sweep summary to results/payload_sweep/summary.csv."""
    os.makedirs(SWEEP_DIR, exist_ok=True)
    path = os.path.join(SWEEP_DIR, 'summary.csv')
    fields = [
        'payload_size', 'protocol', 'fragmented',
        'avg_rtt_ms', 'std_dev_ms', 'jitter_ms', 'avg_total_bytes', 'n_ok',
    ]
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f'[CSV] Sweep summary saved: {path}')


# ── Server launchers ──────────────────────────────────────────────────────────

def script_path(filename: str) -> str:
    """Return absolute path to a script in the same directory."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def start_servers() -> list[subprocess.Popen[str]]:
    """Start CoAP and HTTP servers as background processes."""
    processes: list[subprocess.Popen[str]] = []

    for name, script, extra_args in [
        ('CoAP', 'coap_server.py', ['--port', '5683']),
        ('HTTP', 'http_server.py', ['--port', '8080']),
    ]:
        proc: subprocess.Popen[str] = subprocess.Popen(
            [sys.executable, script_path(script)] + extra_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        print(f'  [{name}] Server started (pid {proc.pid})')
        processes.append(proc)

    return processes


# ── Warmup / ping ─────────────────────────────────────────────────────────────

async def _coap_ping(coap_uri: str) -> bool:
    context: aiocoap.Context = await aiocoap.Context.create_client_context()
    try:
        request = aiocoap.Message(code=aiocoap.GET, uri=coap_uri)
        await asyncio.wait_for(context.request(request).response, timeout=3.0)
        return True
    except Exception as exc:
        print(f'[CoAP] ✗ Server unreachable: {exc}')
        return False
    finally:
        await context.shutdown()


async def _http_ping(http_uri: str) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                http_uri,
                timeout=aiohttp.ClientTimeout(total=3.0),
            ) as response:
                await response.read()
        return True
    except Exception as exc:
        print(f'[HTTP] ✗ Server unreachable: {exc}')
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(
    n_requests: int,
    coap_uri: str,
    http_uri: str,
    start_local: bool,
    payload_sweep: bool,
) -> None:
    """Run the full CoAP vs HTTP benchmark."""
    print()
    print('=' * 55)
    print('  MODULE A — CoAP vs HTTP Benchmark')
    print('=' * 55)
    print()

    processes: list[subprocess.Popen[str]] = []

    if start_local:
        processes = start_servers()
        print(f'\n  Waiting {STARTUP_WAIT}s for servers to initialise...\n')
        await asyncio.sleep(STARTUP_WAIT)
    else:
        print(f'  [INFO] Skipping local server startup.')
        print(f'  [INFO] CoAP target: {coap_uri}')
        print(f'  [INFO] HTTP target: {http_uri}\n')

    print('  Checking server connectivity...')
    coap_ok = await _coap_ping(coap_uri)
    http_ok  = await _http_ping(http_uri)
    if not coap_ok or not http_ok:
        print('\n  ✗ Aborting — one or more servers are unreachable.')
        if processes:
            for proc in processes:
                proc.terminate()
        return
    print('  ✓ Both servers reachable. Starting benchmark...\n')

    # ── Sensor benchmark ──────────────────────────────────────────────────────
    coap_records = await run_coap_benchmark(n_requests, coap_uri)
    http_records = await run_http_benchmark(n_requests, http_uri)
    all_records  = coap_records + http_records

    print_summary(all_records, label='Sensor payload')
    os.makedirs(RESULTS_DIR, exist_ok=True)
    save_csv(all_records, RESULTS_CSV)

    # ── Payload sweep (optional) ──────────────────────────────────────────────
    if payload_sweep:
        print()
        print('=' * 55)
        print('  PAYLOAD SWEEP')
        print(f'  No-frag sizes : {SWEEP_SIZES_NO_FRAG}')
        print(f'  Frag sizes    : {SWEEP_SIZES_WITH_FRAG} (CoAP block-wise)')
        print('=' * 55)
        print()

        os.makedirs(SWEEP_DIR, exist_ok=True)
        sweep_results: dict[int, list[BenchmarkRecord]] = {}

        for size in SWEEP_SIZES:
            label = f'{size}B'
            coap_sw = await run_coap_benchmark(n_requests, coap_uri, payload_size=size)
            http_sw = await run_http_benchmark(n_requests, http_uri, payload_size=size)
            combined = coap_sw + http_sw
            sweep_results[size] = combined
            print_summary(combined, label=label)

            # per-size CSVs
            save_csv(coap_sw, os.path.join(SWEEP_DIR, f'coap_{label}.csv'))
            save_csv(http_sw, os.path.join(SWEEP_DIR, f'http_{label}.csv'))

        summary_rows = build_sweep_summary(sweep_results)
        save_sweep_summary(summary_rows)

    if processes:
        print('\n  Shutting down servers...')
        for proc in processes:
            proc.terminate()

    print('  Done. Run plot_results.py to generate charts.\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CoAP vs HTTP Benchmark')
    parser.add_argument('--requests', type=int, default=100,
                        help='Number of requests per protocol (default: 100)')
    parser.add_argument('--coap-uri', type=str, default=DEFAULT_COAP_URI,
                        help=f'CoAP server URI (default: {DEFAULT_COAP_URI})')
    parser.add_argument('--http-uri', type=str, default=DEFAULT_HTTP_URI,
                        help=f'HTTP server URI (default: {DEFAULT_HTTP_URI})')
    parser.add_argument('--start-local-servers', dest='start_local',
                        action=argparse.BooleanOptionalAction, default=True,
                        help='Start local servers before benchmarking. '
                             'Use --no-start-local-servers for two-PC mode.')
    parser.add_argument('--payload-sweep', action='store_true', default=False,
                        help='Also benchmark synthetic payloads of varying sizes.')

    args = parser.parse_args()

    asyncio.run(main(
        n_requests=args.requests,
        coap_uri=args.coap_uri,
        http_uri=args.http_uri,
        start_local=args.start_local,
        payload_sweep=args.payload_sweep,
    ))