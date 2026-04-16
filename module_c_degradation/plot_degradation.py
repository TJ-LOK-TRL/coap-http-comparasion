# coap-demo/module_c_degradation/plot_degradation.py

"""
Module C — Plot Degradation Results
Reads results/degradation_results.csv and generates:
  - results/degradation_success_rate.png   (success rate vs loss % for CON vs NON)
  - results/degradation_rtt.png            (avg RTT vs loss % for successful requests)

Usage:
    python plot_degradation.py
"""

import os

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


# ── Config ────────────────────────────────────────────────────────────────────

RESULTS_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results')
CSV_PATH:    str = os.path.join(RESULTS_DIR, 'degradation_results.csv')

COLOUR_CON: str = '#2196F3'   # blue
COLOUR_NON: str = '#FF5722'   # deep orange

LOSS_LEVELS: list[int] = [0, 5, 10, 20, 30]


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Load degradation CSV into a DataFrame."""
    df: pd.DataFrame = pd.read_csv(CSV_PATH)
    df['success'] = df['success'].astype(int)
    df['rtt_ms']  = pd.to_numeric(df['rtt_ms'], errors='coerce')
    return df


def save(fig: plt.Figure, filename: str) -> None:
    """Save figure to the results directory."""
    path: str = os.path.join(RESULTS_DIR, filename)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    print(f'  Saved: {path}')
    plt.close(fig)


def success_rate(df: pd.DataFrame, msg_type: str, loss_pct: int, n: int) -> float:
    """Compute success rate (0.0–1.0) for a given message type and loss level."""
    subset = df[(df['msg_type'] == msg_type) & (df['loss_pct'] == loss_pct)]
    if subset.empty:
        return 0.0
    return float(subset['success'].sum()) / n * 100.0


def avg_rtt(df: pd.DataFrame, msg_type: str, loss_pct: int) -> float:
    """Compute average RTT for successful requests only. Returns -1 if none."""
    subset = df[
        (df['msg_type'] == msg_type) &
        (df['loss_pct'] == loss_pct) &
        (df['success']  == 1)
    ]
    if subset.empty:
        return -1.0
    return float(subset['rtt_ms'].mean())


# ── Charts ────────────────────────────────────────────────────────────────────

def plot_success_rate(df: pd.DataFrame, n: int) -> None:
    """Line chart: success rate (%) vs packet loss (%) for CON and NON."""
    con_rates: list[float] = [success_rate(df, 'CON', l, n) for l in LOSS_LEVELS]
    non_rates: list[float] = [success_rate(df, 'NON', l, n) for l in LOSS_LEVELS]

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.plot(LOSS_LEVELS, con_rates, marker='o', linewidth=2.0, color=COLOUR_CON, label='CON (Confirmable)')
    ax.plot(LOSS_LEVELS, non_rates, marker='s', linewidth=2.0, color=COLOUR_NON, label='NON (Non-confirmable)', linestyle='--')

    # Annotate each point
    for x, y in zip(LOSS_LEVELS, con_rates):
        ax.annotate(f'{y:.0f}%', (x, y), textcoords='offset points', xytext=(0, 8), ha='center', fontsize=8, color=COLOUR_CON)
    for x, y in zip(LOSS_LEVELS, non_rates):
        ax.annotate(f'{y:.0f}%', (x, y), textcoords='offset points', xytext=(0, -14), ha='center', fontsize=8, color=COLOUR_NON)

    ax.set_title('Success Rate vs Packet Loss: CON vs NON', fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('Simulated Packet Loss (%)')
    ax.set_ylabel('Success Rate (%)')
    ax.set_xticks(LOSS_LEVELS)
    ax.set_ylim(0, 110)
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.grid(linestyle='--', alpha=0.5)
    ax.legend()

    fig.tight_layout()
    save(fig, 'degradation_success_rate.png')


def plot_rtt_vs_loss(df: pd.DataFrame) -> None:
    """Line chart: avg RTT (ms) of successful requests vs packet loss (%) for CON and NON."""
    con_rtts: list[float | None] = [avg_rtt(df, 'CON', l) for l in LOSS_LEVELS]
    non_rtts: list[float | None] = [avg_rtt(df, 'NON', l) for l in LOSS_LEVELS]

    # Replace -1 (no data) with None for clean gaps in the line
    con_plot: list[float | None] = [v if v >= 0 else None for v in con_rtts]
    non_plot: list[float | None] = [v if v >= 0 else None for v in non_rtts]

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.plot(LOSS_LEVELS, con_plot, marker='o', linewidth=2.0, color=COLOUR_CON, label='CON (Confirmable)')
    ax.plot(LOSS_LEVELS, non_plot, marker='s', linewidth=2.0, color=COLOUR_NON, label='NON (Non-confirmable)', linestyle='--')

    ax.set_title('Avg RTT of Successful Requests vs Packet Loss', fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('Simulated Packet Loss (%)')
    ax.set_ylabel('Avg RTT (ms)')
    ax.set_xticks(LOSS_LEVELS)
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.grid(linestyle='--', alpha=0.5)
    ax.legend()

    fig.tight_layout()
    save(fig, 'degradation_rtt.png')


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """Load degradation CSV and generate all charts."""
    if not os.path.exists(CSV_PATH):
        print(f'[ERROR] CSV not found: {CSV_PATH}')
        print('  Run degradation_test.py first.')
        return

    os.makedirs(RESULTS_DIR, exist_ok=True)

    print()
    print('Generating degradation charts...')
    print()

    df: pd.DataFrame = load_data()

    # Infer n from the data: total requests per msg_type per loss level
    n: int = int(df[df['loss_pct'] == 0]['msg_type'].value_counts().max())

    plot_success_rate(df, n)
    plot_rtt_vs_loss(df)

    print()
    print('All charts saved to results/')
    print()


if __name__ == '__main__':
    main()