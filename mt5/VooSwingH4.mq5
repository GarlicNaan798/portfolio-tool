//+------------------------------------------------------------------+
//| VooSwingH4.mq5                                                   |
//| H4 swing strategy for VOO / S&P500 trackers.                     |
//|                                                                  |
//| Regime filter (D1)  : time-series momentum, Moskowitz et al.     |
//|                       (2012) as used in Bird/Gao/Yeung. Long     |
//|                       only while the J-month return is positive. |
//| Entry timing (H4)   : Sarainmaa (2024) local-low logic - price   |
//|                       below its MA with RSI turning up out of    |
//|                       oversold.                                  |
//| Exits                : ATR stop, RSI mean-reversion exit, and a  |
//|                        bar-count exit standing in for the        |
//|                        papers' fixed holding period.             |
//+------------------------------------------------------------------+
#property strict

#include <Trade/Trade.mqh>

//--- regime (daily, from the momentum paper) ---
input int    MomentumLookbackDays = 63;    // J: 63=3mo, 126=6mo, 189=9mo, 252=12mo
input bool   UseSMA200Filter      = true;  // also require D1 close > SMA(200)

//--- entry timing (H4, from the thesis) ---
input int    MaPeriod             = 50;    // H4 MA; price must be below it to buy
input int    RsiPeriod            = 14;
input double RsiOversold          = 35.0;  // buy when RSI crosses back up through this
input double RsiOverbought        = 70.0;  // thesis sell signal

//--- exits ---
input int    AtrPeriod            = 14;
input double AtrStopMult          = 2.0;
input double AtrTargetMult        = 0.0;   // 0 = no fixed target
input int    MaxBarsInTrade       = 150;   // ~5 weeks of H4 bars on a 24h symbol; 0 = off
input bool   UseRsiExit           = true;

//--- risk ---
input double RiskPercent          = 1.0;   // equity risked per trade
input bool   AllowShorts          = false; // cash VOO can't short; CFDs can
input long   MagicNumber          = 20260810;

CTrade   trade;
int      hMaH4 = INVALID_HANDLE, hRsi = INVALID_HANDLE, hAtr = INVALID_HANDLE, hMaD1 = INVALID_HANDLE;
datetime lastBar = 0;

//+------------------------------------------------------------------+
//| Pure helpers - kept free of symbol state so SelfCheck can run     |
//| them with known numbers.                                          |
//+------------------------------------------------------------------+
bool CrossedUp(double prev, double cur, double level)
{
   return prev < level && cur >= level;
}

bool CrossedDown(double prev, double cur, double level)
{
   return prev > level && cur <= level;
}

// Returns 0 when the risk budget can't cover one minimum lot - refusing the
// trade is correct here, rounding up would silently exceed RiskPercent.
double LotsFromRisk(double riskMoney, double stopDist, double tickValue,
                    double tickSize, double step, double minVol, double maxVol)
{
   if(riskMoney <= 0 || stopDist <= 0 || tickValue <= 0 || tickSize <= 0 || step <= 0)
      return 0.0;

   double lossPerLot = (stopDist / tickSize) * tickValue;
   if(lossPerLot <= 0)
      return 0.0;

   double lots = MathFloor((riskMoney / lossPerLot) / step) * step;

   if(lots < minVol) return 0.0;
   if(lots > maxVol) lots = maxVol;
   return lots;
}

//+------------------------------------------------------------------+
bool SelfCheck()
{
   bool ok = true;

   if(!CrossedUp(30.0, 36.0, 35.0))            { Print("SelfCheck: CrossedUp miss");     ok = false; }
   if(CrossedUp(36.0, 40.0, 35.0))             { Print("SelfCheck: CrossedUp false +");  ok = false; }
   if(!CrossedDown(72.0, 68.0, 70.0))          { Print("SelfCheck: CrossedDown miss");   ok = false; }

   // $100 risk, 5.00 stop, $1 per 0.01 move => $500 loss per lot => 0.2 lots.
   double l = LotsFromRisk(100.0, 5.00, 1.0, 0.01, 0.01, 0.01, 100.0);
   if(MathAbs(l - 0.20) > 1e-8)                { PrintFormat("SelfCheck: lots=%.4f exp 0.20", l); ok = false; }

   // Same trade, but min volume is 1.0 lot -> too big for the budget, refuse.
   if(LotsFromRisk(100.0, 5.00, 1.0, 0.01, 0.01, 1.0, 100.0) != 0.0)
                                               { Print("SelfCheck: should refuse < minVol"); ok = false; }
   // Degenerate inputs must not divide by zero.
   if(LotsFromRisk(100.0, 0.0, 1.0, 0.01, 0.01, 0.01, 100.0) != 0.0)
                                               { Print("SelfCheck: zero stop"); ok = false; }

   Print(ok ? "SelfCheck: PASS" : "SelfCheck: FAIL");
   return ok;
}

