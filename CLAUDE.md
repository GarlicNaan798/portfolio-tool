# portfoliotool

Swing-strategy research. Paper-derived rules, backtested in Python against
buy & hold. Read this before proposing or running anything.

## Run

```bash
uv run --with yfinance --with pandas --with numpy python swing_lab.py
uv run --with yfinance --with pandas --with numpy python swing_lab.py --interval 4h
uv run --with pandas --with numpy python strategy_search.py
```

`swing_lab.py` is the live tool: sweeps 4 variants x parameters x ~20
instruments, all **time-series** momentum (each instrument judged against its
own past; "no signal" means cash). `cross_sectional.py` is the other arm —
rank the universe, hold the leaders, rotate, so capital stays deployed.
`strategy_search.py` is the single-instrument (VOO) ancestor and
`backtest_voo.py` the one-config version it grew from; both are superseded.

## Where the parameters live

**In the code, not in this file.** Duplicating them here creates a second
source of truth that silently goes stale.

| what | where |
|---|---|
| the config grid (variants, J, ATR stop, RSI, bar cap) | `grid()`, swing_lab.py:186 |
| instrument universes | `UNIVERSE_1D` / `UNIVERSE_4H`, swing_lab.py:31 |
| fee, starting equity | module constants, swing_lab.py:26 |
| OOS split dates | `main()`, swing_lab.py:217 |
| indicator definitions | `add_indicators()`, swing_lab.py:95 |

Read them before quoting a number back to the user.

## Rules that are not visible in the code

These are decisions, not defaults. Do not quietly revise them.

- **Buy & hold is the benchmark, always.** "Profitable" is not the bar. A
  strategy that returns 8% while B&H returned 11% is a losing strategy.
- **Parameters come from the source papers** (Moskowitz et al. 2012 TSMOM;
  Bird/Gao/Yeung; Sarainmaa 2024 §5.1) — J = 3/6/9/12 months, RSI(14), SMA
  50/200. Do not open-ended numeric-search new values. That is how this
  becomes an overfitting machine.
- **Rank by instruments beaten, not by best single result.** One instrument
  winning is noise. The same rule winning across uncorrelated markets is
  signal.
- **Never select on the out-of-sample tail.** Picking the best OOS performer
  is overfitting to the holdout instead of the training set. Report the OOS
  census; tune only in-sample.
- **US-listed ETFs are 1d only.** A 6.5h session does not divide into 4h bars
  (measured 1.99 bars/day), so H4 on them is an artifact. 4h is for the 24h
  instruments only.
- **No lookahead.** Signals read bar t, fills happen at bar t+1 open. Any new
  rule preserves this.

## The knowledge base

Everything that is not code lives in two folders, both committed, both plain
markdown. They travel with `git clone` — nothing important lives in a tool's
private directory. `memory/` is the real folder; `.claude/.../memory` is a
junction pointing *into* it, so writing a memory writes into the repo.

| folder | holds | lifecycle |
|---|---|---|
| `notes/` | what a run **did** — results, dated, machine-written by `--md` | append-only, never edited after the fact |
| `memory/` | what it **meant** — decisions, findings, constraints, preferences | living; corrected or deleted when wrong |

`MEMORY.md` is the index and the entry point. Every memory gets one line
there. It is the first thing read in a new session, so it is the hinge the
whole base turns on — if a fact is not reachable from it, it is lost.

### Filing rules

Applied without being asked. This is a filing system, not a judgment call
each time.

1. **One fact per file.** A note that needs "and" in its summary is two notes.
2. **Frontmatter is mandatory**, and `type` is what makes the base queryable:
   `run` (in `notes/`), `finding`, `project`, `feedback`, `user`, `reference`.
3. **Every note links.** A finding links to the `notes/` run that produced it;
   a run links to the findings drawn from it. Use `[[wikilinks]]` — an
   orphan note is a note that will never be found again.
4. **A `[[link]]` to a note that does not exist yet is correct**, not an
   error. It marks the gap.
5. **Name files as the claim**, not the topic: `tsmom-fails-on-equity-etfs`,
   not `tsmom-results`. The filename should survive being read alone.
6. **Kill results are filed like any other finding.** "X does not beat B&H
   out-of-sample" is worth more than a sweep that re-discovers it in six
   weeks.
7. **Parameters are never copied here.** They live in the code; the base
   points at them. A copy is a second source of truth that goes stale.

### Before starting work

Read `MEMORY.md`, then `notes/` if the task resembles earlier research. The
answer may already be there, and re-running a sweep to re-learn something
already filed is the specific failure this base exists to prevent.

### After finishing work

Write the conclusion down before reporting it. A run in `notes/` records what
happened; the judgment is the expensive part to reconstruct and the part that
vanishes when context does.
