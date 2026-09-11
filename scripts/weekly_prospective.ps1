<#
Ciclo semanal del laboratorio (fase prospectiva). Pensado para correr cada domingo por la noche (hora de Taipei),
después del corte de las 18:00 y antes del plazo del lunes 08:30.

Pasos:
  1. Captura las cotizaciones oficiales por fecha que falten (TWSE MI_INDEX, TPEx dailyQuotes), reanudable.
  2. Ejecuta los tres escenarios del backtest hasta la fecha de hoy (Taipei). El corte del domingo emite y archiva la
     lista de la semana entrante con la hora real del sistema (ingested_at) antes del plazo; las semanas anteriores
     se reutilizan del archivo si son idénticas (RawStore.find) y se miden con los datos nuevos.
  3. Ensambla las cabeceras de los informes 15/15b/15c desde los JSON, exporta docs/site/data.json y lo incrusta en docs/index.html.
  4. Commit + push a main y publicación en gh-pages.

Uso:
  .\scripts\weekly_prospective.ps1                 # ciclo completo
  .\scripts\weekly_prospective.ps1 -SkipBacktest   # sólo captura, informes, exportación y publicación (prueba rápida)
  .\scripts\weekly_prospective.ps1 -NoDeploy       # sin commit/push/publicación

Registro: data/weekly_prospective.log. No usa credenciales ni toca nada fuera del repositorio (el push usa el
gestor de credenciales de git ya configurado en la máquina).
#>
param(
  [switch]$SkipBacktest,
  [switch]$NoDeploy
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"
$python = (Get-Command python).Source
$log = Join-Path $root "data\weekly_prospective.log"
function Log($msg) { $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg; Write-Host $line; Add-Content -Path $log -Value $line -Encoding UTF8 }

$taipei = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId((Get-Date).ToUniversalTime(), "Taipei Standard Time")
$today = $taipei.ToString("yyyy-MM-dd")
$fetchFrom = $taipei.AddDays(-14).ToString("yyyy-MM-dd")
Log "=== ciclo semanal · hoy (Taipei) ${today} · SkipBacktest=${SkipBacktest} NoDeploy=${NoDeploy}"

# 1. capturas que falten (reanudable: salta sesiones ya archivadas)
Log "captura de cotizaciones oficiales $fetchFrom..$today"
& $python scripts/fetch_universe_daily.py --start $fetchFrom --end $today 2>&1 | Tee-Object -FilePath (Join-Path $root "data\store\weekly_fetch.log") | Out-Null
if ($LASTEXITCODE -ne 0) { Log "captura falló (rc=$LASTEXITCODE)"; exit 1 }

# 2. escenarios (en paralelo; ~1,5-2,5 h y ~3 GB cada uno). Las etiquetas de archivo son las de las corridas
#    originales de septiembre de 2026 para que las semanas ya archivadas se reutilicen (mismo packet_id → mismo hash).
$start = "2026-05-04"
$scenarios = @(
  @{ label = "universe_2026-05-04_$today"; archive = "universe_2026-05-04_2026-09-09"; report = "15_backtest_universo_2026.md";
     args = @("--lookback-start", "2024-07-01", "--min-train-weeks", "40") },
  @{ label = "user_75kTWD_oddlots_2026-05-04_$today"; archive = "user_75kTWD_oddlots_2026"; report = "15b_backtest_universo_2026_lotes_sueltos.md";
     args = @("--lookback-start", "2024-07-01", "--min-train-weeks", "40", "--notional", "15000", "--lot-size", "1", "--min-commission", "20", "--slippage-bps", "20") },
  @{ label = "universe_longhist_2021_2026-05-04_$today"; archive = "universe_longhist_2021_2026"; report = "15c_backtest_universo_2026_historial_2021.md";
     args = @("--lookback-start", "2021-01-04", "--min-train-weeks", "52") }
)
if (-not $SkipBacktest) {
  $procs = @()
  foreach ($s in $scenarios) {
    $a = @("scripts/run_backtest.py", "--manifest", "daily", "--start", $start, "--end", $today, "--forecasters", "Q0,Q1,A1",
           "--label", $s.label, "--archive-label", $s.archive, "--report", $s.report) + $s.args
    $out = Join-Path $root ("data\store\weekly_" + $s.archive + ".log")
    Log ("lanzo " + $s.label)
    $procs += Start-Process -FilePath $python -ArgumentList $a -WorkingDirectory $root -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError ($out + ".err")
  }
  foreach ($p in $procs) { $p.WaitForExit() }
  $failed = $procs | Where-Object { $_.ExitCode -ne 0 }
  if ($failed) { Log ("backtest falló: " + (($failed | ForEach-Object { $_.Id }) -join ",")); exit 1 }
  Log "escenarios terminados"
}

# 3. informes y sitio
& $python scripts/assemble_backtest_reports.py 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) { Log "ensamblado de informes falló"; exit 1 }
& $python scripts/export_site_data.py 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) { Log "exportación falló"; exit 1 }

# 4. publicación
if (-not $NoDeploy) {
  git add -A docs README.md 2>&1 | Out-Null
  $changes = git status --porcelain docs README.md
  if ($changes) {
    git -c user.name="Brayann Benavides" -c user.email="brayannbegu11@gmail.com" commit -q -m "Ciclo semanal ${today}: listas, resultados y sitio actualizados" 2>&1 | ForEach-Object { Log $_ }
    git push -q origin main 2>&1 | ForEach-Object { Log $_ }
    & $python scripts/deploy_pages.py 2>&1 | ForEach-Object { Log $_ }
    Log "publicado"
  } else {
    Log "sin cambios que publicar"
  }
}
Log "=== ciclo semanal terminado"
