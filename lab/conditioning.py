"""Does aggregate stress predict when factors pay?

Runs the test pre-registered in PLAN.md. Nothing here was chosen after
looking at a result: the hypothesis sign, the t-threshold, the split date
and the action under each outcome were all written down first.

Newey-West standard errors are implemented directly rather than pulled from
statsmodels - the regressor is persistent, OLS errors would be badly
understated, and the correction is twenty lines.
"""

import numpy as np
import pandas as pd

from lab import data

SPLIT = "2015-01-01"          # fixed in PLAN.md before any data was pulled
T_THRESHOLD = 2.5             # raised above 2.0 for Stambaugh bias
FEE_BPS = 5.0
NW_LAGS = 12


# ------------------------------------------------------------------ plumbing
def monthly_excess(prices):
    """Month-end factor returns in excess of T-bills."""
    px = pd.DataFrame(prices).ffill()
    m = px.resample("ME").last()
    r = m.pct_change()
    cash = r[data.CASH] if data.CASH in r else 0.0
    out = r.drop(columns=[data.CASH], errors="ignore").sub(cash, axis=0)
    return out.dropna(how="all")


def monthly_state(state):
    """State observable at month end - no revision, no look-ahead.

    Each series is standardised on an EXPANDING window so the z-score at
    time t uses only data up to t. Full-sample standardisation would leak
    the future into the level, which is the subtler half of the mistake
    Baker-Wurgler makes.
    """
    s = state.ffill().resample("ME").last()
    z = pd.DataFrame(index=s.index)
    for c in s.columns:
        mu = s[c].expanding(min_periods=36).mean()
        sd = s[c].expanding(min_periods=36).std()
        z[c] = (s[c] - mu) / sd
    return z.dropna(how="all")


def newey_west_t(y, x, lags=NW_LAGS):
    """OLS slope with HAC standard errors. Returns (beta, t, n)."""
    df = pd.concat([y, x], axis=1).dropna()
    if len(df) < 30:
        return np.nan, np.nan, len(df)
    yy = df.iloc[:, 0].values
    X = np.column_stack([np.ones(len(df)), df.iloc[:, 1].values])
    n = len(yy)

    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ X.T @ yy
    resid = yy - X @ beta

    # HAC meat: Gamma_0 plus Bartlett-weighted autocovariances
    S = (X * resid[:, None]).T @ (X * resid[:, None])
    for l in range(1, min(lags, n - 1) + 1):
        w = 1.0 - l / (lags + 1.0)
        A = (X[l:] * resid[l:, None]).T @ (X[:-l] * resid[:-l, None])
        S += w * (A + A.T)

    var = xtx_inv @ S @ xtx_inv
    se = np.sqrt(max(var[1, 1], 0.0))
    return float(beta[1]), (float(beta[1] / se) if se > 0 else np.nan), n


# ------------------------------------------------------------------- the test
def regressions(rets, z, state_col, label):
    """Next month's excess return on today's state. Sign is the hypothesis."""
    print(f"\n{label}  (state = {state_col}, standardised on expanding window)")
    print(f"{'factor':>8s} {'beta':>9s} {'NW t':>7s} {'n':>5s}  hypothesis: "
          f"beta > 0 (stress now -> higher return next month)")
    signs = []
    for f in rets.columns:
        fwd = rets[f].shift(-1)
        b, t, n = newey_west_t(fwd, z[state_col], NW_LAGS)
        if np.isnan(b):
            continue
        signs.append(b > 0)
        print(f"{f:>8s} {b:>+9.4f} {t:>7.2f} {n:>5d}")
    return signs


def pooled(rets, z, state_col):
    """Stack all factors into one regression - the pre-registered t test."""
    ys, xs = [], []
    for f in rets.columns:
        fwd = rets[f].shift(-1)
        d = pd.concat([fwd, z[state_col]], axis=1).dropna()
        ys.append(d.iloc[:, 0])
        xs.append(d.iloc[:, 1])
    if not ys:
        return np.nan, np.nan, 0
    return newey_west_t(pd.concat(ys, ignore_index=True),
                        pd.concat(xs, ignore_index=True), NW_LAGS)


