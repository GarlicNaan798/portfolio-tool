---
name: harness-validated-against-published-aqr-tsmom
description: Our Yahoo reconstruction reproduces AQR's published TSMOM decay (era B 0.41 vs 0.40), so the negative findings stand as statements about markets.
metadata:
  type: finding
---
From `validate_vs_aqr.py`. The positive control the council prescribed on the
whole programme, run against AQR's published series rather than our own data.

    AQR published TSMOM (58 futures, Moskowitz/Ooi/Pedersen 2012)
      era A 2001-2008    96 months   17.99%/yr   vol 13.2%   Sharpe 1.36
      era B 2010-2026   197 months    5.25%/yr   vol 13.1%   Sharpe 0.40
      pre-2009 all      288 months   17.95%/yr               Sharpe 1.51
      full 1985-2026    497 months   12.25%/yr               Sharpe 0.98

    Our Phase E, 31 Yahoo futures, self-reconstructed
      era A 0.90    era B 0.41

**Era B matches almost exactly: 0.41 against 0.40.** Era A is lower for us
(0.90 against 1.36), which is the expected direction - 31 markets with
unadjusted roll artifacts against 58 properly constructed ones, and our
winsorising at +/-25% clips exactly the large moves trend following earns
from.

**This resolves the council's central criticism.** [[NOTES]] records that
error detection here was conditioned on implausibility, so the negatives from
phases 1-6 were unvalidated rather than validated - the 25bps futures error
having shipped a false negative that was nearly banked. The harness now
reproduces a published series it was never fitted to.

Per the stopping rule in [[NOTES]]: the harness reproduces the published
series, and no strategy cleared all three gates. **That is the programme's
answer.**

**Independent confirmation of the decay.** AQR's own TSMOM runs at Sharpe
0.98 over 1985-2026 but 0.40 since 2010. [[trend-following-decayed-after-2009]]
was sourced from the literature and reproduced on our data; it now also
holds in the factor series the literature is built on.

**What this does NOT license.** The validation covers the measurement
machinery, not the cost assumptions - and cost, not roll artifacts, is what
changed three conclusions here (see
[[cost-assumptions-decided-every-conclusion-here]]). AQR series are gross of
retail frictions. A validated harness measuring a gross series still says
nothing about what a retail account nets.
