//+------------------------------------------------------------------+
//| CustomImport.mq5                                                 |
//| Creates a custom symbol and loads bars from a CSV in MQL5\Files. |
//| Replaces the Symbols -> Bars -> Import GUI dance. No broker      |
//| account or connection needed.                                    |
//|                                                                  |
//| Drag onto any chart, pick the file, done.                        |
//+------------------------------------------------------------------+
#property strict
#property script_show_inputs

input string CsvFile    = "VOO_D1.csv";  // must sit in MQL5\Files\
input string CustomName = "VOO_D1";      // custom symbol to create
input int    Digits_    = 2;
input double TickSize   = 0.01;

//+------------------------------------------------------------------+
bool EnsureSymbol(string name)
{
   if(CustomSymbolCreate(name, "Custom\\" + name))
      Print("created custom symbol ", name);
   else
   {
      int err = GetLastError();
      if(err == 5300 || err == 5304)          // already exists - reuse it
      {
         Print("custom symbol ", name, " already exists, reusing");
         ResetLastError();
      }
      else
      {
         Print("CustomSymbolCreate failed, error ", err);
         return false;
      }
   }

   CustomSymbolSetInteger(name, SYMBOL_DIGITS, Digits_);
   CustomSymbolSetDouble(name, SYMBOL_TRADE_TICK_SIZE, TickSize);
   CustomSymbolSetDouble(name, SYMBOL_TRADE_TICK_VALUE, TickSize);
   CustomSymbolSetDouble(name, SYMBOL_POINT, TickSize);
   CustomSymbolSetDouble(name, SYMBOL_TRADE_CONTRACT_SIZE, 1.0);
   CustomSymbolSetDouble(name, SYMBOL_VOLUME_MIN, 1.0);
   CustomSymbolSetDouble(name, SYMBOL_VOLUME_STEP, 1.0);
   CustomSymbolSetDouble(name, SYMBOL_VOLUME_MAX, 1000000.0);
   CustomSymbolSetInteger(name, SYMBOL_TRADE_CALC_MODE, SYMBOL_CALC_MODE_EXCH_STOCKS);
   CustomSymbolSetInteger(name, SYMBOL_TRADE_MODE, SYMBOL_TRADE_MODE_FULL);
   CustomSymbolSetInteger(name, SYMBOL_TRADE_EXEMODE, SYMBOL_TRADE_EXECUTION_INSTANT);
   CustomSymbolSetString(name, SYMBOL_CURRENCY_BASE, "USD");
   CustomSymbolSetString(name, SYMBOL_CURRENCY_PROFIT, "USD");
   CustomSymbolSetString(name, SYMBOL_CURRENCY_MARGIN, "USD");
   CustomSymbolSetString(name, SYMBOL_DESCRIPTION, "Vanguard S&P 500 ETF (imported)");
   return true;
}

//+------------------------------------------------------------------+
void OnStart()
{
   if(!EnsureSymbol(CustomName))
      return;

   int fh = FileOpen(CsvFile, FILE_READ | FILE_TXT | FILE_ANSI);
   if(fh == INVALID_HANDLE)
   {
      Print("cannot open ", CsvFile, " in MQL5\\Files - error ", GetLastError());
      return;
   }

   MqlRates rates[];
   int n = 0;
   int lineNo = 0;
   int skipped = 0;

   while(!FileIsEnding(fh))
   {
      string line = FileReadString(fh);
      lineNo++;
      if(StringLen(line) < 10 || StringFind(line, "<DATE>") >= 0)
         continue;                                   // header or blank

      string f[];
      if(StringSplit(line, '\t', f) < 7)
      {
         skipped++;
         continue;
      }

      datetime t = StringToTime(f[0] + " " + f[1]);
      if(t <= 0)
      {
         skipped++;
         continue;
      }

      ArrayResize(rates, n + 1, 4096);
      rates[n].time         = t;
      rates[n].open         = StringToDouble(f[2]);
      rates[n].high         = StringToDouble(f[3]);
      rates[n].low          = StringToDouble(f[4]);
      rates[n].close        = StringToDouble(f[5]);
      rates[n].tick_volume  = (long)StringToInteger(f[6]);
      rates[n].real_volume  = 0;
      rates[n].spread       = 0;

      // A bar whose high is below its low would poison the tester silently.
      if(rates[n].high < rates[n].low || rates[n].open <= 0)
      {
         skipped++;
         continue;
      }
      n++;
   }
   FileClose(fh);

   if(n == 0)
   {
      Print("no usable rows parsed from ", CsvFile, " (", lineNo, " lines read)");
      return;
   }

   int written = CustomRatesUpdate(CustomName, rates, n);
   if(written < 0)
   {
      Print("CustomRatesUpdate failed, error ", GetLastError());
      return;
   }

   SymbolSelect(CustomName, true);   // show it in Market Watch

   PrintFormat("%s: parsed %d bars (%d skipped), written %d, range %s .. %s",
               CustomName, n, skipped, written,
               TimeToString(rates[0].time, TIME_DATE),
               TimeToString(rates[n - 1].time, TIME_DATE));
   Print("Now open Ctrl+R, pick ", CustomName, ", and run the EA.");
}
//+------------------------------------------------------------------+
