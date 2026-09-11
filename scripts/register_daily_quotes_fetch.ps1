<#
Registra (o elimina) la tarea programada de Windows que captura a diario las cotizaciones oficiales por fecha
(TWSE MI_INDEX y TPEx dailyQuotes) de los últimos días que falten.

Por qué existe (ronda 20, R20-06): para que una lista cuente como predicción del protocolo, todos los datos del
paquete deben haberse recibido ANTES del corte del domingo 18:00 Taipei. El ciclo semanal corre después del corte,
así que la captura de la sesión del viernes debe ocurrir antes: esta tarea corre todos los días a las 18:45 hora
local del este de EE. UU. (06:45 Taipei del día siguiente en verano, 07:45 en invierno), de modo que la sesión del
viernes queda archivada el sábado por la mañana en Taipei, con ingested_at real y anterior al corte.

Uso:
  .\scripts\register_daily_quotes_fetch.ps1                 # todos los días a las 18:45 hora local
  .\scripts\register_daily_quotes_fetch.ps1 -Hora 19:15
  .\scripts\register_daily_quotes_fetch.ps1 -Eliminar
#>
param(
  [string]$Hora = "18:45",
  [string]$Nombre = "taiwan-ia-lab cotizaciones por fecha",
  [switch]$Eliminar
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if ($Eliminar) {
  Unregister-ScheduledTask -TaskName $Nombre -Confirm:$false
  Write-Host "Tarea '$Nombre' eliminada."
  exit 0
}

$python = (Get-Command python).Source
$script = Join-Path $root "scripts\fetch_universe_daily.py"
$log = Join-Path $root "data\daily_quotes_fetch.log"
if (-not (Test-Path $script)) { throw "No existe $script" }

# --start se calcula en cmd con PowerShell para tomar los últimos 10 días; el script es reanudable (salta lo ya archivado)
$inner = "for /f %d in ('powershell -NoProfile -Command ""(Get-Date).AddDays(-10).ToString('yyyy-MM-dd')""') do `"$python`" `"$script`" --start %d >> `"$log`" 2>&1"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $inner" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $Hora
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $Nombre -Action $action -Trigger $trigger -Settings $settings -Description "Captura diaria de las cotizaciones oficiales por fecha de TWSE/TPEx (taiwan-ia-lab)" -Force | Out-Null
Write-Host "Tarea '$Nombre' registrada: todos los días a las $Hora (hora local), con arranque diferido si el PC estaba apagado."
