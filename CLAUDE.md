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

## Persisting what runs produce

Sweeps are slow and their output is not re-derivable without re-running.

- `notes/` — one markdown note per meaningful run, written by
  `swing_lab.py --md`. Results, dated. Never edited after the fact.
- `memory/` — junction to my memory dir. Decisions, constraints, and user
  preferences; one fact per file, `[[wikilinks]]` between them. Not run
  output. Gitignored (the files live outside the repo).

`notes/` is committed — it is the durable record and the only thing that
survives a new machine.

Before starting research that resembles earlier work, read `notes/` — the
answer may already be there.

## After a sweep, write the conclusion down

Do this without being asked. A note in `notes/` records *what happened*; it
does not record *what it meant*, and the judgment is the part that is
expensive to reconstruct. When a run settles a question — a variant is dead,
an instrument class behaves differently, a rule turned out to be doing
nothing — add one file to `memory/` saying so, and link it to the note that
produced it. One fact per file.

Kill results count. "TSMOM on equity ETFs does not beat B&H out-of-sample"
is worth more than another sweep that re-discovers it in six weeks.
