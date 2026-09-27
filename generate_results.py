"""
generate_results.py

One-off script to produce the plots referenced in README's Results
section. Not part of the package itself -- run manually:
    python3 generate_results.py
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from lob_sim.backtest import run_backtest
from lob_sim.metrics import compute_summary, format_summary

STRATEGY_KWARGS = dict(gamma=0.005, sigma=2.0, k=300.0, T=1.0, quote_size=2)
SIM_KWARGS = dict(rate_limit=3.0, rate_market=1.0, rate_cancel=1.5)

book, engine, sim, strat = run_backtest(
    duration=500.0,
    requote_interval=1.0,
    initial_mid_price=100.0,
    strategy_kwargs=STRATEGY_KWARGS,
    simulator_kwargs=SIM_KWARGS,
    seed=42,
)

final_mid = book.mid_price()
summary = compute_summary(strat, final_mid)
print(format_summary(summary))

times = [h["time"] for h in strat.history]
invs = [h["inventory"] for h in strat.history]
pnls = [h["mtm_pnl"] for h in strat.history]
mids = [h["mid_price"] for h in strat.history]

# --- Plot 1: inventory + P&L over time -----------------------------------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)

ax1.plot(times, invs, color="#1f77b4", linewidth=1.2)
ax1.axhline(0, color="gray", linewidth=0.8, linestyle="--")
ax1.set_ylabel("Inventory (shares)")
ax1.set_title("Market maker inventory over the trading session")

ax2.plot(times, pnls, color="#d62728", linewidth=1.2)
ax2.axhline(0, color="gray", linewidth=0.8, linestyle="--")
ax2.set_ylabel("Mark-to-market P&L ($)")
ax2.set_xlabel("Normalized time (0 to T=1)")
ax2.set_title("Mark-to-market P&L over the trading session")

plt.tight_layout()
plt.savefig("assets/inventory_and_pnl.png", dpi=130)
plt.close(fig)

# --- Plot 2: spread captured distribution --------------------------------
edges = []
for f in strat.fills:
    if f["mid_at_fill"] is None:
        continue
    if f["side"] == "buy":
        edges.append((f["mid_at_fill"] - f["price"]) * f["quantity"])
    else:
        edges.append((f["price"] - f["mid_at_fill"]) * f["quantity"])

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.hist(edges, bins=40, color="#2ca02c", alpha=0.8)
ax.axvline(0, color="black", linewidth=1)
ax.axvline(sum(edges) / len(edges), color="red", linewidth=1.2, linestyle="--",
           label=f"mean = ${sum(edges)/len(edges):.4f}")
ax.set_xlabel("Spread captured per fill ($, vs. pre-trade mid)")
ax.set_ylabel("Number of fills")
ax.set_title("Distribution of spread captured per fill")
ax.legend()
plt.tight_layout()
plt.savefig("assets/spread_captured_distribution.png", dpi=130)
plt.close(fig)

print("\nSaved assets/inventory_and_pnl.png and assets/spread_captured_distribution.png")
