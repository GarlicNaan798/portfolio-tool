---
name: sarainmaa-2024-sp500-ml
description: Random-forest swing trading on the S&P500 shows no significant edge over buy and hold, p = 0.83.
metadata:
  type: reference
---
Sarainmaa (2024), "Swing trading the S&P500 index with technical analysis and
machine learning methods with responsible way", Master's thesis, Turku. In the
repo root as `sarainmaa_olli.pdf`.

Balanced random forest on daily bars. Features: SMA(50), SMA(200), RSI(14),
volume change, seasonality. Labels mark local extrema at +/-2% over a
five-week window. Train 2010-2017, test 2018-2019, charging 0.25% per trade.
It beat buy and hold on the test set, but across 20 randomly chosen two-month
windows Welch's t-test returned **p = 0.83** - the null could not be rejected.

**For us:** source of the dip-entry logic and the 0.25% fee assumption. Its
own headline is a null result, which we reproduced independently. Section 5.1
holds the labelling scheme.