//+------------------------------------------------------------------+
int OnInit()
{
   if(!SelfCheck())
      return INIT_FAILED;

   hMaH4 = iMA(_Symbol, PERIOD_H4, MaPeriod, 0, MODE_SMA, PRICE_CLOSE);
   hRsi  = iRSI(_Symbol, PERIOD_H4, RsiPeriod, PRICE_CLOSE);
   hAtr  = iATR(_Symbol, PERIOD_H4, AtrPeriod);
   hMaD1 = iMA(_Symbol, PERIOD_D1, 200, 0, MODE_SMA, PRICE_CLOSE);

   if(hMaH4 == INVALID_HANDLE || hRsi == INVALID_HANDLE ||
      hAtr  == INVALID_HANDLE || hMaD1 == INVALID_HANDLE)
   {
      Print("OnInit: indicator handle failed");
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(hMaH4);
   IndicatorRelease(hRsi);
   IndicatorRelease(hAtr);
   IndicatorRelease(hMaD1);
}

//+------------------------------------------------------------------+
//| Read `count` values from an indicator buffer starting at the last |
//| closed bar (shift 1).                                             |
//+------------------------------------------------------------------+
bool ReadBuf(int handle, int count, double &out[])
{
   ArraySetAsSeries(out, true);
   return CopyBuffer(handle, 0, 1, count, out) == count;
}

//+------------------------------------------------------------------+
//| +1 bullish, -1 bearish, 0 unknown/insufficient history.           |
//+------------------------------------------------------------------+
int Regime()
{
   double now  = iClose(_Symbol, PERIOD_D1, 1);
   double then = iClose(_Symbol, PERIOD_D1, 1 + MomentumLookbackDays);
   if(now <= 0 || then <= 0)
      return 0;

   int dir = (now > then) ? 1 : -1;

   if(UseSMA200Filter)
   {
      double ma[];
      ArraySetAsSeries(ma, true);
      if(CopyBuffer(hMaD1, 0, 1, 1, ma) != 1)
         return 0;
      if(dir > 0 && now < ma[0]) return 0;   // momentum up but below the 200 - stand aside
      if(dir < 0 && now > ma[0]) return 0;
   }
   return dir;
}

//+------------------------------------------------------------------+
void ManageOpenPosition(double rsiPrev, double rsiNow)
{
   long type = PositionGetInteger(POSITION_TYPE);

   if(MaxBarsInTrade > 0)
   {
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      int held = iBarShift(_Symbol, PERIOD_H4, opened, false);
      if(held >= MaxBarsInTrade)
      {
         trade.PositionClose(_Symbol);
         return;
      }
   }

   if(UseRsiExit)
   {
      if(type == POSITION_TYPE_BUY  && CrossedDown(rsiPrev, rsiNow, RsiOverbought))
         trade.PositionClose(_Symbol);
      else if(type == POSITION_TYPE_SELL && CrossedUp(rsiPrev, rsiNow, RsiOversold))
         trade.PositionClose(_Symbol);
   }
}

//+------------------------------------------------------------------+
void TryEntry(int dir, double rsiPrev, double rsiNow, double ma, double atr)
{
   double close = iClose(_Symbol, PERIOD_H4, 1);
   if(close <= 0 || atr <= 0)
      return;

   bool longSetup  = dir > 0 && close < ma && CrossedUp(rsiPrev, rsiNow, RsiOversold);
   bool shortSetup = AllowShorts && dir < 0 && close > ma && CrossedDown(rsiPrev, rsiNow, RsiOverbought);

   if(!longSetup && !shortSetup)
      return;

   double stopDist = atr * AtrStopMult;
   double lots = LotsFromRisk(
      AccountInfoDouble(ACCOUNT_EQUITY) * RiskPercent / 100.0,
      stopDist,
      SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE),
      SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE),
      SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP),
      SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN),
      SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX));

   if(lots <= 0)
      return;

   int    digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(longSetup)
   {
      double sl = NormalizeDouble(ask - stopDist, digits);
      double tp = AtrTargetMult > 0 ? NormalizeDouble(ask + atr * AtrTargetMult, digits) : 0.0;
      trade.Buy(lots, _Symbol, 0.0, sl, tp, "tsmom+rsi");
   }
   else
   {
      double sl = NormalizeDouble(bid + stopDist, digits);
      double tp = AtrTargetMult > 0 ? NormalizeDouble(bid - atr * AtrTargetMult, digits) : 0.0;
      trade.Sell(lots, _Symbol, 0.0, sl, tp, "tsmom+rsi");
   }
}

//+------------------------------------------------------------------+
void OnTick()
{
   // Act once per closed H4 bar. Everything below reads shift 1, so no
   // decision ever uses a bar that is still forming.
   datetime bt = iTime(_Symbol, PERIOD_H4, 0);
   if(bt == lastBar || bt == 0)
      return;
   lastBar = bt;

   double rsi[], ma[], atr[];
   if(!ReadBuf(hRsi, 2, rsi) || !ReadBuf(hMaH4, 1, ma) || !ReadBuf(hAtr, 1, atr))
      return;

   double rsiNow = rsi[0], rsiPrev = rsi[1];

   // Any open position on this symbol blocks a new entry - on a netting
   // account a second Buy would silently resize someone else's position.
   if(PositionSelect(_Symbol))
   {
      if(PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         ManageOpenPosition(rsiPrev, rsiNow);
      return;
   }

   int dir = Regime();
   if(dir == 0)
      return;

   TryEntry(dir, rsiPrev, rsiNow, ma[0], atr[0]);
}
//+------------------------------------------------------------------+
