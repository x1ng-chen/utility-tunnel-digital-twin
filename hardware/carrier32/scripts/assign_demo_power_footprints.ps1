$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$schematic = Join-Path $projectRoot 'carrier32.kicad_sch'
$tool = Join-Path $projectRoot '.venv/Scripts/kicad-tool.exe'
$env:KICAD_CLI = 'D:/KiCad/bin/kicad-cli.exe'
$env:PYTHONUTF8 = '1'
$footprints = @{
    C6='Capacitor_SMD:C_1210_3225Metric'; C11='Capacitor_SMD:C_1210_3225Metric'
    C20='Capacitor_SMD:C_1210_3225Metric'; C22='Capacitor_SMD:C_1210_3225Metric'
    F1='Fuse:Fuse_1812_4532Metric'
    L1='Inductor_SMD:L_Abracon_ASPI-0628'; L2='Inductor_SMD:L_Abracon_ASPI-0628'
    U1='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'; U2='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'
}
foreach ($ref in @($footprints.Keys | Sort-Object)) {
    $fp = $footprints[$ref]
    & $tool sch edit symbol set-property $schematic $ref Footprint $fp --dry-run --format json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Dry-run failed: $ref" }
    & $tool sch edit symbol set-property $schematic $ref Footprint $fp --format json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Set failed: $ref" }
    Write-Output "$ref $fp"
}
