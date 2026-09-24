"""
orderbook.py

Core Limit Order Book data structure.

This module ONLY defines how orders are stored and how price levels
are organized. Matching logic (deciding when orders trade) lives in
a separate step — see matching in simulator.py — so this stays a
clean, testable data structure.
"""

from collections import deque
from dataclasses import dataclass, field
from itertools import count
from sortedcontainers import SortedDict

# Monotonically increasing order IDs, also used to break ties for
# debugging/logging (NOT for matching priority — that's handled by
# the deque's FIFO ordering itself, which is separate from the ID).
_id_counter = count(1)


@dataclass
class Order:
    """A single resting order sitting in the book."""
    order_id: int
    side: str          # "buy" or "sell"
    price: float
    quantity: int       # remaining quantity (shrinks on partial fills)
    timestamp: float     # simulation time it was placed, for reference/logging


class OrderBook:
    """
    Holds two sides of the book:
      - self.bids: price -> deque[Order], sorted DESCENDING (best bid = highest price)
      - self.asks: price -> deque[Order], sorted ASCENDING  (best ask = lowest price)

    We use SortedDict for both. SortedDict keeps keys in ascending
    order internally; for bids we just read from the *end* of the
    key list to get the highest price, instead of maintaining a
    second descending structure. This keeps the code simple: one
    sorted structure, and we choose which end to look at.
    """

    def __init__(self):
        self.bids = SortedDict()   # price -> deque[Order]
        self.asks = SortedDict()   # price -> deque[Order]

    # ---- basic top-of-book queries -------------------------------

    def best_bid(self):
        """Highest price someone is willing to buy at, or None if no bids."""
        if not self.bids:
            return None
        return self.bids.peekitem(-1)[0]   # last key = highest price

    def best_ask(self):
        """Lowest price someone is willing to sell at, or None if no asks."""
        if not self.asks:
            return None
        return self.asks.peekitem(0)[0]    # first key = lowest price

    def spread(self):
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    def mid_price(self):
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2

    # ---- inserting a resting order (no matching happens here) ----

    def add_order(self, side, price, quantity, timestamp):
        """
        Add a new resting order directly to the book at `price`.

        IMPORTANT: this does NOT check whether the order crosses the
        spread. That decision ("should this match immediately or
        rest?") belongs to the matching engine in simulator.py, which
        will call add_order() only for the leftover quantity that
        doesn't get matched. Keeping that logic out of this class is
        deliberate — this class should only know how to store orders,
        not decide when they trade.
        """
        order = Order(
            order_id=next(_id_counter),
            side=side,
            price=price,
            quantity=quantity,
            timestamp=timestamp,
        )
        book_side = self.bids if side == "buy" else self.asks
        if price not in book_side:
            book_side[price] = deque()
        book_side[price].append(order)
        return order

    def remove_order(self, side, price, order_id):
        """Cancel a specific resting order by id. Returns True if removed."""
        book_side = self.bids if side == "buy" else self.asks
        if price not in book_side:
            return False
        q = book_side[price]
        for o in q:
            if o.order_id == order_id:
                q.remove(o)
                if not q:
                    del book_side[price]
                return True
        return False

    def __repr__(self):
        return f"OrderBook(best_bid={self.best_bid()}, best_ask={self.best_ask()})"
