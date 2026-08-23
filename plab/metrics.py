"""Performance statistics, with honest error bars.

Replaces four copies of sharpe()/stats() that had drifted across files.
"""

import numpy as np
import pandas as pd

BPY = 252


def sharpe(returns, bpy=BPY):
    r = pd.Series(returns).dropna()
    return float(r.mean() / r.std() * np.sqrt(bpy)) if len(r) > 5 and r.std() > 0 else 0.0


def sharpe_se(sr, years):
    """Lo (2002): the standard error of an annualised Sharpe over T years.

    Carried everywhere because a Sharpe without its error bar has repeatedly
    been mistaken for a result in this project.
    """
    return float(np.sqrt((1 + sr ** 2 / 2) / max(years, 0.1)))


def max_drawdown(equity):
    eq = pd.Series(equity).dropna()
    return float((eq / eq.cummax() - 1).min()) if len(eq) else 0.0


def cagr(equity, bpy=BPY):
    eq = pd.Series(equity).dropna()
    if len(eq) < 2 or eq.iloc[0] <= 0:
        return 0.0
    return float((eq.iloc[-1] / eq.iloc[0]) ** (bpy / len(eq)) - 1)


def summary(returns, bpy=BPY):
    """One dict of everything, so callers stop recomputing it differently."""
    r = pd.Series(returns).dropna()
    if len(r) < 5:
        return dict(cagr=0.0, maxdd=0.0, sharpe=0.0, se=0.0, t=0.0,
                    years=0.0, vol=0.0)
    eq = (1 + r).cumprod()
    years = len(r) / bpy
    sr = sharpe(r, bpy)
    se = sharpe_se(sr, years)
    return dict(cagr=cagr(eq, bpy), maxdd=max_drawdown(eq), sharpe=sr,
                se=se, t=sr / se if se else 0.0, years=years,
                vol=float(r.std() * np.sqrt(bpy)))


def fmt(name, s, width=22):
    return (f"{name:<{width}s} CAGR {s['cagr']:>7.2%}  vol {s['vol']:>6.1%}  "
            f"maxDD {s['maxdd']:>7.1%}  SR {s['sharpe']:>5.2f} "
            f"+/-{s['se']:.2f}  t {s['t']:>5.2f}")


def block_bootstrap_sharpe(returns, n=2000, block=20, seed=0, bpy=BPY):
    """Resample in blocks to preserve short-term structure.

    Returns (actual, 2.5th pct, 97.5th pct, fraction <= 0).
    """
    r = pd.Series(returns).dropna().values
    if len(r) < block * 5:
        return 0.0, 0.0, 0.0, 1.0
    actual = r.mean() / r.std() * np.sqrt(bpy) if r.std() else 0.0
    rng = np.random.default_rng(seed)
    nb = len(r) // block
    out = np.empty(n)
    for i in range(n):
        starts = rng.integers(0, len(r) - block, nb)
        s = np.concatenate([r[j:j + block] for j in starts])
        out[i] = s.mean() / s.std() * np.sqrt(bpy) if s.std() else 0.0
    lo, hi = np.percentile(out, [2.5, 97.5])
    return float(actual), float(lo), float(hi), float((out <= 0).mean())


def alpha_beta(returns, bench_returns, bpy=BPY):
    """Regress the strategy on a benchmark: r = alpha + beta * r_bench.

    Alpha is the intercept - the part of the return NOT explained by simply
    carrying market exposure. Subtracting two CAGRs is not alpha: a portfolio
    with beta 1.3 SHOULD out-return the market in a rising one, and that
    excess is leverage, not skill.

    Returns annualised alpha, its t-stat, beta, and R-squared. No statsmodels
    dependency - it is a two-parameter OLS.
    """
    df = pd.concat([pd.Series(returns), pd.Series(bench_returns)],
                   axis=1).dropna()
    if len(df) < 30:
        return dict(alpha=0.0, t=0.0, beta=0.0, r2=0.0, n=len(df))
    y = df.iloc[:, 0].values
    x = df.iloc[:, 1].values
    n = len(y)

    vx = x.var(ddof=1)
    beta = float(np.cov(x, y, ddof=1)[0, 1] / vx) if vx > 0 else 0.0
    a = float(y.mean() - beta * x.mean())

    resid = y - (a + beta * x)
    s = resid.std(ddof=2)
    se_a = s * np.sqrt(1.0 / n + x.mean() ** 2 / ((n - 1) * vx)) if vx > 0 else 0.0
    t = float(a / se_a) if se_a > 0 else 0.0

    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return dict(alpha=a * bpy, t=t, beta=beta, r2=r2, n=n)
