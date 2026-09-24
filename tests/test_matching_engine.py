"""
tests/test_matching_engine.py

Covers the scenarios most likely to hide subtle bugs:
  - a non-crossing limit order just rests
  - a crossing limit order partially fills, leftover rests
  - an order sweeps through multiple price levels
  - time priority (FIFO) is respected within a price level
  - market orders consume available liquidity and never rest
  - market orders that exceed available liquidity partially fill, rest is lost
  - cancelling a resting order removes it from later matching
"""

import pytest
from lob_sim.orderbook import OrderBook
from lob_sim.matching_engine import MatchingEngine


@pytest.fixture
def engine():
    book = OrderBook()
    return MatchingEngine(book)


def test_non_crossing_limit_order_rests(engine):
    # Resting sell at 101, new buy at 100 does NOT cross -> should just rest.
    engine.process_limit_order("sell", 101.0, 50, timestamp=1)
    fills, resting = engine.process_limit_order("buy", 100.0, 30, timestamp=2)

    assert fills == []
    assert resting is not None
    assert resting.price == 100.0
    assert resting.quantity == 30
    assert engine.book.best_bid() == 100.0
    assert engine.book.best_ask() == 101.0


def test_crossing_limit_order_partial_fill_leftover_rests(engine):
    # Resting sell: 100 shares at $100 (Ashwin).
    engine.process_limit_order("sell", 100.0, 100, timestamp=1)
    # Incoming buy for 120 at $100 -> fills 100, leftover 20 rests as a bid.
    fills, resting = engine.process_limit_order("buy", 100.0, 120, timestamp=2)

    assert len(fills) == 1
    assert fills[0].quantity == 100
    assert fills[0].price == 100.0

    assert resting is not None
    assert resting.quantity == 20
    assert engine.book.best_bid() == 100.0
    assert engine.book.best_ask() is None  # ask side fully consumed


def test_sweep_multiple_price_levels(engine):
    # Two ask levels: 50 @ $100, 50 @ $100.50
    engine.process_limit_order("sell", 100.0, 50, timestamp=1)
    engine.process_limit_order("sell", 100.5, 50, timestamp=2)

    # Market-ish limit buy at $101 for 80 shares should sweep both levels.
    fills, resting = engine.process_limit_order("buy", 101.0, 80, timestamp=3)

    assert len(fills) == 2
    assert fills[0].price == 100.0
    assert fills[0].quantity == 50
    assert fills[1].price == 100.5
    assert fills[1].quantity == 30

    # 30 shares filled from the second level, 20 remain there.
    assert engine.book.best_ask() == 100.5
    asks_at_1005 = engine.book.asks[100.5]
    assert len(asks_at_1005) == 1
    assert asks_at_1005[0].quantity == 20

    # Nothing left over to rest — fully filled.
    assert resting is None


def test_time_priority_within_price_level(engine):
    # Ashwin (100), Bhavya (50), Chetan (200), all at $100, in that order.
    engine.process_limit_order("sell", 100.0, 100, timestamp=1)   # Ashwin
    engine.process_limit_order("sell", 100.0, 50, timestamp=2)    # Bhavya
    engine.process_limit_order("sell", 100.0, 200, timestamp=3)   # Chetan

    fills, _ = engine.process_market_order("buy", 120)

    assert len(fills) == 2
    # Ashwin fully filled first.
    assert fills[0].resting_order_id == 1
    assert fills[0].quantity == 100
    # Then Bhavya, partially.
    assert fills[1].resting_order_id == 2
    assert fills[1].quantity == 20

    # Bhavya has 30 left, Chetan untouched -- both still resting at $100.
    remaining_queue = engine.book.asks[100.0]
    assert len(remaining_queue) == 2
    assert remaining_queue[0].order_id == 2
    assert remaining_queue[0].quantity == 30
    assert remaining_queue[1].order_id == 3
    assert remaining_queue[1].quantity == 200


def test_market_order_never_rests(engine):
    engine.process_limit_order("sell", 100.0, 10, timestamp=1)
    # Market buy for more than available liquidity.
    fills, unfilled = engine.process_market_order("buy", 50)

    assert len(fills) == 1
    assert fills[0].quantity == 10
    assert unfilled == 40  # lost, not resting

    # Book has no asks left, and no phantom resting market order was created.
    assert engine.book.best_ask() is None


def test_cancel_removes_order_from_future_matching(engine):
    engine.process_limit_order("sell", 100.0, 50, timestamp=1)
    _, resting = engine.process_limit_order("sell", 100.0, 50, timestamp=2)

    cancelled = engine.cancel_order("sell", 100.0, resting.order_id)
    assert cancelled is True

    fills, unfilled = engine.process_market_order("buy", 80)
    # Only the first order's 50 shares are available now.
    assert len(fills) == 1
    assert fills[0].quantity == 50
    assert unfilled == 30


def test_new_order_at_same_price_goes_to_back_of_queue(engine):
    engine.process_limit_order("sell", 100.0, 100, timestamp=1)   # Ashwin
    engine.process_limit_order("sell", 100.0, 50, timestamp=2)    # Bhavya
    # Partially fill Bhavya (leaves her with 30), then Divya arrives.
    engine.process_market_order("buy", 120)  # consumes Ashwin(100) + 20 of Bhavya
    engine.process_limit_order("sell", 100.0, 40, timestamp=3)    # Divya

    queue = engine.book.asks[100.0]
    ids_in_order = [o.order_id for o in queue]
    # Bhavya's original order_id (2) must still precede Divya's (3), despite
    # Bhavya now holding less quantity than Divya.
    assert ids_in_order == [2, 3]
    assert queue[0].quantity == 30   # Bhavya's leftover
    assert queue[1].quantity == 40   # Divya
