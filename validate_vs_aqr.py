"""Positive control on the whole programme.

Phase E measured trend following on 31 Yahoo futures and found Sharpe 0.90
in 2001-2008 falling to 0.41 in 2010-2026. AQR publishes the actual TSMOM
factor across 58 futures. If our reconstruction tracked the real thing, the
two should tell the same story. If they do not, the harness is broken and
every negative in findings/ is void - see NOTES.md stopping rule.
"""
import numpy as np, pandas as pd
from plab import factors

MPY = 12
def sharpe(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(MPY)) if len(x) > 6 and x.std() else 0.0
def se(sr, yrs):
    return float(np.sqrt((1 + sr**2/2) / max(yrs, .1)))

ts = factors.fetch("tsmom")
col = "TSMOM"
ERAS = {"A 2001-2008": ("2001-01-01", "2008-12-31"),
        "B 2010-2026": ("2010-01-01", "2026-12-31"),
        "pre-2009 all": ("1985-01-01", "2008-12-31"),
        "full 1985-2026": ("1985-01-01", "2026-12-31")}

print("AQR published TSMOM (58 futures, Moskowitz/Ooi/Pedersen 2012)\n")
print(f"{'era':>16s} {'n months':>9s} {'ann ret':>9s} {'ann vol':>9s} {'Sharpe':>8s} {'+/-':>6s}")
res = {}
for label, (lo, hi) in ERAS.items():
    s = ts[col].loc[lo:hi].dropna()
    if len(s) < 12: continue
    sr = sharpe(s); yrs = len(s)/MPY
    res[label] = sr
    print(f"{label:>16s} {len(s):>9d} {s.mean()*MPY:>8.2%} {s.std()*np.sqrt(MPY):>8.2%} "
          f"{sr:>8.2f} {se(sr, yrs):>6.2f}")

print("\nOUR PHASE E, 31 Yahoo futures, self-reconstructed:")
print(f"{'A 2001-2008':>16s} {'':>9s} {'':>9s} {'':>9s} {0.90:>8.2f}")
print(f"{'B 2010-2026':>16s} {'':>9s} {'':>9s} {'':>9s} {0.41:>8.2f}")

a, b = res.get("A 2001-2008", 0), res.get("B 2010-2026", 0)
print(f"\n{'='*66}\nVERDICT\n{'='*66}")
print(f"AQR  era A {a:.2f} -> era B {b:.2f}   (decay {a-b:+.2f})")
print(f"Ours era A 0.90 -> era B 0.41   (decay {0.90-0.41:+.2f})")
same_dir = (a > b) == (0.90 > 0.41)
close = abs((a - b) - (0.90 - 0.41)) < 0.5
print(f"\nsame direction of decay : {same_dir}")
print(f"decay magnitude within 0.5: {close}")
if same_dir and close:
    print("\nHARNESS VALIDATED. Our reconstruction reproduced the published")
    print("series' behaviour. The negative findings in findings/ stand as")
    print("statements about markets, not artifacts of broken tooling.")
elif same_dir:
    print("\nPARTIAL. Direction matches, magnitude does not. Treat magnitudes")
    print("in findings/ as unreliable; directions as probably sound.")
else:
    print("\nHARNESS NOT VALIDATED. Per the stopping rule in NOTES.md, every")
    print("negative in findings/ must be treated as void.")
