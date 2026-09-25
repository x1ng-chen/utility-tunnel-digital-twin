param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$schematic = Join-Path $projectRoot 'carrier32.kicad_sch'
$contract = Join-Path $projectRoot 'config/connector-contract.csv'
$tool = Join-Path $projectRoot '.venv/Scripts/kicad-tool.exe'
$library = 'D:/KiCad/share/kicad/symbols/Connector_Generic.kicad_sym'
$env:KICAD_CLI = 'D:/KiCad/bin/kicad-cli.exe'
$env:PYTHONUTF8 = '1'

$rows = @(Import-Csv $contract)
if ($rows.Count -ne 32) { throw "Expected 32 sensor connectors, got $($rows.Count)" }
if (@($rows.board_ref | Select-Object -Unique).Count -ne 32) { throw 'Duplicate board reference in contract' }

function Invoke-KicadTool {
    param([string[]]$Arguments)
    $args2 = @($Arguments)
    if ($DryRun) { $args2 += '--dry-run' }
    $args2 += @('--format', 'json')
    & $tool @args2 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "kicad-tool failed: $($Arguments -join ' ')" }
}

$culture = [System.Globalization.CultureInfo]::InvariantCulture
$knownLabels = [System.Collections.Generic.HashSet[string]]::new()
$labelList = & $tool sch query list $schematic labels --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not query existing labels' }
foreach ($label in $labelList.items) {
    $key = '{0}|{1}|{2}' -f $label.text, $label.at.x.ToString('0.##',$culture), $label.at.y.ToString('0.##',$culture)
    [void]$knownLabels.Add($key)
}

for ($i = 0; $i -lt $rows.Count; $i++) {
    $row = $rows[$i]
    $x = 30 + 33 * ($i % 6)
    $y = 160 + 17 * [math]::Floor($i / 6)
    $pos = '{0},{1}' -f $x, $y

    $existing = & $tool sch query symbol $schematic $row.board_ref --format json | ConvertFrom-Json
    $exists = $LASTEXITCODE -eq 0
    if ($exists) {
        if ([math]::Abs($existing.at.x - $x) -gt 0.01 -or [math]::Abs($existing.at.y - $y) -gt 0.01) {
            throw "Existing $($row.board_ref) is not at expected $pos"
        }
    } else {
        $add = @('sch','edit','symbol','add',$schematic,'Connector_Generic:Conn_01x04',$row.board_ref,$pos,'--lib-file',$library)
        & $tool @add --dry-run --format json | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "dry-run add failed: $($row.board_ref)" }
        if ($DryRun) {
            Write-Output "would add $($row.board_ref) $($row.asset_code) at $pos"
            continue
        }
        Invoke-KicadTool $add
    }

    $fields = @(
        @('Value', $row.asset_code),
        @('Footprint', $row.connector_footprint)
    )
    foreach ($field in $fields) {
        $edit = @('sch','edit','symbol','set-property',$schematic,$row.board_ref,$field[0],$field[1])
        & $tool @edit --dry-run --format json | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "dry-run field failed: $($row.board_ref) $($field[0])" }
        Invoke-KicadTool $edit
    }

    $pins = @($row.pin1,$row.pin2,$row.pin3,$row.pin4)
    for ($p = 0; $p -lt 4; $p++) {
        if ($pins[$p] -eq 'NC') { continue }
        $pinY = $y - 2.54 + 2.54 * $p
        $pinX = $x - 5.08
        $xy = '{0},{1}' -f $pinX.ToString('0.##',$culture), $pinY.ToString('0.##',$culture)
        $key = '{0}|{1}|{2}' -f $pins[$p], $pinX.ToString('0.##',$culture), $pinY.ToString('0.##',$culture)
        if ($knownLabels.Contains($key)) { continue }
        $label = @('sch','edit','label','add',$schematic,'local',$pins[$p],$xy,'--rotation','180')
        & $tool @label --dry-run --format json | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "dry-run label failed: $($row.board_ref) pin $($p+1)" }
        Invoke-KicadTool $label
        [void]$knownLabels.Add($key)
    }
    Write-Output "$($row.board_ref) $($row.asset_code) at $pos"
}

Write-Output "Sensor connector contract processed: $($rows.Count) (dry-run=$DryRun)"
