---
name: ic-measurement-has-a-negative-noise-floor
description: Rank IC over ~60 names carries an intrinsic bias of about -0.004 on pure noise, independent of any signal/forward gap.
metadata:
  type: finding
---
From `plab/validate.py`, discovered the first time the negative control was
strengthened from one noise draw to eight.

    reversal IC on PURE NOISE, by signal/forward gap
      gap=0   -0.0043    30% positive
      gap=1   -0.0015    50%
      gap=2   -0.0039    40%
      gap=5   -0.0034    30%

**The floor is about -0.004 and does not depend on the gap.** The obvious
hypothesis - that the signal window and forward window sharing the price at
date t creates spurious correlation - is WRONG. Inserting a gap does not
remove it. It is an intrinsic small-sample bias in rank correlation over
roughly 60 names.

**Two consequences:**

1. **Our reversal result is conservative, not inflated.** Measured IC on real
   data was +0.0315. Against a floor of -0.0048 that is +0.036 of real
   distance, so [[ic-does-not-predict-long-only-portfolio-value]] understates
   rather than overstates the signal.

2. **A check can be miscalibrated and look rigorous.** The first strengthened
   version demanded that ~half of noise draws be positive, which assumes a
   zero-centred floor. It failed - correctly flagging something real - but
   the something was the check's own assumption, not a pipeline defect.

**Method note.** Report ICs as a distance above the measured floor rather
than as absolute numbers, and re-measure the floor whenever the universe
size changes, since the bias is a function of how many names are ranked.

Found only because controls were made to run unconditionally, per
[[NOTES]] - the council's point that error detection conditioned on
implausibility is one-sided by construction.
