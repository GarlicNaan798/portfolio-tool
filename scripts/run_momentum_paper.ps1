$ErrorActionPreference = "Stop"

$Repo = "C:\Users\Adnan\OneDrive\Desktop\portfoliotool"
$Python = "C:\Users\Adnan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$LogDir = Join-Path $Repo "state"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutLog = Join-Path $LogDir "scheduled_momentum_$Stamp.out.log"
$ErrLog = Join-Path $LogDir "scheduled_momentum_$Stamp.err.log"

Set-Location $Repo
$env:PYTHONPATH = "src"
$env:PORTFOLIO_DRY_RUN = "false"

& $Python -m portfolio_model.momentum_signal `
  --cache state/backtest_bars_sp500.json `
  --output-dir state `
  --refresh-data `
  --sleeve-fraction 0.10 `
  --execute-paper `
  --max-order-notional 3000 `
  1> $OutLog 2> $ErrLog

$ExitCode = $LASTEXITCODE
Add-Content -Path $OutLog -Value "ExitCode=$ExitCode"
exit $ExitCode
