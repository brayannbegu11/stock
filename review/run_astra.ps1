<#
Lanza una ronda de revisión adversarial con GPT-6 Astra (Codex CLI) sobre este repositorio.

Uso:
  .\review\run_astra.ps1 -Ronda ronda2_correcciones [-Effort high|xhigh]

- Árbol congelado: antes de la ronda se calcula el sha256 de todos los archivos revisables
  (docs, src, tests, scripts, AGENTS.md, pyproject.toml, review/prompts, review/schemas)
  y se guarda como baseline; al terminar se recalcula y cualquier diferencia se informa.
- Sandbox workspace-write (necesario para que pytest cree temporales); el revisor tiene
  instrucción de no modificar archivos y la comprobación de integridad lo verifica.
- Esfuerzo de razonamiento forzado por invocación (la config global está en "low").
- Salida final validada contra review/schemas/hallazgos.schema.json y archivada con hora UTC.
#>
param(
  [Parameter(Mandatory = $true)][string]$Ronda,
  [ValidateSet("medium", "high", "xhigh")][string]$Effort = "high"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$prompt = Join-Path $root "review\prompts\$Ronda.md"
if (-not (Test-Path $prompt)) { throw "No existe el prompt $prompt" }
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$outDir = Join-Path $root "review\out"
New-Item -ItemType Directory -Force $outDir | Out-Null
$last = Join-Path $outDir "$Ronda`_$stamp.json"
$log = Join-Path $outDir "$Ronda`_$stamp.log"
$baseline = Join-Path $outDir "$Ronda`_$stamp`_baseline.sha256"

function Get-TreeHashes {
  $paths = @("docs", "src", "tests", "scripts", "AGENTS.md", "pyproject.toml", "README.md", "review\prompts", "review\schemas", "data\reference", "data\audit")
  Get-ChildItem -Path ($paths | ForEach-Object { Join-Path $root $_ }) -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "__pycache__" } |
    Sort-Object FullName |
    ForEach-Object { "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $_.FullName).Hash, $_.FullName.Substring($root.Length + 1) }
}

$before = Get-TreeHashes
$before | Set-Content -Encoding UTF8 $baseline
Write-Host "Astra · ronda=$Ronda · effort=$Effort · archivos congelados=$($before.Count) · salida=$last"

Get-Content $prompt -Raw | codex exec `
  --skip-git-repo-check `
  -C $root `
  -s workspace-write `
  -c "model_reasoning_effort=`"$Effort`"" `
  --output-schema (Join-Path $root "review\schemas\hallazgos.schema.json") `
  -o $last `
  - 2>&1 | Tee-Object -FilePath $log

$after = Get-TreeHashes
$diff = Compare-Object -ReferenceObject $before -DifferenceObject $after
if ($diff) {
  Write-Host "ADVERTENCIA: el árbol cambió durante la revisión:" -ForegroundColor Yellow
  $diff | Format-Table -AutoSize
} else {
  Write-Host "Integridad: ningún archivo revisable cambió durante la ronda." -ForegroundColor Green
}
Get-FileHash -Algorithm SHA256 $last | Format-List
