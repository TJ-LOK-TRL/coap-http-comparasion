# coap-demo/module_a_benchmark/plot_results.py

"""
Module A — Plot Benchmark Results
Reads results/benchmark_results.csv and generates:
  - results/latency_chart.png       (avg RTT per protocol)
  - results/packetsize_chart.png    (avg total bytes per protocol)
  - results/rtt_distribution.png   (RTT distribution box plot)

Usage:
    python plot_results.py
"""

import os

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns


# ── Config ────────────────────────────────────────────────────────────────────

RESULTS_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results')
CSV_PATH:    str = os.path.join(RESULTS_DIR, 'benchmark_results.csv')

COLOUR_COAP: str = '#2196F3'   # blue
COLOUR_HTTP: str = '#FF5722'   # deep orange

PROTOCOL_ORDER: list[str] = ['CoAP', 'HTTP']


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Load and filter benchmark CSV, keeping only successful requests."""
    df: pd.DataFrame = pd.read_csv(CSV_PATH)
    df = df[df['status'] == 'ok'].copy()
    df['rtt_ms']        = df['rtt_ms'].astype(float)
    df['payload_bytes'] = df['payload_bytes'].astype(int)
    df['total_bytes']   = df['total_bytes'].astype(int)
    return df


def save(fig: plt.Figure, filename: str) -> None:
    """Save a figure to the results directory."""
    path: str = os.path.join(RESULTS_DIR, filename)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    print(f'  Saved: {path}')
    plt.close(fig)


# ── Charts ────────────────────────────────────────────────────────────────────

def plot_latency(df: pd.DataFrame) -> None:
    """Bar chart: average RTT (ms) per protocol."""
    summary: pd.DataFrame = (
        df.groupby('protocol')['rtt_ms']
        .mean()
        .reindex(PROTOCOL_ORDER)
        .reset_index()
    )
    summary.columns = pd.Index(['protocol', 'avg_rtt_ms'])

    colours: list[str] = [COLOUR_COAP, COLOUR_HTTP]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(summary['protocol'], summary['avg_rtt_ms'], color=colours, width=0.45, zorder=3)

    for bar, val in zip(bars, summary['avg_rtt_ms']):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.05,
            f'{val:.2f} ms',
            ha='center', va='bottom', fontsize=10, fontweight='bold',
        )

    ax.set_title('Average Round-Trip Time: CoAP vs HTTP', fontsize=13, fontweight='bold', pad=12)
    ax.set_ylabel('Average RTT (ms)')
    ax.set_xlabel('Protocol')
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    save(fig, 'latency_chart.png')


def plot_packet_size(df: pd.DataFrame) -> None:
    """Stacked bar chart: average payload bytes vs header overhead per protocol."""
    summary: pd.DataFrame = (
        df.groupby('protocol')[['payload_bytes', 'total_bytes']]
        .mean()
        .reindex(PROTOCOL_ORDER)
        .reset_index()
    )
    summary['header_bytes'] = summary['total_bytes'] - summary['payload_bytes']

    colours_payload: list[str] = [COLOUR_COAP, COLOUR_HTTP]
    colours_header:  list[str] = ['#90CAF9', '#FFAB91']

    x: list[str] = list(summary['protocol'])
    fig, ax = plt.subplots(figsize=(6, 4))

    ax.bar(x, summary['payload_bytes'], color=colours_payload, width=0.45, label='Payload', zorder=3)
    ax.bar(x, summary['header_bytes'],  color=colours_header,  width=0.45,
           bottom=summary['payload_bytes'], label='Header overhead', zorder=3)

    for i, row in summary.iterrows():
        ax.text(
            i, float(row['total_bytes']) + 1,
            f'{int(row["total_bytes"])} B',
            ha='center', va='bottom', fontsize=10, fontweight='bold',
        )

    ax.set_title('Average Packet Size: CoAP vs HTTP', fontsize=13, fontweight='bold', pad=12)
    ax.set_ylabel('Bytes')
    ax.set_xlabel('Protocol')
    ax.legend(loc='upper left')
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    save(fig, 'packetsize_chart.png')


def plot_rtt_distribution(df: pd.DataFrame) -> None:
    """Box plot: RTT distribution per protocol."""
    palette: dict[str, str] = {'CoAP': COLOUR_COAP, 'HTTP': COLOUR_HTTP}

    fig, ax = plt.subplots(figsize=(6, 4))
    sns.boxplot(
        data=df,
        x='protocol',
        y='rtt_ms',
        order=PROTOCOL_ORDER,
        palette=palette,
        width=0.4,
        linewidth=1.2,
        flierprops={'marker': 'o', 'markersize': 3, 'alpha': 0.5},
        ax=ax,
    )

    ax.set_title('RTT Distribution: CoAP vs HTTP', fontsize=13, fontweight='bold', pad=12)
    ax.set_ylabel('RTT (ms)')
    ax.set_xlabel('Protocol')
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    save(fig, 'rtt_distribution.png')


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """Load results CSV and generate all benchmark charts."""
    if not os.path.exists(CSV_PATH):
        print(f'[ERROR] CSV not found: {CSV_PATH}')
        print('  Run benchmark.py first.')
        return

    os.makedirs(RESULTS_DIR, exist_ok=True)

    print()
    print('Generating benchmark charts...')
    print()

    df: pd.DataFrame = load_data()

    plot_latency(df)
    plot_packet_size(df)
    plot_rtt_distribution(df)

    print()
    print('All charts saved to results/')
    print()


if __name__ == '__main__':
    main()