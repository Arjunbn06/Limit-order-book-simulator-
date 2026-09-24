"""
matching_engine.py

The matching engine decides HOW an incoming order interacts with the
OrderBook: how much of it trades immediately (against resting orders
on the opposite side), and how much (if any) rests afterward.

Deliberately separate from OrderBook (orderbook.py): OrderBook only
knows how to store/retrieve orders. This module owns all the
decision logic about crossing and fills.
"""

from dataclasses import dataclass


@dataclass
class Fill:
    """A single trade resulting from matching."""
    price: float
    quantity: int
    resting_order_id: int   # the order that was already in the book
    incoming_side: str      # "buy" or "sell" — side of the aggressor


class MatchingEngine:
    def __init__(self, order_book):
        self.book = order_book

    def process_limit_order(self, side, price, quantity, timestamp):
        """
        Submit a new limit order. Matches against the opposite side
        while price allows, then rests any leftover quantity in the
        book. Returns (fills, resting_order_or_None).
        """
        fills, remaining = self._match(side, price, quantity, is_market=False)
        resting = None
        if remaining > 0:
            resting = self.book.add_order(side, price, remaining, timestamp)
        return fills, resting

    def process_market_order(self, side, quantity):
        """
        Submit a market order: matches against the opposite side at
        whatever prices are available, ignoring price entirely.
        Leftover (if the book runs out of liquidity) is NOT rested —
        market orders never sit in the book.
        """
        fills, remaining = self._match(side, price=None, quantity=quantity, is_market=True)
        return fills, remaining  # remaining = unfilled quantity, lost (no liquidity)

    def cancel_order(self, side, price, order_id):
        return self.book.remove_order(side, price, order_id)

    # ---- internal matching loop -----------------------------------

    def _match(self, side, price, quantity, is_market):
        """
        Core matching loop, shared by limit and market orders.

        `side` is the side of the INCOMING order. It matches against
        the opposite side of the book.
        """
        fills = []
        opposite_book = self.book.asks if side == "buy" else self.book.bids
        remaining = quantity

        while remaining > 0 and len(opposite_book) > 0:
            best_price = self._best_opposite_price(side)

            if not is_market:
                # Limit order: stop if price no longer crosses.
                if side == "buy" and price < best_price:
                    break
                if side == "sell" and price > best_price:
                    break

            queue = opposite_book[best_price]

            # Walk the queue at this price level, front to back (time priority).
            while remaining > 0 and queue:
                resting_order = queue[0]
                traded_qty = min(remaining, resting_order.quantity)

                fills.append(Fill(
                    price=best_price,
                    quantity=traded_qty,
                    resting_order_id=resting_order.order_id,
                    incoming_side=side,
                ))

                resting_order.quantity -= traded_qty
                remaining -= traded_qty

                if resting_order.quantity == 0:
                    queue.popleft()   # fully consumed, remove from queue

            if not queue:
                del opposite_book[best_price]   # price level exhausted

        return fills, remaining

    def _best_opposite_price(self, side):
        return self.book.best_ask() if side == "buy" else self.book.best_bid()