def conditional_strategy(rets, z, state_col, fee_bps=FEE_BPS):
    """Size up in high stress, down in low. Compare to holding constantly.

    Weight is 1 + z clipped to [0, 2], so average exposure is ~1 and the
    comparison is not simply 'more leverage beats less'.
    """
    fee = fee_bps / 10_000.0
    w = (1.0 + z[state_col]).clip(0.0, 2.0).shift(1)
    out = {}
    for f in rets.columns:
        r = rets[f]
        d = pd.concat([r, w], axis=1).dropna()
        if len(d) < 24:
            continue
        rr, ww = d.iloc[:, 0], d.iloc[:, 1]
        cond = rr * ww - ww.diff().abs().fillna(0.0) * fee
        const = rr
        out[f] = (sharpe(cond), sharpe(const),
                  cond.mean() * 12, const.mean() * 12)
    return out


def sharpe(r, ppy=12):
    r = pd.Series(r).dropna()
    return float(r.mean() / r.std() * np.sqrt(ppy)) if len(r) > 6 and r.std() else 0.0


def main():
    print("Loading (all cached, all real-time series):")
    prices, state = data.load_all()
    rets = monthly_excess(prices)
    z = monthly_state(state)

    common = rets.index.intersection(z.index)
    rets, z = rets.loc[common], z.loc[common]
    factors = [c for c in rets.columns if c in data.FACTOR_ETFS]
    rets = rets[factors]

    print(f"\n{len(rets)} months, {rets.index[0]:%Y-%m} to {rets.index[-1]:%Y-%m}")
    print(f"factors: {factors}")
    print(f"OOS split fixed at {SPLIT} (PLAN.md, before any data was seen)")

    ins = rets[rets.index < SPLIT]
    oos = rets[rets.index >= SPLIT]
    z_in = z[z.index < SPLIT]
    z_oos = z[z.index >= SPLIT]
    print(f"in-sample {len(ins)} months, out-of-sample {len(oos)} months")

    for col in ("vix", "credit_spread"):
        if col not in z.columns:
            continue
        print("\n" + "=" * 72)
        print(f"STATE VARIABLE: {col}")
        print("=" * 72)
        regressions(ins, z_in, col, "IN SAMPLE - not evidence")
        signs = regressions(oos, z_oos, col, "OUT OF SAMPLE - this is the test")

        b, t, n = pooled(oos, z_oos, col)
        n_right = sum(signs)
        print(f"\npooled OOS: beta {b:+.4f}, NW t = {t:.2f}, n = {n}")
        print(f"sign matches hypothesis on {n_right}/{len(signs)} factors")

        res = conditional_strategy(oos, z_oos, col)
        print(f"\n{'factor':>8s} {'cond SR':>9s} {'const SR':>9s} "
              f"{'cond ret':>9s} {'const ret':>10s}  better?")
        n_better = 0
        for f, (cs, ks, cr, kr) in res.items():
            better = cs > ks
            n_better += better
            print(f"{f:>8s} {cs:>9.2f} {ks:>9.2f} {cr:>+9.2%} {kr:>+10.2%}"
                  f"  {'yes' if better else 'no'}")

        g1 = n_right >= 3
        g2 = (not np.isnan(t)) and t > T_THRESHOLD
        g3 = n_better >= 3
        print("\n" + "-" * 72)
        print(f"  [{'x' if g1 else ' '}] sign matches on >= 3 of 4 factors "
              f"({n_right}/{len(signs)})")
        print(f"  [{'x' if g2 else ' '}] pooled NW t > {T_THRESHOLD} "
              f"({t:.2f})")
        print(f"  [{'x' if g3 else ' '}] conditional beats constant after "
              f"{FEE_BPS}bps on >= 3 of 4 ({n_better}/{len(res)})")
        print("\n  " + ("CONFIRMED for this state variable"
                        if (g1 and g2 and g3) else
                        "REJECTED for this state variable"))

    print("\n" + "=" * 72)
    print("Per PLAN.md: rejection means the conditioning thesis is dead for")
    print("retail-accessible data. Do NOT substitute another state variable")
    print("and re-run - that is 'change the input, keep the premise'.")


if __name__ == "__main__":
    main()
