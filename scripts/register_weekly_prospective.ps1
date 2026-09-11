<#
Registra (o elimina) la tarea programada de Windows que ejecuta el ciclo semanal prospectivo.

Uso:
  .\scripts\register_weekly_prospective.ps1                # domingos a las 08:00 hora local (= 20:00 Taipei en horario de verano de EE. UU.)
  .\scripts\register_weekly_prospective.ps1 -Hora 07:00    # otra hora
  .\scripts\register_weekly_prospective.ps1 -Eliminar

Por qué domingo por la mañana (hora local del este de EE. UU.): el corte del protocolo es el domingo 18:00 Taipei
(06:00 hora local en verano, 05:00 en invierno) y el plazo es el lunes 08:30 Taipei (20:30 / 19:30 hora local del
domingo). Los tres escenarios tardan hasta 2,5 h; a las 08:00 locales terminan hacia las 11:00, con margen.
Si el PC estaba apagado, la tarea se ejecuta en cuanto arranca (StartWhenAvailable); si arranca después del plazo,
la lista de esa semana queda archivada con su hora real y el sitio la muestra como emitida fuera de plazo.
#>
param(
  [string]$Hora = "08:00",
  [string]$Nombre = "taiwan-ia-lab ciclo semanal",
  [switch]$Eliminar
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if ($Eliminar) {
  Unregister-ScheduledTask -TaskName $Nombre -Confirm:$false
  Write-Host "Tarea '$Nombre' eliminada."
  exit 0
}

$pwsh = (Get-Command pwsh).Source
$script = Join-Path $root "scripts\weekly_prospective.ps1"
if (-not (Test-Path $script)) { throw "No existe $script" }

$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At $Hora
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 6) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $Nombre -Action $action -Trigger $trigger -Settings $settings -Description "Ciclo semanal prospectivo de taiwan-ia-lab: capturas, escenarios, informes y publicación" -Force | Out-Null
Write-Host "Tarea '$Nombre' registrada: domingos a las $Hora (hora local), con arranque diferido si el PC estaba apagado."
Write-Host "Comprobar: Get-ScheduledTask -TaskName '$Nombre' | Get-ScheduledTaskInfo"
