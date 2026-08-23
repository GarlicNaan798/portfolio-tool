"""Controls that run every time, not when someone is suspicious.

The council's sharpest criticism (NOTES.md): every bug in this project was
caught because a number looked implausible. That filter is one-sided - it
catches errors that produce absurd results and preserves every error that
produces a plausible one. A 25x cost misspecification once shipped a FALSE
NEGATIVE and was nearly banked as a finding.

The fix is not more care. It is checks that do not depend on anyone being
suspicious:

    POSITIVE  plant a known signal in synthetic data. The harness MUST find
              it. If it cannot detect a signal that is definitely there, no
              negative result it produces means anything.

    NEGATIVE  feed it pure noise. The harness MUST NOT find anything. If it
              does, every positive result is suspect.

    LOOKAHEAD shift a signal one bar into the future. Results MUST improve.
              If they do not, the pipeline is not using the signal when it
              claims to - or is already leaking.

    COSTS     raise the fee. Returns MUST fall monotonically. This is the
              specific check that would have caught the futures error.

Call run_all() before trusting any output.
"""

import numpy as np
import pandas as pd

from plab import alpha, portfolio

BPY = 252


def synthetic_panel(n_names=60, n_days=2500, signal_strength=0.0, seed=0):
    """Prices where yesterday's rank predicts today's return by construction.

    signal_strength = 0 gives pure noise. Higher values plant a stronger
    cross-sectional edge. The planted signal is deliberately simple: names
    with a lower recent return get a positive drift, so short-term reversal
    should detect it.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2005-01-03", periods=n_days, freq="B")
    cols = [f"S{i:03d}" for i in range(n_names)]

    rets = rng.normal(0.0004, 0.015, (n_days, n_names))
    if signal_strength > 0:
        # each day, tilt tomorrow's return against the last 21 days' return
        px_tmp = np.cumprod(1 + rets, axis=0)
        for t in range(25, n_days - 1):
            past = px_tmp[t] / px_tmp[t - 21] - 1.0
            tilt = -(past - past.mean())
            sd = tilt.std()
            if sd > 0:
                rets[t + 1] += signal_strength * tilt / sd * 0.015
            px_tmp[t + 1] = px_tmp[t] * (1 + rets[t + 1])

    close = pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx,
                         columns=cols)
    return close


def _ic_of(px, horizon=21):
    rep = alpha.ic_report(px, horizon=horizon)
    return float(rep.loc["reversal", "ic"]) if "reversal" in rep.index else 0.0


def positive_control(strength=1.5, min_ic=0.03):
    """A planted signal must be detected."""
    px = synthetic_panel(signal_strength=strength, seed=1)
    ic = _ic_of(px)
    ok = ic >= min_ic
    return ok, f"planted signal -> reversal IC {ic:+.4f} (need >= {min_ic})"


def negative_control(n_seeds=8, max_abs_mean=0.010):
    """Pure noise must produce no MATERIAL signal, and report the noise floor.

    An earlier version of this check demanded that roughly half of noise
    draws show a positive IC. That assumed the measurement is centred on
    zero. It is not: rank correlation over ~60 names carries a small
    intrinsic bias of about -0.004, present at every signal/forward gap, so
    most noise draws come out slightly negative. The check was wrong, not
    the pipeline.

    What matters is (a) the floor is small next to anything we would call a
    signal, and (b) it is REPORTED, so a measured IC can be read as a
    distance above the floor rather than as an absolute number. The floor
    runs slightly negative, which makes real positive ICs conservative.
    """
    ics = [_ic_of(synthetic_panel(signal_strength=0.0, seed=100 + i))
           for i in range(n_seeds)]
    mean_ic = float(np.mean(ics))
    sd = float(np.std(ics, ddof=1)) if n_seeds > 1 else 0.0
    ok = abs(mean_ic) <= max_abs_mean
    return ok, (f"pure noise      -> IC floor {mean_ic:+.4f} +/-{sd:.4f} over "
                f"{n_seeds} draws (need |floor| <= {max_abs_mean}); "
                f"read real ICs as distance above this")


def lookahead_control(strength=1.5):
    """Peeking one bar ahead MUST beat not peeking.

    If a cheating version does not outperform, the pipeline is not actually
    consuming the signal where it says it is.
    """
    px = synthetic_panel(signal_strength=strength, seed=2)
    scores = alpha.combine(alpha.build(px))

    honest, _ = portfolio.run(px, scores, top_n=10, fee_bps=0.0)
    cheat, _ = portfolio.run(px, scores.shift(-21), top_n=10, fee_bps=0.0)

    h = honest.iloc[-1] / honest.iloc[0] - 1
    c = cheat.iloc[-1] / cheat.iloc[0] - 1
    ok = c > h
    return ok, f"peeking ahead   -> {c:+.1%} vs honest {h:+.1%} (peek must win)"


def cost_monotonicity_control():
    """Raising the fee must lower the return, every time.

    This is the check that would have caught charging futures 25bps.
    """
    px = synthetic_panel(signal_strength=1.0, seed=3)
    scores = alpha.combine(alpha.build(px))
    out = []
    for bps in (0.0, 5.0, 25.0, 100.0):
        eq, _ = portfolio.run(px, scores, top_n=10, fee_bps=bps)
        out.append(eq.iloc[-1])
    ok = all(out[i] >= out[i + 1] for i in range(len(out) - 1))
    txt = " > ".join(f"{v:.2f}" for v in out)
    return ok, f"cost monotonic  -> {txt} (must be non-increasing)"


def benchmark_sanity_control():
    """An equal-weight book of ALL names must match the universe mean.

    Guards the benchmark itself - the quantity that was wrong for seven
    phases.
    """
    px = synthetic_panel(signal_strength=0.0, seed=4)
    flat = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    eq, _ = portfolio.run(px, flat, method="equal", top_n=px.shape[1],
                          rebal=21, fee_bps=0.0)
    ew = (1 + px.pct_change().fillna(0.0).mean(axis=1)).cumprod()
    ew = ew.reindex(eq.index)
    diff = abs(eq.iloc[-1] / eq.iloc[0] - ew.iloc[-1] / ew.iloc[0])
    ok = diff < 0.05
    return ok, f"benchmark sanity-> equal-weight book vs universe mean differs {diff:.3f} (need < 0.05)"


CONTROLS = [
    ("positive", positive_control),
    ("negative", negative_control),
    ("lookahead", lookahead_control),
    ("costs", cost_monotonicity_control),
    ("benchmark", benchmark_sanity_control),
]


def run_all(verbose=True, strict=True):
    """Run every control. Returns True only if all pass.

    strict=True is the default on purpose: a result printed after a failed
    control is worse than no result, because it looks the same as a good one.
    """
    if verbose:
        print("=" * 74)
        print("HARNESS CONTROLS - these run every time, not on suspicion")
        print("=" * 74)
    results = []
    for name, fn in CONTROLS:
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"raised {type(e).__name__}: {e}"
        results.append(ok)
        if verbose:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name:10s} {msg}")

    passed = all(results)
    if verbose:
        print(f"\n{sum(results)}/{len(results)} controls passed")
        if not passed:
            print("\nA control failed. Any result produced now is unreliable -")
            print("this is exactly the situation where a 25x cost error once")
            print("shipped a false negative. See NOTES.md.")
    if strict and not passed:
        raise SystemExit("harness controls failed - refusing to report results")
    return passed


if __name__ == "__main__":
    run_all()
