# Plan: does any published anomaly survive contact with a retail account?

Steps 1 and 2 are done and their results are below. Steps 3-6 are
pre-registered — criteria, thresholds and the action under every outcome are
fixed here **before** the data is looked at, because the previous project's
central failure was measuring after deciding what counted as success.

## Why this line of attack

Two replication studies reach opposite verdicts on the same literature:

- **Chen & Zimmermann**: ~98% of published anomalies replicate, following
  each original paper's own methodology.
- **Hou, Xue & Zhang (2020)**: 82% of 452 anomalies **fail** at t > 2.78,
  once microcaps are removed and returns are value-weighted.

Both are right. The disagreement is entirely about *where* the anomaly lives.
HXZ put it plainly: *"because of high costs in trading these stocks,
anomalies in microcaps are more apparent than real."*

That is the question this project has actually been asking all along, without
knowing it.

## DONE — Step 1: pull the data

`openassetpricing` gives 212 anomalies with monthly long-short portfolio
returns, 1926-2024, plus metadata for 331 signals (authors, year, data type,
rebalance period, original sample window). Cached under `data/cz/`.

No reconstruction. The previous project rebuilt TSMOM and value by hand and
got both partly wrong, catching the errors only by luck.

## DONE — Step 2: split by construction

    portfolio set                    t>1.96   t>2.78   median |t|   median ann
    original (as published)            79%      67%       3.44        +5.2%
    value-weighted                     48%      31%       1.81        +3.4%
    microcaps excluded (NYSE p20)      67%      50%       2.74        +3.6%
    price > $5                         75%      59%       3.16        +4.0%

**Value-weighting alone halves survival** (67% -> 31%) and pushes the median
anomaly to |t| = 1.81, below significance. Microcap exclusion costs a further
chunk. Combining both, as HXZ do, lands near their reported 18% survival.

**This independently validates the previous project's negative results.** It
tested large caps; that is where the literature says anomalies die. A measured
edge of 0.28% at t = 1.53 is what a large-cap anomaly is *supposed* to look
like.

Note also: the median annual return is +3.4% value-weighted, and that is
**gross**.

---

## Step 3 — which anomalies can we even compute?

`Cat.Data` in the metadata separates signals needing accounting data,
13F filings, or analyst forecasts from those computable from **price and
volume alone**. Only the last group is reachable with Alpaca.

**Pre-registered question:** do price-only anomalies survive value-weighting
at a materially different rate than accounting-based ones?

**Thresholds, fixed now:**
- If price-only survival at t > 2.78 under value-weighting is **below 20%**,
  the price-only avenue is closed. Record it and stop pursuing price signals.
- If **above 40%**, price-only anomalies are the live subset and step 4
  proceeds on them alone.
- Between 20-40%: proceed, but treat every subsequent result as provisional.

## Step 4 — post-publication decay

McLean & Pontiff found anomaly returns fall ~26% out-of-sample and ~58%
post-publication. The metadata carries `SampleEndYear` and publication `Year`,
so each anomaly can be split into three eras without any judgement calls:

    in-sample        up to SampleEndYear
    out-of-sample    SampleEndYear -> publication Year
    post-publication after publication Year

**Pre-registered expectation:** monotone decline across the three eras.

**Action:** whatever survives step 3 is re-ranked on **post-publication
returns only**. An anomaly that worked before its paper and not after is not a
candidate, however good its full-sample t-stat.

## Step 5 — cost breakeven, before any strategy is built

For each surviving anomaly compute the round-trip cost that reduces its
post-publication return to zero, given its rebalance period.

Then compare against realistic retail costs by liquidity tier:

    large cap       ~1-5 bps      spread plus commission
    mid cap         ~10-25 bps
    microcap        ~100-300 bps  where the anomalies actually live

**Pre-registered rule:** an anomaly is a candidate only if its breakeven cost
exceeds **3x** the realistic cost of its tier. Not 1x — cost estimates in this
project have been wrong three times, always optimistically, and a 3x margin is
the minimum that survives being wrong again.

## Step 6 — the retail question, only if anything reaches it

HXZ dismiss microcap anomalies as untradeable **at institutional size**. A
retail account is small enough that capacity is not the binding constraint;
spread is. Whether that changes the answer is genuinely open.

Only run this if step 5 produces candidates. If it does not, the honest
conclusion is that published cross-sectional anomalies are not accessible to a
retail account, and that is a complete answer to the question this project
started with.

## Stopping rule

The programme ends, with the conclusion "no retail-accessible edge in
published cross-sectional anomalies", if **either**:

- step 3 closes the price-only avenue and no fundamental data is bought, **or**
- step 5 produces no anomaly with a 3x cost margin.

Substituting a different universe, weighting scheme or signal family and
re-running is **not** a response to either outcome.

## Standing rules carried forward

- Benchmark is what you would otherwise hold, never SPY by default.
- State the cost assumption before the result, and check it against the
  instrument being traded.
- Report the census, never select on the holdout.
- A result that has not survived a positive control is not a result.
