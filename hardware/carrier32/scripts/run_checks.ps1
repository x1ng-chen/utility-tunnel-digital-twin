param(
    [switch]$Preflight
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$kicadCli = 'D:\KiCad\bin\kicad-cli.exe'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Program,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program exited with code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $kicadCli)) {
    throw "KiCad CLI not found at $kicadCli"
}

$projectFile = Join-Path $projectRoot 'carrier32.kicad_pro'
$jobsetFile = Join-Path $projectRoot 'carrier32.kicad_jobset'
foreach ($requiredFile in @($projectFile, $jobsetFile)) {
    if (-not (Test-Path -LiteralPath $requiredFile)) {
        throw "Required project file is missing: $requiredFile"
    }
}

Invoke-Checked -Program $kicadCli -Arguments @('version')

if ($Preflight) {
    Write-Output 'carrier32 preflight: PASS'
    exit 0
}

$designInputChecker = Join-Path $PSScriptRoot 'check_design_inputs.py'
$netContractChecker = Join-Path $PSScriptRoot 'check_net_contract.py'
$bundleChecker = Join-Path $PSScriptRoot 'check_fabrication_bundle.py'
foreach ($checker in @($designInputChecker, $netContractChecker, $bundleChecker)) {
    if (-not (Test-Path -LiteralPath $checker)) {
        throw "Full verification is unavailable until this checker exists: $checker"
    }
}

Invoke-Checked -Program 'python' -Arguments @($designInputChecker, '--phase', 'fabrication', (Join-Path $projectRoot 'config\design-inputs.csv'))
Invoke-Checked -Program 'python' -Arguments @($netContractChecker, (Join-Path $projectRoot 'config\net-contract.csv'))
Invoke-Checked -Program 'python' -Arguments @($bundleChecker, $projectRoot)
