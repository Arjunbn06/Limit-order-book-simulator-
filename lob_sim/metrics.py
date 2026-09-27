"""
metrics.py

Performance analytics for a completed AvellanedaStoikovStrategy run:
P&L, inventory behavior, spread captured per fill, and fill rate.

Deliberately kept separate from strategy.py: the strategy's job is to
trade, not to grade its own performance. This module reads the
strategy's recorded history/fills after the fact.
"""

import math


def compute_summary(strategy, final_mid_price):
    """
    Returns a dict of summary statistics for a completed run.

    `spread_captured` per fill is defined relative to the mid-price AT
    THE MOMENT OF THE FILL, not the strategy's own reservation price
    and not the end-of-run price. This isolates "did we trade on the
    correct side of fair value" from "did the market move against our
    inventory afterward" -- the latter is inventory risk, a separate
    (and often larger) effect, which is exactly why total spread
    captured and final mark-to-market P&L can disagree in sign.
    """
    fills = strategy.fills
    history = strategy.history

    num_fills = len(fills)
    num_buy_fills = sum(1 for f in fills if f["side"] == "buy")
    num_sell_fills = num_fills - num_buy_fills
    total_volume = sum(f["quantity"] for f in fills)

    def edge_of(f):
        if f["side"] == "buy":
            return (f["mid_at_fill"] - f["price"]) * f["quantity"]
        return (f["price"] - f["mid_at_fill"]) * f["quantity"]

    # Passive fills (we provided liquidity) and aggressive fills (our own
    # quote crossed the spread on placement, an inventory-unwind trade)
    # have fundamentally different expected economics and are reported
    # separately -- averaging them together hides which effect is which.
    passive = [f for f in fills if f.get("origin") == "passive" and f["mid_at_fill"] is not None]
    aggressive = [f for f in fills if f.get("origin") == "aggressive" and f["mid_at_fill"] is not None]

    passive_edges = [edge_of(f) for f in passive]
    aggressive_edges = [edge_of(f) for f in aggressive]
    all_edges = passive_edges + aggressive_edges

    spread_captured_total = sum(all_edges)
    avg_spread_captured_per_fill = (
        spread_captured_total / len(all_edges) if all_edges else 0.0
    )
    avg_edge_passive = sum(passive_edges) / len(passive_edges) if passive_edges else 0.0
    avg_edge_aggressive = (
        sum(aggressive_edges) / len(aggressive_edges) if aggressive_edges else 0.0
    )

    num_requotes = len(history)
    fill_rate = num_fills / num_requotes if num_requotes > 0 else 0.0

    inventories = [h["inventory"] for h in history]
    max_abs_inventory = max((abs(i) for i in inventories), default=0)
    mean_abs_inventory = (
        sum(abs(i) for i in inventories) / len(inventories) if inventories else 0.0
    )

    pnl_series = [h["mtm_pnl"] for h in history]
    max_drawdown = _max_drawdown(pnl_series)
    pnl_volatility = _stdev(_diffs(pnl_series))

    final_mtm_pnl = strategy.mark_to_market_pnl(final_mid_price)

    return {
        "num_requotes": num_requotes,
        "num_fills": num_fills,
        "num_buy_fills": num_buy_fills,
        "num_sell_fills": num_sell_fills,
        "total_volume": total_volume,
        "fill_rate_per_requote": fill_rate,
        "spread_captured_total": spread_captured_total,
        "avg_spread_captured_per_fill": avg_spread_captured_per_fill,
        "num_passive_fills": len(passive),
        "num_aggressive_fills": len(aggressive),
        "avg_edge_passive": avg_edge_passive,
        "avg_edge_aggressive": avg_edge_aggressive,
        "final_inventory": strategy.inventory,
        "final_cash": strategy.cash,
        "final_mtm_pnl": final_mtm_pnl,
        "max_abs_inventory": max_abs_inventory,
        "mean_abs_inventory": mean_abs_inventory,
        "max_drawdown": max_drawdown,
        "pnl_volatility": pnl_volatility,
    }


def format_summary(summary):
    """Human-readable report, e.g. for printing at the end of a run."""
    lines = [
        "--- Backtest Summary ---",
        f"Requotes:              {summary['num_requotes']}",
        f"Fills:                 {summary['num_fills']} "
        f"({summary['num_buy_fills']} buy / {summary['num_sell_fills']} sell)",
        f"Fill rate per requote:  {summary['fill_rate_per_requote']:.3f}",
        f"Total volume traded:   {summary['total_volume']}",
        "",
        f"Spread captured (total):        ${summary['spread_captured_total']:.2f}",
        f"Spread captured (avg/fill, all): ${summary['avg_spread_captured_per_fill']:.4f}",
        f"  passive fills:   {summary['num_passive_fills']:4d}   avg edge ${summary['avg_edge_passive']:.4f}",
        f"  aggressive fills:{summary['num_aggressive_fills']:4d}   avg edge ${summary['avg_edge_aggressive']:.4f}",
        "",
        f"Final inventory:       {summary['final_inventory']}",
        f"Final cash:            ${summary['final_cash']:.2f}",
        f"Final mark-to-market P&L: ${summary['final_mtm_pnl']:.2f}",
        "",
        f"Max |inventory|:       {summary['max_abs_inventory']}",
        f"Mean |inventory|:       {summary['mean_abs_inventory']:.2f}",
        f"Max drawdown (MTM P&L): ${summary['max_drawdown']:.2f}",
        f"P&L volatility (per requote step): ${summary['pnl_volatility']:.4f}",
    ]
    return "\n".join(lines)


# ---- small stats helpers (no numpy dependency needed for these) -------

def _diffs(series):
    return [series[i] - series[i - 1] for i in range(1, len(series))]


def _stdev(values):
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _max_drawdown(series):
    """Largest peak-to-trough decline in a P&L series (as a positive number)."""
    if not series:
        return 0.0
    peak = series[0]
    max_dd = 0.0
    for v in series:
        peak = max(peak, v)
        max_dd = max(max_dd, peak - v)
    return max_dd
