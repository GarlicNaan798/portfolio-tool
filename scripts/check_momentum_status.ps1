$ErrorActionPreference = "Stop"

$Repo = "C:\Users\Adnan\OneDrive\Desktop\portfoliotool"
$Python = "C:\Users\Adnan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$LogDir = Join-Path $Repo "state"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutLog = Join-Path $LogDir "scheduled_momentum_status_$Stamp.out.log"
$ErrLog = Join-Path $LogDir "scheduled_momentum_status_$Stamp.err.log"

Set-Location $Repo
$env:PYTHONPATH = "src"

& $Python -c "from pathlib import Path; from portfolio_model.env import load_dotenv; load_dotenv(Path('.env')); from portfolio_model.alpaca import AlpacaClient; c=AlpacaClient(); print('clock', c.clock()); print('orders'); [print(o.get('submitted_at'), o.get('symbol'), o.get('side'), o.get('status'), o.get('notional'), o.get('filled_qty'), o.get('filled_avg_price'), o.get('id')) for o in c.orders(status='all', limit=20)]; print('positions'); [print(p.get('symbol'), p.get('market_value'), p.get('unrealized_pl'), p.get('unrealized_plpc'), p.get('qty')) for p in c.positions()]" `
  1> $OutLog 2> $ErrLog

$ExitCode = $LASTEXITCODE
Add-Content -Path $OutLog -Value "ExitCode=$ExitCode"
exit $ExitCode
