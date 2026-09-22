$ErrorActionPreference = 'Stop'

$runner = Join-Path $PSScriptRoot 'run_checks.ps1'
if (-not (Test-Path -LiteralPath $runner)) {
    throw "run_checks.ps1 is missing"
}

& $runner -Preflight
if ($LASTEXITCODE -ne 0) {
    throw "run_checks.ps1 -Preflight returned $LASTEXITCODE"
}

Write-Output 'run_checks preflight: PASS'
