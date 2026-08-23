# Council audit: what was wrong with the reasoning

Four voices reviewed the decision chain across ten phases. This records the
criticism, not the defence. Findings live in `findings/`; dead ends in
`IDEAS.md`. This file is about **how the choices were made**.

## The single most important criticism

> "Error detection was conditioned on implausibility. Both data bugs and all
> three cost misspecifications were caught because a number looked wrong -
> never by a check that ran regardless. That filter is one-sided by
> construction: it catches errors that produce absurd results and preserves
> every error that produces a plausible one."

This is correct and it is the finding that matters most.

- The cartesian join was caught because 2.4M rows for a 116k panel is absurd.
- The 25bps-on-futures error was caught because a positive control returned
  the wrong sign.
- The hardcoded "interval contains zero" text was caught by reading it.

Every one was noticed by a human eye landing on something implausible.
**None was caught by a test that runs whether or not anyone is suspicious.**

The consequence is severe: **the negative results from phases 1-6 are not
validated, they are merely unfalsified.** The only positive control in the
project ran at phase 7 of 8. Before that, no instrument had ever been shown
capable of detecting a signal it genuinely contained. "0/480 configs beat
buy & hold" may be true. Nothing in the process establishes it.

The 25bps futures error is the proof: it produced a **false negative** that
was very nearly banked as a finding.

## Ranked reasoning errors

**1. Diagnostics ran in reverse order.**
IC measured at phase 8 of 8. Quintile analysis built at phase 9, only after
an IC-based recommendation had already failed. Positive control at phase 7.
The cheap measurements that decide whether a search is worth running were
built last, after the expensive searches had already been run and their
results filed as knowledge.

**2. The arena made failure structural, and the house rule locked it in.**
"Beat buy & hold, always" applied to 2010-2026 US large caps means beating
the best-performing liquid asset of the sample, long-only, at retail cost.
Published TSMOM's claimed value is diversification and crisis alpha - phase 7
measured exactly that (era A 0.90, era B 0.41) and it was graded pass/fail
against the wrong question. The benchmark question was never "beat buy &
hold"; it was "beat it **at what risk, in what regime**".

**3. The benchmark was wrong for seven phases, and the corrected one is
still contaminated.**
SPY was the comparison until near the end. Equal-weighting the same
survivorship-biased universe produces **+4.08%/yr alpha vs SPY at t=3.42** -
larger and far more significant than the strategy's own +5.52% at t=1.77.
**The headline result is smaller than its own known bias term.**

**4. Significance was reported on post-hoc selections.**
Instruments, signals, eras and benchmarks were repeatedly chosen after
seeing result tables, then t-statistics were quoted as if the choice had
been made in advance. t=1.77 is not t=1.77 against the search that produced
it. Phase 9 is the proof: the best-IC signal was selected on that basis and
performed **worse**.

**5. No stopping rule was ever written.**
> "Commit 3fb8738 says 'both fail the gates' - and the next commit adds more
> code. The pre-registered gate was fired and ignored. Every process
> improvement was adopted after a failure, always in the direction of
> continuing. That is not convergence, it's a ratchet."

Gates were pre-registered for individual phases. Nothing was ever written
down that would end the programme.

## The warning about the new data

All three voices flagged the same risk, unprompted.

> "AQR data fixes roll artifacts. Roll artifacts never killed anything here -
> **costs did**, three times. AQR's series are gross of the retail frictions
> that ate 90% of the spread. Reaching for the new library after failure #10
> is the same move as 22->188 stocks after failure #6: change the input, keep
> the premise."

> "100+ years x dozens of factors to search, with a selection process that has
> picked instruments after seeing tables eight times. That is an industrial
> overfitting machine wearing a published-paper badge."

And the point that resolves it, from the Pragmatist:

> "Replicate published TSMOM on AQR's own data as one final positive control.
> If the harness reproduces it, the harness is validated and the research is
> done."

**That is the correct use of the new data: validation, not search.** AQR
publishes the answer. If our harness cannot reproduce a published factor
series from its own inputs, the harness is broken and every negative in this
repo is void. If it can, the negatives stand and the programme has its answer.

## What the council agreed was worth keeping

- The walk-forward harness, **specifically the random-selection null** - the
  only component with a shelf life longer than a market regime
- `plab/metrics` - Lo standard errors, block bootstrap, alpha/beta regression
- `plab/portfolio` - construction pays whether or not there is alpha
- `IDEAS.md` - prevents the six-week re-discovery
- `explain_picks.py` - the one artefact that answered the repeated request
  for simpler explanations
- The positive control, late as it was

## What the council called wasted

- The MT5 EA: built before a five-minute check on data access
- The 480-config ETF sweep: Moskowitz published this; 0/480 was the
  predicted result
- Universe 22->188: breadth chased with no signal-quality gate
- Most of the 20 papers: "if a paper did not change a decision, it was
  reading, not research"

## Changes made in response

1. `plab/validate.py` - positive and negative controls that run **every
   time**, not when someone is suspicious. A result is not printed unless the
   controls pass.
2. A written stopping rule, below.

## Stopping rule

Written now, before the next result is seen.

The programme ends, and the conclusion is "no tradeable edge was found", if
**either**:

- the harness fails to reproduce a published AQR factor series within
  tolerance (harness broken, all findings void), **or**
- the harness reproduces it, and no strategy clears all three gates - beat
  the equal-weight benchmark, beat random config selection, and an excess
  bootstrap interval excluding zero.

"Try a different input" is not a response to either outcome.
