"""plab - portfolio lab.

Built after ~15 single-instrument strategies failed (see IDEAS.md). The
pivot: stop trading one thing, and instead score many stocks, construct a
portfolio from those scores, and rebalance it.

The reason this is not just another idea: Grinold's law says
IR ~ IC x sqrt(breadth). Every earlier attempt here used equal-weight top-N,
which converts a signal into a portfolio inefficiently. Construction is the
conversion step, and it was never optimised.

The honest limit, measured in findings/phase-c-breadth-was-not-the-constraint.md:
price-only IC on single stocks was about +0.02. Construction improves the
IC-to-IR conversion; it cannot manufacture IC. So alpha.ic_report() exists to
measure what we actually have before any of it matters.
"""

from plab import alpha, data, metrics, portfolio  # noqa: F401
