param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$board = Join-Path $projectRoot 'carrier32.kicad_pcb'
$tool = Join-Path $projectRoot '.venv/Scripts/kicad-tool.exe'
$env:KICAD_CLI = 'D:/KiCad/bin/kicad-cli.exe'
$env:KICAD10_FOOTPRINT_DIR = 'D:/KiCad/share/kicad/footprints'
$env:PYTHONUTF8 = '1'

# Approximate power-area placement only. The board is not routed or frozen.
# Coordinates keep the input/protection chain near the left edge, the two
# buck stages apart, and each ESP LDO near its later socket corridor.
$positions = [ordered]@{
    J1='62,75'; Q1='92,75'; R1='91,88'; D1='99,87'; D2='106,75';
    C1='118,75'; C2='136,75';
    F2='92,60'; F3='105,60'; F4='118,60';
    C19='115,100'; C3='123,100'; C4='130,100'; C5='147,95';
    C7='164,111'; R2='160,105'; R3='160,115'; R4='171,117';
    F8='192,93'; F9='203,93'; F10='214,93';
    C21='115,138'; C8='123,138'; C9='130,138'; C10='147,133';
    C12='164,149'; R5='160,143'; R6='160,153'; R7='171,155';
    F5='192,138'; F6='203,138'; F7='214,138';
    U3='235,91'; C13='226,91'; C14='242,91'; C15='254,91';
    JP1='263,87'; JP2='263,96'; TP1='274,87';
    U4='235,136'; C16='226,136'; C17='242,136'; C18='254,136';
    JP3='263,132'; JP4='263,141'; TP2='274,132'
}

foreach ($entry in $positions.GetEnumerator()) {
    $args = @('pcb', 'edit', 'footprint', 'move', $board, $entry.Key, $entry.Value)
    if ($DryRun) { $args += '--dry-run' }
    & $tool @args --format json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "move $($entry.Key) failed" }
}
Write-Output "power footprints positioned: $($positions.Count) (dry-run=$DryRun)"
