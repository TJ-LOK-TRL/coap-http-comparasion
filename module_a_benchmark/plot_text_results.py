# coap-demo/module_a_benchmark/plot_text_results.py

"""
Module A — Text Benchmark Report
Reads results/benchmark_results.csv and generates:
  - results/benchmark_report.txt   (full human + LLM-readable report)

If payload sweep data exists (results/payload_sweep/summary.csv),
the report also includes sweep analysis sections.

Usage:
    python plot_text_results.py
"""

import os
from io import StringIO

import pandas as pd


# ── Config ────────────────────────────────────────────────────────────────────

RESULTS_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results')
CSV_PATH:    str = os.path.join(RESULTS_DIR, 'benchmark_results.csv')
OUTPUT_PATH: str = os.path.join(RESULTS_DIR, 'benchmark_report.txt')

PROTOCOL_ORDER: list[str] = ['CoAP', 'HTTP']

# UDP MTU fragmentation boundary (bytes)
FRAG_BOUNDARY: int = 1500

# Column width for ASCII tables
COL_W: int = 18


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Load and filter benchmark CSV, keeping only successful requests."""
    df: pd.DataFrame = pd.read_csv(CSV_PATH)
    df = df[df['status'] == 'ok'].copy()
    df['rtt_ms']        = df['rtt_ms'].astype(float)
    df['payload_bytes'] = df['payload_bytes'].astype(int)
    df['total_bytes']   = df['total_bytes'].astype(int)
    return df


def load_sweep_summary() -> pd.DataFrame | None:
    """Load payload sweep summary CSV if it exists."""
    path = os.path.join(RESULTS_DIR, 'payload_sweep', 'summary.csv')
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df['payload_size']   = df['payload_size'].astype(int)
    df['avg_rtt_ms']     = df['avg_rtt_ms'].astype(float)
    df['std_dev_ms']     = df['std_dev_ms'].astype(float)
    df['jitter_ms']      = df['jitter_ms'].astype(float)
    df['avg_total_bytes'] = df['avg_total_bytes'].astype(float)
    return df


def calc_jitter(rtts: list[float]) -> float:
    """Mean absolute difference between consecutive RTTs (RFC 3550)."""
    if len(rtts) < 2:
        return 0.0
    return sum(abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))) / (len(rtts) - 1)


def fmt_bytes(n: int | float) -> str:
    """Human-readable byte size label."""
    n = int(n)
    if n >= 1024:
        return f'{n // 1024} KB ({n} B)'
    return f'{n} B'


def fmt_bytes_short(n: int | float) -> str:
    n = int(n)
    if n >= 1024:
        return f'{n // 1024}KB'
    return f'{n}B'


def separator(char: str = '─', width: int = 64) -> str:
    return char * width


def table_row(*cols: str, widths: list[int] | None = None) -> str:
    widths = widths or [COL_W] * len(cols)
    return '  ' + '  '.join(str(c).ljust(w) for c, w in zip(cols, widths))


def table_header(*cols: str, widths: list[int] | None = None) -> str:
    row = table_row(*cols, widths=widths)
    underline = table_row(*['-' * len(c) for c in cols], widths=widths)
    return row + '\n' + underline


# ── Section builders ──────────────────────────────────────────────────────────

def section_overview(df: pd.DataFrame) -> str:
    out = StringIO()

    total  = len(pd.read_csv(CSV_PATH))
    ok     = len(df)
    failed = total - ok

    out.write('SECTION 1 — OVERVIEW\n')
    out.write(separator() + '\n')
    out.write(f'  Total requests  : {total}\n')
    out.write(f'  Successful (ok) : {ok}\n')
    out.write(f'  Failed / errors : {failed}\n')
    out.write('\n')

    counts = df.groupby('protocol').size().reindex(PROTOCOL_ORDER)
    for proto in PROTOCOL_ORDER:
        out.write(f'  {proto} samples : {counts[proto]}\n')

    return out.getvalue()


def section_latency(df: pd.DataFrame) -> str:
    out = StringIO()

    summary = (
        df.groupby('protocol')['rtt_ms']
        .agg(['mean', 'median', 'min', 'max', 'std'])
        .reindex(PROTOCOL_ORDER)
    )

    out.write('SECTION 2 — LATENCY (RTT)\n')
    out.write(separator() + '\n')
    out.write('  All values in milliseconds.\n\n')

    widths = [10, 10, 10, 10, 10, 10]
    out.write(table_header('Protocol', 'Mean', 'Median', 'Min', 'Max', 'Std Dev', widths=widths) + '\n')

    for proto in PROTOCOL_ORDER:
        r = summary.loc[proto]
        out.write(table_row(
            proto,
            f'{r["mean"]:.3f}',
            f'{r["median"]:.3f}',
            f'{r["min"]:.3f}',
            f'{r["max"]:.3f}',
            f'{r["std"]:.3f}',
            widths=widths,
        ) + '\n')

    out.write('\n')

    # Relative comparison
    coap_mean = summary.loc['CoAP', 'mean']
    http_mean = summary.loc['HTTP', 'mean']

    if coap_mean < http_mean:
        faster, slower = 'CoAP', 'HTTP'
        ratio = http_mean / coap_mean
    else:
        faster, slower = 'HTTP', 'CoAP'
        ratio = coap_mean / http_mean

    out.write(f'  → {faster} is faster than {slower} by {ratio:.2f}× '
              f'(mean RTT: CoAP {coap_mean:.3f} ms vs HTTP {http_mean:.3f} ms)\n')

    return out.getvalue()


def section_packet_size(df: pd.DataFrame) -> str:
    out = StringIO()

    summary = (
        df.groupby('protocol')[['payload_bytes', 'total_bytes']]
        .mean()
        .reindex(PROTOCOL_ORDER)
    )
    summary['header_bytes']    = summary['total_bytes'] - summary['payload_bytes']
    summary['overhead_pct']    = summary['header_bytes'] / summary['total_bytes'] * 100

    out.write('SECTION 3 — PACKET SIZE\n')
    out.write(separator() + '\n')

    widths = [10, 16, 16, 16, 14]
    out.write(table_header(
        'Protocol', 'Avg Payload (B)', 'Avg Header (B)', 'Avg Total (B)', 'Header %',
        widths=widths,
    ) + '\n')

    for proto in PROTOCOL_ORDER:
        r = summary.loc[proto]
        out.write(table_row(
            proto,
            f'{r["payload_bytes"]:.1f}',
            f'{r["header_bytes"]:.1f}',
            f'{r["total_bytes"]:.1f}',
            f'{r["overhead_pct"]:.1f}%',
            widths=widths,
        ) + '\n')

    out.write('\n')

    coap_hdr = summary.loc['CoAP', 'header_bytes']
    http_hdr = summary.loc['HTTP', 'header_bytes']
    out.write(f'  → CoAP header overhead : {coap_hdr:.1f} B\n')
    out.write(f'  → HTTP header overhead : {http_hdr:.1f} B\n')
    out.write(f'  → HTTP adds {http_hdr - coap_hdr:.1f} B more header per request '
              f'({(http_hdr / coap_hdr):.2f}× CoAP)\n')

    return out.getvalue()


def section_rtt_distribution(df: pd.DataFrame) -> str:
    out = StringIO()

    out.write('SECTION 4 — RTT DISTRIBUTION (PERCENTILES)\n')
    out.write(separator() + '\n')
    out.write('  Percentile values in milliseconds.\n\n')

    percentiles = [10, 25, 50, 75, 90, 95, 99]
    labels = [f'p{p}' for p in percentiles]
    widths = [10] + [8] * len(percentiles)
    out.write(table_header('Protocol', *labels, widths=widths) + '\n')

    for proto in PROTOCOL_ORDER:
        rtts = df[df['protocol'] == proto]['rtt_ms']
        vals = [f'{rtts.quantile(p / 100):.3f}' for p in percentiles]
        out.write(table_row(proto, *vals, widths=widths) + '\n')

    out.write('\n')

    for proto in PROTOCOL_ORDER:
        rtts = df[df['protocol'] == proto]['rtt_ms']
        iqr  = rtts.quantile(0.75) - rtts.quantile(0.25)
        out.write(f'  {proto} IQR (p25–p75): {iqr:.3f} ms\n')

    return out.getvalue()


def section_jitter(df: pd.DataFrame) -> str:
    out = StringIO()

    out.write('SECTION 5 — JITTER\n')
    out.write(separator() + '\n')
    out.write('  Jitter = mean absolute difference between consecutive RTTs (RFC 3550).\n\n')

    widths = [10, 14]
    out.write(table_header('Protocol', 'Jitter (ms)', widths=widths) + '\n')

    jitter_map: dict[str, float] = {}
    for proto in PROTOCOL_ORDER:
        rtts = df[df['protocol'] == proto]['rtt_ms'].tolist()
        j    = calc_jitter(rtts)
        jitter_map[proto] = j
        out.write(table_row(proto, f'{j:.4f}', widths=widths) + '\n')

    out.write('\n')

    coap_j = jitter_map['CoAP']
    http_j = jitter_map['HTTP']
    if coap_j < http_j:
        out.write(f'  → CoAP has lower jitter ({coap_j:.4f} ms vs {http_j:.4f} ms), '
                  f'meaning more consistent latency.\n')
    else:
        out.write(f'  → HTTP has lower jitter ({http_j:.4f} ms vs {coap_j:.4f} ms), '
                  f'meaning more consistent latency.\n')

    return out.getvalue()


# ── Sweep sections ────────────────────────────────────────────────────────────

def section_sweep_rtt(df: pd.DataFrame) -> str:
    out = StringIO()

    out.write('SECTION 6 — PAYLOAD SWEEP: AVG RTT vs PAYLOAD SIZE\n')
    out.write(separator() + '\n')
    out.write('  Avg RTT ± Std Dev in milliseconds for each payload size.\n')
    out.write(f'  Note: UDP MTU fragmentation boundary at {FRAG_BOUNDARY} B.\n\n')

    sizes = sorted(df['payload_size'].unique())
    widths = [10, 18, 18]
    out.write(table_header('Size', 'CoAP avg RTT ± σ', 'HTTP avg RTT ± σ', widths=widths) + '\n')

    coap_df = df[df['protocol'] == 'CoAP'].set_index('payload_size')
    http_df = df[df['protocol'] == 'HTTP'].set_index('payload_size')

    for size in sizes:
        marker = ' ← MTU boundary' if size == FRAG_BOUNDARY else (
                 ' ← above MTU'   if size > FRAG_BOUNDARY else '')

        coap_val = (f'{coap_df.loc[size, "avg_rtt_ms"]:.2f} ± {coap_df.loc[size, "std_dev_ms"]:.2f}'
                    if size in coap_df.index else 'N/A')
        http_val = (f'{http_df.loc[size, "avg_rtt_ms"]:.2f} ± {http_df.loc[size, "std_dev_ms"]:.2f}'
                    if size in http_df.index else 'N/A')

        out.write(table_row(fmt_bytes_short(size), coap_val, http_val, widths=widths)
                  + marker + '\n')

    return out.getvalue()


def section_sweep_jitter(df: pd.DataFrame) -> str:
    out = StringIO()

    out.write('SECTION 7 — PAYLOAD SWEEP: JITTER vs PAYLOAD SIZE\n')
    out.write(separator() + '\n')
    out.write('  Jitter in milliseconds.\n\n')

    sizes = sorted(df['payload_size'].unique())
    widths = [10, 14, 14]
    out.write(table_header('Size', 'CoAP jitter', 'HTTP jitter', widths=widths) + '\n')

    coap_df = df[df['protocol'] == 'CoAP'].set_index('payload_size')
    http_df = df[df['protocol'] == 'HTTP'].set_index('payload_size')

    for size in sizes:
        coap_j = f'{coap_df.loc[size, "jitter_ms"]:.4f}' if size in coap_df.index else 'N/A'
        http_j = f'{http_df.loc[size, "jitter_ms"]:.4f}' if size in http_df.index else 'N/A'
        out.write(table_row(fmt_bytes_short(size), coap_j, http_j, widths=widths) + '\n')

    return out.getvalue()


def section_sweep_overhead(df: pd.DataFrame) -> str:
    out = StringIO()

    out.write('SECTION 8 — PAYLOAD SWEEP: HEADER OVERHEAD vs PAYLOAD SIZE\n')
    out.write(separator() + '\n')
    out.write('  Header overhead = avg_total_bytes - payload_size (in bytes).\n\n')

    sizes = sorted(df['payload_size'].unique())
    widths = [10, 16, 16, 18]
    out.write(table_header('Size', 'CoAP overhead', 'HTTP overhead', 'Difference (H−C)', widths=widths) + '\n')

    coap_df = df[df['protocol'] == 'CoAP'].set_index('payload_size')
    http_df = df[df['protocol'] == 'HTTP'].set_index('payload_size')

    for size in sizes:
        coap_o = coap_df.loc[size, 'avg_total_bytes'] - size if size in coap_df.index else None
        http_o = http_df.loc[size, 'avg_total_bytes'] - size if size in http_df.index else None
        diff   = f'{http_o - coap_o:.1f} B' if coap_o is not None and http_o is not None else 'N/A'
        out.write(table_row(
            fmt_bytes_short(size),
            f'{coap_o:.1f} B' if coap_o is not None else 'N/A',
            f'{http_o:.1f} B' if http_o is not None else 'N/A',
            diff,
            widths=widths,
        ) + '\n')

    return out.getvalue()


def section_sweep_crossover(df: pd.DataFrame) -> str:
    out = StringIO()

    out.write('SECTION 9 — PAYLOAD SWEEP: CoAP/HTTP RTT RATIO vs PAYLOAD SIZE\n')
    out.write(separator() + '\n')
    out.write('  Ratio = CoAP avg RTT ÷ HTTP avg RTT.\n')
    out.write('  Ratio < 1.00 → CoAP is faster.\n')
    out.write('  Ratio > 1.00 → HTTP is faster.\n\n')

    coap = df[df['protocol'] == 'CoAP'].set_index('payload_size')['avg_rtt_ms']
    http = df[df['protocol'] == 'HTTP'].set_index('payload_size')['avg_rtt_ms']
    common = sorted(coap.index.intersection(http.index))

    widths = [10, 12, 12, 12, 20]
    out.write(table_header('Size', 'CoAP (ms)', 'HTTP (ms)', 'Ratio', 'Faster protocol', widths=widths) + '\n')

    for size in common:
        c = coap[size]
        h = http[size]
        ratio = c / h
        faster = 'CoAP' if ratio < 1.0 else ('HTTP' if ratio > 1.0 else 'Tie')
        out.write(table_row(
            fmt_bytes_short(size),
            f'{c:.3f}',
            f'{h:.3f}',
            f'{ratio:.3f}×',
            faster,
            widths=widths,
        ) + '\n')

    # Crossover detection
    out.write('\n')
    crossovers = []
    prev_faster = None
    for size in common:
        ratio = coap[size] / http[size]
        cur_faster = 'CoAP' if ratio < 1.0 else 'HTTP'
        if prev_faster is not None and cur_faster != prev_faster:
            crossovers.append(size)
        prev_faster = cur_faster

    if crossovers:
        for s in crossovers:
            out.write(f'  → Crossover detected near {fmt_bytes_short(s)}: '
                      f'advantage switches around this payload size.\n')
    else:
        winner = 'CoAP' if coap[common[0]] < http[common[0]] else 'HTTP'
        out.write(f'  → No crossover detected. {winner} is faster across all measured payload sizes.\n')

    return out.getvalue()


def section_summary(df: pd.DataFrame, sweep_df: pd.DataFrame | None) -> str:
    out = StringIO()

    out.write('SECTION 10 — SUMMARY & KEY TAKEAWAYS\n')
    out.write(separator() + '\n')

    coap_rtt = df[df['protocol'] == 'CoAP']['rtt_ms'].mean()
    http_rtt = df[df['protocol'] == 'HTTP']['rtt_ms'].mean()
    coap_total = df[df['protocol'] == 'CoAP']['total_bytes'].mean()
    http_total = df[df['protocol'] == 'HTTP']['total_bytes'].mean()
    coap_j = calc_jitter(df[df['protocol'] == 'CoAP']['rtt_ms'].tolist())
    http_j = calc_jitter(df[df['protocol'] == 'HTTP']['rtt_ms'].tolist())

    out.write('  Latency:\n')
    out.write(f'    CoAP mean RTT = {coap_rtt:.3f} ms\n')
    out.write(f'    HTTP mean RTT = {http_rtt:.3f} ms\n')
    faster_rtt = 'CoAP' if coap_rtt < http_rtt else 'HTTP'
    out.write(f'    → {faster_rtt} wins on latency '
              f'({min(coap_rtt, http_rtt):.3f} vs {max(coap_rtt, http_rtt):.3f} ms)\n\n')

    out.write('  Bandwidth:\n')
    out.write(f'    CoAP avg total bytes = {coap_total:.1f} B\n')
    out.write(f'    HTTP avg total bytes = {http_total:.1f} B\n')
    smaller = 'CoAP' if coap_total < http_total else 'HTTP'
    out.write(f'    → {smaller} uses less bandwidth per request '
              f'({min(coap_total, http_total):.1f} vs {max(coap_total, http_total):.1f} B)\n\n')

    out.write('  Jitter:\n')
    out.write(f'    CoAP jitter = {coap_j:.4f} ms\n')
    out.write(f'    HTTP jitter = {http_j:.4f} ms\n')
    steadier = 'CoAP' if coap_j < http_j else 'HTTP'
    out.write(f'    → {steadier} has more consistent latency\n\n')

    if sweep_df is not None:
        out.write('  Payload Sweep Insights:\n')
        coap_s = sweep_df[sweep_df['protocol'] == 'CoAP'].set_index('payload_size')['avg_rtt_ms']
        http_s = sweep_df[sweep_df['protocol'] == 'HTTP'].set_index('payload_size')['avg_rtt_ms']
        common = sorted(coap_s.index.intersection(http_s.index))
        for size in common:
            ratio = coap_s[size] / http_s[size]
            label = f'CoAP {1/ratio:.2f}× faster' if ratio < 1.0 else f'HTTP {ratio:.2f}× faster'
            above = ' [above MTU]' if size > FRAG_BOUNDARY else ''
            out.write(f'    {fmt_bytes_short(size)}{above}: {label}\n')
        out.write(f'\n    UDP MTU fragmentation boundary = {FRAG_BOUNDARY} B\n')

    return out.getvalue()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """Load results CSV and write a full text benchmark report."""
    if not os.path.exists(CSV_PATH):
        print(f'[ERROR] CSV not found: {CSV_PATH}')
        print('  Run benchmark.py first.')
        return

    os.makedirs(RESULTS_DIR, exist_ok=True)

    print()
    print('Generating text benchmark report...')
    print()

    df       = load_data()
    sweep_df = load_sweep_summary()

    lines: list[str] = []

    lines.append('=' * 64)
    lines.append('  CoAP vs HTTP — BENCHMARK REPORT')
    lines.append('  (Text version — suitable for LLM analysis)')
    lines.append('=' * 64)
    lines.append('')

    lines.append(section_overview(df))
    lines.append(section_latency(df))
    lines.append(section_packet_size(df))
    lines.append(section_rtt_distribution(df))
    lines.append(section_jitter(df))

    if sweep_df is not None:
        print('  Sweep summary found — including sweep sections...')
        lines.append(section_sweep_rtt(sweep_df))
        lines.append(section_sweep_jitter(sweep_df))
        lines.append(section_sweep_overhead(sweep_df))
        lines.append(section_sweep_crossover(sweep_df))
    else:
        print('  (No payload sweep data found — skipping sweep sections.)')

    lines.append(section_summary(df, sweep_df))

    lines.append('=' * 64)
    lines.append('  END OF REPORT')
    lines.append('=' * 64)
    lines.append('')

    report = '\n'.join(lines)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(report)

    # Also print to stdout so it's visible immediately
    print()
    print(report)
    print(f'Report saved to: {OUTPUT_PATH}')
    print()


if __name__ == '__main__':
    main()