<#
Registra (o elimina) la tarea programada de Windows que ejecuta la captura diaria.

NO se ejecuta automáticamente: registrar una tarea es un cambio persistente del sistema
y requiere decisión explícita del usuario. Revisa los parámetros y lánzalo a mano.

Uso:
  .\scripts\register_daily_capture.ps1                 # registra "taiwan-ia-lab captura diaria" a las 18:30 hora local
  .\scripts\register_daily_capture.ps1 -Hora 19:00     # otra hora
  .\scripts\register_daily_capture.ps1 -Eliminar       # elimina la tarea

Qué hace la tarea: `python scripts/capture_daily.py` en la raíz del repositorio, con salida
anexada a data/capture_daily.log. La captura escribe en data/raw con ingested_at real; no
usa credenciales ni toca nada fuera del repositorio.

Por qué 18:30 hora local: la sesión de TWSE cierra a las 13:30 Taipei y los OpenAPI se
actualizan a lo largo de la tarde; los endpoints son instantáneas (informe 02), así que
la captura debe correr todos los días, también festivos y fines de semana.
Ajusta la hora si el PC no suele estar encendido a esa hora (la tarea se configura para
ejecutarse en cuanto arranque si se perdió el disparo).
#>
param(
  [string]$Hora = "18:30",
  [string]$Nombre = "taiwan-ia-lab captura diaria",
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
$script = Join-Path $root "scripts\capture_daily.py"
$log = Join-Path $root "data\capture_daily.log"
if (-not (Test-Path $script)) { throw "No existe $script" }

$cmd = "`"$python`" `"$script`" >> `"$log`" 2>&1"
# cmd /c recorta la primera y la última comilla cuando el comando empieza por comilla y tiene más de dos: el comando
# entero va entre otro par de comillas, si no la tarea termina con código 1 sin ejecutar nada ni escribir el log
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$cmd`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $Hora
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $Nombre -Action $action -Trigger $trigger -Settings $settings -Description "Captura diaria de TWSE/TPEx/FinMind a data/raw (taiwan-ia-lab)" -Force | Out-Null
Write-Host "Tarea '$Nombre' registrada: todos los días a las $Hora (hora local), con arranque diferido si el PC estaba apagado."
Write-Host "Comprobar: Get-ScheduledTask -TaskName '$Nombre' | Get-ScheduledTaskInfo"
