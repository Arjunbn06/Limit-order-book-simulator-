"""
backtest.py

Wires the pieces together: an OrderFlowSimulator generates noise-trader
flow, and an AvellanedaStoikovStrategy periodically re-quotes into the
same book, receiving fills whenever noise flow crosses its quotes.
"""

from lob_sim.orderbook import OrderBook
from lob_sim.matching_engine import MatchingEngine
from lob_sim.simulator import OrderFlowSimulator
from lob_sim.strategy import AvellanedaStoikovStrategy


def run_backtest(
    duration=1.0,
    requote_interval=0.01,
    initial_mid_price=100.0,
    tick_size=0.01,
    strategy_kwargs=None,
    simulator_kwargs=None,
    seed=None,
):
    book = OrderBook()
    engine = MatchingEngine(book)
    # strategy.T is the model's own normalized session length (default
    # 1.0) -- independent of `duration`, which is real simulated seconds.
    strategy = AvellanedaStoikovStrategy(
        engine, tick_size=tick_size, **(strategy_kwargs or {})
    )

    sim = OrderFlowSimulator(
        engine,
        initial_mid_price=initial_mid_price,
        tick_size=tick_size,
        seed=seed,
        on_fill=strategy.on_fill,
        **(simulator_kwargs or {}),
    )

    # Avellaneda-Stoikov's (T - t) term represents "fraction of the
    # session remaining" and is meant to live on an O(1) scale (T=1.0
    # by default). The simulation itself runs on real seconds, which
    # can be any duration -- so we normalize wall-clock time into
    # [0, T] before handing it to the strategy. Skipping this step
    # means (T - t) can be huge (e.g. 198 "seconds remaining"), which
    # blows up the inventory-skew term into nonsense reservation prices.
    t = 0.0
    while t < duration:
        t = min(t + requote_interval, duration)
        sim.run(t)   # advance noise flow up to real time t
        mid = book.mid_price() or sim.mid_price_estimate
        normalized_t = (t / duration) * strategy.T
        strategy.requote(mid, normalized_t)

    return book, engine, sim, strategy
