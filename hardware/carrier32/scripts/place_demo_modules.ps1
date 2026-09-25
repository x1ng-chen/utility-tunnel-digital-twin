$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$board = Join-Path $projectRoot 'carrier32.kicad_pcb'
$tool = Join-Path $projectRoot '.venv/Scripts/kicad-tool.exe'
$env:KICAD_CLI = 'D:/KiCad/bin/kicad-cli.exe'
$env:KICAD10_FOOTPRINT_DIR = 'D:/KiCad/share/kicad/footprints'
$env:PYTHONUTF8 = '1'

$placements = @(
    @('J_MCU_A',320,85), @('J_MCU_B',375,85),
    @('J_ESP_A',320,150), @('J_ESP_B',375,150),
    @('J_TFT_A',320,185), @('J_TFT_B',375,185),
    @('J_JOY',315,220), @('J_FAN_A',345,220), @('J_FAN_B',375,220),
    @('J_INA_A',315,250), @('J_INA_B',345,250),
    @('J_RELAY',375,250), @('J_BUZZER',395,250)
)
for ($i = 1; $i -le 18; $i++) {
    $ref = 'D_WS{0:00}' -f $i
    $x = 75 + 34 * (($i - 1) % 9)
    $y = 274 + 22 * [math]::Floor(($i - 1) / 9)
    $placements += ,@($ref,$x,$y)
}

foreach ($placement in $placements) {
    $ref,$x,$y = $placement
    $xy = $x.ToString()+','+$y.ToString()
    & $tool pcb edit footprint move $board $ref $xy --format json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Placement failed: $ref" }
}
Write-Output "Placed $($placements.Count) demo-module footprints"
