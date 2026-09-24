"""
simulator.py

Order flow simulation: generates synthetic "noise trader" activity
(limit orders, market orders, cancellations) using Poisson arrivals,
and feeds it through the MatchingEngine. This stands in for the rest
of the market that a market-making strategy (strategy.py) will later
quote against.
"""

import random


class OrderFlowSimulator:
    """
    Uses the SUPERPOSITION property of Poisson processes: the sum of
    independent Poisson processes (rate lambda_1, ..., lambda_n) is
    itself Poisson with rate sum(lambda_i), and conditional on an
    event firing, its type is chosen randomly with probability
    proportional to each lambda_i. So we run ONE combined clock
    instead of five separate ones per event type.
    """

    def __init__(
        self,
        engine,
        initial_mid_price,
        tick_size=0.01,
        rate_limit=3.0,      # combined limit buy+sell arrival rate (orders/sec)
        rate_market=1.0,     # combined market buy+sell arrival rate (orders/sec)
        rate_cancel=1.5,     # cancellation arrival rate (orders/sec)
        limit_order_size_range=(10, 100),
        market_order_size_range=(5, 50),
        price_offset_mean_ticks=5,   # avg distance of limit orders from mid
        seed=None,
    ):
        self.engine = engine
        self.book = engine.book

        self.mid_price_estimate = initial_mid_price  # fallback while book is thin
        self.tick_size = tick_size

        self.rate_limit = rate_limit
        self.rate_market = rate_market
        self.rate_cancel = rate_cancel
        self.total_rate = rate_limit + rate_market + rate_cancel

        self.limit_order_size_range = limit_order_size_range
        self.market_order_size_range = market_order_size_range
        self.price_offset_mean_ticks = price_offset_mean_ticks

        self.rng = random.Random(seed)
        self.time = 0.0
        self.history = []  # (time, mid_price_or_None) after each event

    # ---- public API ---------------------------------------------------

    def step(self):
        """Advance by exactly one combined-process event."""
        dt = self.rng.expovariate(self.total_rate)
        self.time += dt

        event_type = self._choose_event_type()
        self._execute(event_type)

        self._update_mid_price_estimate()
        self.history.append((self.time, self.book.mid_price()))

    def run(self, duration):
        """Run until self.time >= duration."""
        while self.time < duration:
            self.step()

    # ---- internals ------------------------------------------------------

    def _choose_event_type(self):
        r = self.rng.uniform(0, self.total_rate)
        if r < self.rate_limit:
            return "limit_buy" if self.rng.random() < 0.5 else "limit_sell"
        elif r < self.rate_limit + self.rate_market:
            return "market_buy" if self.rng.random() < 0.5 else "market_sell"
        else:
            return "cancel"

    def _execute(self, event_type):
        if event_type == "limit_buy":
            self._submit_limit("buy")
        elif event_type == "limit_sell":
            self._submit_limit("sell")
        elif event_type == "market_buy":
            self._submit_market("buy")
        elif event_type == "market_sell":
            self._submit_market("sell")
        elif event_type == "cancel":
            self._submit_cancel()

    def _submit_limit(self, side):
        # Noise-trader limit orders land a random distance from the
        # current mid-price estimate. Exponential offset -> most orders
        # land close to mid, occasional ones land far out (fat queue tail).
        ref_price = self.mid_price_estimate
        offset_ticks = self.rng.expovariate(1.0 / self.price_offset_mean_ticks)
        offset = offset_ticks * self.tick_size

        raw_price = (ref_price - offset) if side == "buy" else (ref_price + offset)
        price = round(raw_price / self.tick_size) * self.tick_size

        qty = self.rng.randint(*self.limit_order_size_range)
        self.engine.process_limit_order(side, price, qty, timestamp=self.time)

    def _submit_market(self, side):
        qty = self.rng.randint(*self.market_order_size_range)
        self.engine.process_market_order(side, qty)

    def _submit_cancel(self):
        # Pick a uniformly random resting order and cancel it.
        side = "buy" if self.rng.random() < 0.5 else "sell"
        book_side = self.book.bids if side == "buy" else self.book.asks
        if not book_side:
            return  # nothing resting on this side right now
        price = self.rng.choice(list(book_side.keys()))
        queue = book_side[price]
        if not queue:
            return
        order = self.rng.choice(list(queue))
        self.engine.cancel_order(side, price, order.order_id)

    def _update_mid_price_estimate(self):
        mid = self.book.mid_price()
        if mid is not None:
            self.mid_price_estimate = mid
