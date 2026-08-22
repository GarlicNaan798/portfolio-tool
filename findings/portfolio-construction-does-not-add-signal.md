---
name: portfolio-construction-does-not-add-signal
description: A 141-stock portfolio system beats SPY by 0.26 Sharpe, but almost all of that is survivorship; excess over the equal-weight universe is not distinguishable from chance.
metadata:
  type: finding
---
From `run_portfolio.py`, 141 US large caps, 2000-2026, strict walk-forward
(8y train / 2y test / 30d embargo, 9 configs per fold, 9 folds), 5bps/side.

**Step 1, signal quality - the number that governs everything else:**

    signal      mean IC        t    hit
    mom_12_1     0.0147     1.10    55%
    reversal     0.0315     2.83    53%    <- the only one that works
    low_vol     -0.0288    -1.87    45%    <- wrong sign
    trend       -0.0076    -0.58    52%
    COMBINED     0.0065     0.52    54%    <- worse than reversal alone

Equal-weighting the four signals **destroys** the one that works. Reversal
alone reaches t = 2.83; the blend collapses to t = 0.52 because low_vol and
trend carry the opposite sign and cancel it.

**Step 3, walk-forward:**

    walk-forward OOS   CAGR 18.84%  SR 0.91 +/- 0.28
    random config      CAGR 15.31%  SR 0.80
    equal-weight univ  CAGR 15.94%  SR 0.83
    SPY                CAGR 11.64%  SR 0.65

Against SPY this looks like +0.26 Sharpe. **Almost all of it is
survivorship** - equal-weighting the same universe beats SPY by +0.18
without any signal at all, because the universe is today's large caps and
the companies that failed are absent.

The signal's actual contribution is **+0.08 Sharpe over the equal-weight
universe**, against a standard error of 0.28.

    excess over equal-weight universe
      mean          +2.72% a year
      bootstrap CI  -0.21 to +0.62   (18.2% of resamples <= 0)

**Not distinguishable from chance.**

**A gate bug worth recording.** The first version bootstrapped the
portfolio's own Sharpe and reported PASS. That tests SR > 0, which any
long-equity book clears on beta alone in a bull market. Testing the EXCESS
over the benchmark flipped the verdict. Same class of error as the two
data bugs in [[cost-assumptions-decided-every-conclusion-here]] - it
flattered the result.

**What this does and does not close.** Construction methods barely
separated (equal, inv_vol and mean_var landed within 0.01 Sharpe of each
other), which is consistent with construction being a conversion step, not
a source of alpha. The blend destroying its best component is the more
actionable finding: signal weighting matters more than portfolio weighting,
and equal-weighting signals is not a safe default when they disagree in sign.
