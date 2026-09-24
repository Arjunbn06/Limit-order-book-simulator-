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
- [ ] Matching engine — crossing logic for limit/market orders, partial fills
- [ ] Order flow simulation — Poisson arrivals for limit/market orders/cancels
- [ ] Avellaneda-Stoikov market-making strategy
- [ ] Performance metrics — P&L, inventory over time, spread captured, fill rate
- [ ] Unit tests for the matching engine
- [ ] Results / plots

## Model overview

**Order book.** Two sides — bids and asks — each organized by price level,
with orders at the same price level served in arrival order (price-time
priority). The book only stores *resting* intent to trade; a trade only
happens when an incoming order crosses the spread.

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
    orderbook.py     # core LOB data structure
    simulator.py      # matching engine + order flow simulation  [pending]
    strategy.py        # Avellaneda-Stoikov market maker          [pending]
    metrics.py          # P&L, inventory, fill-rate tracking       [pending]
tests/
    test_orderbook.py                                              [pending]
    test_matching_engine.py                                        [pending]
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
