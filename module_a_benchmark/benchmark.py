# coap-demo/module_a_benchmark/benchmark.py

"""
Module A — CoAP vs HTTP Benchmark
Measures latency (RTT) and response payload size for both protocols.
Saves results to results/benchmark_results.csv.

Usage:
    python benchmark.py --requests 100
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

COAP_URI: str = 'coap://127.0.0.1:5683/sensor'
HTTP_URI: str = 'http://127.0.0.1:8080/sensor'
RESULTS_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results')
RESULTS_CSV: str = os.path.join(RESULTS_DIR, 'benchmark_results.csv')

STARTUP_WAIT: float = 2.0


# ── CoAP benchmark ────────────────────────────────────────────────────────────

async def run_coap_benchmark(n: int) -> list[BenchmarkRecord]:
    """Send n GET requests to the CoAP server and record RTT + payload size."""
    context: aiocoap.Context = await aiocoap.Context.create_client_context()
    records: list[BenchmarkRecord] = []

    print(f'[CoAP] Sending {n} requests to {COAP_URI}...')

    for i in range(n):
        request: aiocoap.Message = aiocoap.Message(code=aiocoap.GET, uri=COAP_URI)
        start: float = time.perf_counter()
        try:
            response: aiocoap.Message = await asyncio.wait_for(
                context.request(request).response,
                timeout=5.0,
            )
            rtt_ms: float = round((time.perf_counter() - start) * 1000, 3)
            payload_bytes: int = len(response.payload)
            # CoAP header is fixed 4 bytes + token; typical overhead ~8-12 bytes
            header_bytes: int = 4 + len(response.token)
            total_bytes: int = header_bytes + payload_bytes

            records.append({
                'protocol':      'CoAP',
                'request_num':   i + 1,
                'rtt_ms':        rtt_ms,
                'payload_bytes': payload_bytes,
                'total_bytes':   total_bytes,
                'status':        'ok',
            })
        except Exception as exc:
            records.append({
                'protocol':      'CoAP',
                'request_num':   i + 1,
                'rtt_ms':        -1,
                'payload_bytes': 0,
                'total_bytes':   0,
                'status':        f'error: {exc}',
            })

    await context.shutdown()
    ok: int = sum(1 for r in records if r['status'] == 'ok')
    print(f'[CoAP] Done. {ok}/{n} successful.')
    return records


# ── HTTP benchmark ────────────────────────────────────────────────────────────

async def run_http_benchmark(n: int) -> list[BenchmarkRecord]:
    """Send n GET requests to the HTTP server and record RTT + payload size."""
    records: list[BenchmarkRecord] = []

    print(f'[HTTP] Sending {n} requests to {HTTP_URI}...')

    async with aiohttp.ClientSession() as session:
        for i in range(n):
            start: float = time.perf_counter()
            try:
                async with session.get(HTTP_URI) as response:
                    body: bytes = await response.read()
                    rtt_ms: float = round((time.perf_counter() - start) * 1000, 3)

                    payload_bytes: int = len(body)
                    # Estimate HTTP header overhead (typical GET response headers ~200-400 bytes)
                    raw_headers: str = str(response.headers)
                    header_bytes: int = len(raw_headers.encode('utf-8'))
                    total_bytes: int = header_bytes + payload_bytes

                    records.append({
                        'protocol':      'HTTP',
                        'request_num':   i + 1,
                        'rtt_ms':        rtt_ms,
                        'payload_bytes': payload_bytes,
                        'total_bytes':   total_bytes,
                        'status':        'ok',
                    })
            except Exception as exc:
                records.append({
                    'protocol':      'HTTP',
                    'request_num':   i + 1,
                    'rtt_ms':        -1,
                    'payload_bytes': 0,
                    'total_bytes':   0,
                    'status':        f'error: {exc}',
                })

    ok: int = sum(1 for r in records if r['status'] == 'ok')
    print(f'[HTTP] Done. {ok}/{n} successful.')
    return records


# ── CSV export ────────────────────────────────────────────────────────────────

def save_csv(records: list[BenchmarkRecord]) -> None:
    """Write all benchmark records to a CSV file."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    fields: list[str] = ['protocol', 'request_num', 'rtt_ms', 'payload_bytes', 'total_bytes', 'status']

    with open(RESULTS_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    print(f'\n[CSV] Results saved to {RESULTS_CSV}')


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(records: list[BenchmarkRecord]) -> None:
    """Print a human-readable summary table of average metrics per protocol."""
    protocols: list[str] = ['CoAP', 'HTTP']

    print()
    print('=' * 62)
    print('  BENCHMARK SUMMARY')
    print('=' * 62)
    print(f'  {"Protocol":<10} {"Avg RTT (ms)":<16} {"Avg Payload (B)":<18} {"Avg Total (B)"}')
    print('-' * 62)

    for proto in protocols:
        ok_records = [r for r in records if r['protocol'] == proto and r['status'] == 'ok']
        if not ok_records:
            print(f'  {proto:<10} {"N/A":<16} {"N/A":<18} {"N/A"}')
            continue

        avg_rtt:     float = round(sum(float(r['rtt_ms'])        for r in ok_records) / len(ok_records), 3)
        avg_payload: float = round(sum(float(r['payload_bytes']) for r in ok_records) / len(ok_records), 1)
        avg_total:   float = round(sum(float(r['total_bytes'])   for r in ok_records) / len(ok_records), 1)

        print(f'  {proto:<10} {avg_rtt:<16} {avg_payload:<18} {avg_total}')

    print('=' * 62)
    print()


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


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(n_requests: int) -> None:
    """Run the full CoAP vs HTTP benchmark."""
    print()
    print('=' * 55)
    print('  MODULE A — CoAP vs HTTP Benchmark')
    print('=' * 55)
    print()

    processes: list[subprocess.Popen[str]] = start_servers()

    print(f'\n  Waiting {STARTUP_WAIT}s for servers to initialise...\n')
    await asyncio.sleep(STARTUP_WAIT)

    coap_records: list[BenchmarkRecord] = await run_coap_benchmark(n_requests)
    http_records: list[BenchmarkRecord] = await run_http_benchmark(n_requests)

    all_records: list[BenchmarkRecord] = coap_records + http_records

    print_summary(all_records)
    save_csv(all_records)

    print('  Shutting down servers...')
    for proc in processes:
        proc.terminate()

    print('  Done. Run plot_results.py to generate charts.\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CoAP vs HTTP Benchmark')
    parser.add_argument('--requests', type=int, default=100, help='Number of requests per protocol')
    args = parser.parse_args()

    asyncio.run(main(args.requests))