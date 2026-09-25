# Limit Order Book Simulator & Market-Making Strategy

A research-grade simulation of a limit order book (LOB) with a market-making
agent implementing the **Avellaneda-Stoikov (2008)** optimal market-making
model. Built from first principles in Python: a price-time priority matching
engine, stochastic order flow, an inventory-aware quoting strategy, and
performance analytics.

## Motivation

Market makers profit by continuously quoting both sides of the book and
capturing the bid-ask spread, but every fill shifts their inventory and
exposes them to directional price risk. The Avellaneda-Stoikov model gives a
closed-form way to manage this trade-off: it derives a *reservation price*
(a fair value skewed by current inventory) and an *optimal spread* around it,
so the market maker's quotes automatically lean against their own risk as
their position builds up.

This project implements that model on top of a real matching engine — rather
than a simplified analytical simulation — so the strategy has to survive
actual order flow, queue position, and partial fills, not just a toy price
process.

## Status

This is an active, in-progress build. Current state:

- [x] Core order book data structure (`orderbook.py`) — price levels, FIFO
      queues per level, best bid/ask, spread, mid-price
- [x] Matching engine (`matching_engine.py`) — crossing logic for limit/market
      orders, multi-level sweeps, partial fills
- [x] Unit tests for the matching engine (7 tests, `tests/test_matching_engine.py`)
- [x] Order flow simulation (`simulator.py`) — Poisson-driven limit/market
      orders and cancellations, via superposition of Poisson processes
- [x] Avellaneda-Stoikov market-making strategy (`strategy.py`) +
      backtest runner (`backtest.py`)
- [ ] Dedicated metrics module — P&L/inventory/fill-rate currently tracked
      inline in `strategy.py`; a `metrics.py` with spread-captured and
      fill-rate analysis is still pending
- [ ] Results / plots in this README (currently only produced ad hoc)

## Model overview

**Order book.** Two sides — bids and asks — each organized by price level,
with orders at the same price level served in arrival order (price-time
priority). The book only stores *resting* intent to trade; a trade only
happens when an incoming order crosses the spread.

**Matching engine.** Kept deliberately separate from the order book itself:
the book only knows how to store orders, the engine decides how an incoming
order trades against them. An incoming order crosses the spread when a buy's
price is at or above the best ask (or a sell's price is at or below the best
bid); market orders always cross, at whatever price is available. On a
cross, the engine walks the opposite side from best price to worst, and
within each price level from front to back (time priority), consuming
resting orders until either the incoming order is filled or it stops
crossing. Leftover quantity on a limit order rests in the book; leftover
quantity on a market order is simply lost (market orders never rest).

**Order flow.** Synthetic "noise trader" activity — limit orders, market
orders, and cancellations — is generated using independent Poisson
processes, one per event type. Rather than simulating five separate clocks,
we use the *superposition* property of Poisson processes: the sum of
independent Poisson processes is itself Poisson at the combined rate, and
conditional on an event firing, its type is chosen randomly with probability
proportional to each type's own rate. Limit order prices are placed a random
(exponentially distributed) distance from the current mid-price, so most
orders land close to the touch with an occasional order landing further out
— giving the book realistic depth and a fat queue tail.

**Strategy (Avellaneda-Stoikov).** The market maker tracks its own inventory
`q` and cash, and periodically re-quotes a bid and ask around a *reservation
price* `r = s - q * gamma * sigma^2 * (T - t)`, where `s` is the current
mid-price and `(T - t)` is the fraction of the trading session remaining
(normalized to `[0, T]`, independent of how many real seconds the
simulation runs for). Positive (long) inventory pulls `r` below mid,
encouraging fills on the ask; negative (short) inventory pulls it above mid,
encouraging fills on the bid. The quoted half-spread around `r` widens with
risk aversion (`gamma`), volatility (`sigma`), and time remaining, with a
floor set by `k` (how readily orders arrive at a given distance from `r`).
**Calibration note:** these parameters must be scaled to the specific
simulated market's tick size and natural spread — textbook parameter values
produced a multi-dollar spread against a market that naturally trades at a
one-cent spread, resulting in almost no fills. `gamma`, `sigma`, and `k` were
retuned so the model's quoted spread sits close to the market's natural
spread, restoring realistic quoting/fill behavior.

**Avellaneda-Stoikov, in brief.** The model gives the market maker a
reservation price

```
r(s, q, t) = s - q * gamma * sigma^2 * (T - t)
```

where `s` is the current mid-price, `q` is current inventory, `gamma` is a
risk-aversion parameter, `sigma^2` is price volatility, and `(T - t)` is time
remaining in the trading horizon. Inventory `q` pulls the reservation price
away from the mid-price — long inventory pulls it down (encouraging sells),
short inventory pulls it up (encouraging buys). Quotes are then placed
symmetrically around `r`, at a width derived from `gamma`, `sigma`, and order
arrival intensity, balancing spread capture against inventory risk.

## Repository structure

```
lob_sim/
    orderbook.py         # core LOB data structure
    matching_engine.py    # crossing / fill logic
    simulator.py            # order flow simulation (Poisson arrivals)
    strategy.py               # Avellaneda-Stoikov market maker
    backtest.py                 # wires simulator + strategy together
    metrics.py                    # dedicated P&L/fill-rate analysis          [pending]
tests/
    test_matching_engine.py   # 7 tests: partial fills, multi-level sweeps,
                                # time priority, market orders, cancels
```

## Running it

Setup and usage instructions will be added as the simulator and strategy
modules land.

## What's next

See the Status checklist above. Once the full pipeline is in place, this
README will be extended with a Results section (P&L and inventory plots
across parameter settings) and a discussion of extensions — e.g. adaptive
volatility estimation, adverse-selection-aware quoting, and multi-asset
inventory management.
