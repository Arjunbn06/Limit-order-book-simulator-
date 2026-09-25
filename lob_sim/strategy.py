"""
strategy.py

Avellaneda-Stoikov (2008) optimal market-making strategy.

The strategy holds inventory and cash, quotes a bid and an ask around
a "reservation price" that skews away from the mid-price based on
current inventory, and re-quotes periodically as the market moves.
"""

import math


class AvellanedaStoikovStrategy:
    def __init__(
        self,
        engine,
        gamma=0.1,        # risk aversion: higher = skews harder against inventory
        sigma=2.0,        # assumed volatility of the mid-price (per unit time)
        T=1.0,             # trading horizon (e.g. 1.0 = "end of day")
        k=1.5,               # order arrival intensity param (controls spread width)
        tick_size=0.01,
        quote_size=10,
    ):
        self.engine = engine
        self.book = engine.book

        self.gamma = gamma
        self.sigma = sigma
        self.T = T
        self.k = k
        self.tick_size = tick_size
        self.quote_size = quote_size

        self.inventory = 0
        self.cash = 0.0

        self.active_bid = None   # Order object currently resting, or None
        self.active_ask = None

        # history for later analysis/plots: (time, inventory, cash, mtm_pnl)
        self.history = []

    # ---- Avellaneda-Stoikov formulas -----------------------------------

    def reservation_price(self, mid_price, t):
        """
        r(s, q, t) = s - q * gamma * sigma^2 * (T - t)

        Inventory q pulls the reservation price away from mid: positive
        (long) inventory pulls it DOWN (we want to sell), negative
        (short) inventory pulls it UP (we want to buy).
        """
        time_remaining = max(self.T - t, 0.0)
        return mid_price - self.inventory * self.gamma * (self.sigma ** 2) * time_remaining

    def optimal_spread(self, t):
        """
        delta = gamma * sigma^2 * (T - t) + (2/gamma) * ln(1 + gamma/k)

        First term: widens as risk aversion, volatility, or remaining
        time increase (more uncertainty ahead -> demand more compensation).
        Second term: a floor coming from how densely orders arrive at
        each price (k) -- if orders arrive very readily even far from
        mid, there's less need to quote tight to get filled.
        """
        time_remaining = max(self.T - t, 0.0)
        return self.gamma * (self.sigma ** 2) * time_remaining + (2.0 / self.gamma) * math.log(1 + self.gamma / self.k)

    def quote_prices(self, mid_price, t):
        r = self.reservation_price(mid_price, t)
        spread = self.optimal_spread(t)
        bid = r - spread / 2.0
        ask = r + spread / 2.0
        bid = round(bid / self.tick_size) * self.tick_size
        ask = round(ask / self.tick_size) * self.tick_size
        # Safety: never cross our own bid/ask due to rounding at tiny spreads.
        if bid >= ask:
            ask = bid + self.tick_size
        return bid, ask

    # ---- quoting lifecycle ----------------------------------------------

    def cancel_existing_quotes(self):
        if self.active_bid is not None and self.active_bid.quantity > 0:
            self.engine.cancel_order("buy", self.active_bid.price, self.active_bid.order_id)
        if self.active_ask is not None and self.active_ask.quantity > 0:
            self.engine.cancel_order("sell", self.active_ask.price, self.active_ask.order_id)
        self.active_bid = None
        self.active_ask = None

    def requote(self, mid_price, t):
        """Cancel old quotes (if any) and place fresh bid/ask around the
        current reservation price."""
        self.cancel_existing_quotes()
        bid_price, ask_price = self.quote_prices(mid_price, t)

        bid_fills, bid_order = self.engine.process_limit_order(
            "buy", bid_price, self.quote_size, timestamp=t
        )
        for f in bid_fills:
            self._apply_fill(f, side="buy")

        ask_fills, ask_order = self.engine.process_limit_order(
            "sell", ask_price, self.quote_size, timestamp=t
        )
        for f in ask_fills:
            self._apply_fill(f, side="sell")

        # Only keep a reference if quantity actually remains resting
        # (an order that fully crossed on placement won't be in the book).
        self.active_bid = bid_order if (bid_order and bid_order.quantity > 0) else None
        self.active_ask = ask_order if (ask_order and ask_order.quantity > 0) else None

        self._record(t, mid_price)

    # ---- fill handling ----------------------------------------------------

    def on_fill(self, fill):
        """Callback for fills produced by OTHER participants' orders that
        happen to land against our resting quotes."""
        if self.active_bid is not None and fill.resting_order_id == self.active_bid.order_id:
            self._apply_fill(fill, side="buy")
        elif self.active_ask is not None and fill.resting_order_id == self.active_ask.order_id:
            self._apply_fill(fill, side="sell")

    def _apply_fill(self, fill, side):
        """We got filled on `side` at fill.price for fill.quantity."""
        if side == "buy":
            self.inventory += fill.quantity
            self.cash -= fill.price * fill.quantity
        else:
            self.inventory -= fill.quantity
            self.cash += fill.price * fill.quantity

    # ---- bookkeeping ----------------------------------------------------

    def mark_to_market_pnl(self, mid_price):
        """Cash plus the value of current inventory at the current mid-price."""
        return self.cash + self.inventory * mid_price

    def _record(self, t, mid_price):
        self.history.append({
            "time": t,
            "inventory": self.inventory,
            "cash": self.cash,
            "mid_price": mid_price,
            "mtm_pnl": self.mark_to_market_pnl(mid_price),
        })
