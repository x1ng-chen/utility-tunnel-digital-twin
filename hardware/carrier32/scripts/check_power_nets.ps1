param(
    [string]$Schematic,
    [string]$Netlist
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Schematic) { $Schematic = Join-Path $projectRoot 'carrier32.kicad_sch' }
if (-not $Netlist) { $Netlist = Join-Path $projectRoot 'build/power.net' }
$tool = Join-Path $projectRoot '.venv/Scripts/kicad-tool.exe'

$nets = (& $tool sch query list $Schematic nets --netlist $Netlist --format json | ConvertFrom-Json).items
if ($LASTEXITCODE -ne 0) { throw 'Unable to query KiCad netlist.' }
$pinToNet = @{}
foreach ($net in $nets) {
    foreach ($node in $net.nodes) {
        $key = "$($node.ref).$($node.pin)"
        if ($pinToNet.ContainsKey($key)) { throw "Duplicate net assignment for $key" }
        $pinToNet[$key] = $net.name.TrimStart('/')
    }
}

$expected = @{
    'J1.1'='12V_IN'; 'J1.2'='GND'
    'F1.1'='12V_IN'; 'F1.2'='12V_FUSED'
    'Q1.1'='12V_PROTECTED'; 'Q1.2'='12V_PROTECTED'; 'Q1.3'='12V_PROTECTED'; 'Q1.4'='Q1_GATE'
    'Q1.5'='12V_FUSED'; 'Q1.6'='12V_FUSED'; 'Q1.7'='12V_FUSED'; 'Q1.8'='12V_FUSED'
    'D1.1'='12V_PROTECTED'; 'D1.2'='Q1_GATE'
    'D2.1'='12V_PROTECTED'; 'D2.2'='GND'
    'F2.1'='12V_PROTECTED'; 'F2.2'='12V_FAN_A'
    'F3.1'='12V_PROTECTED'; 'F3.2'='12V_FAN_B'
    'F4.1'='12V_PROTECTED'; 'F4.2'='12V_MQ_BRANCH'
    'F5.1'='5V_MQ'; 'F5.2'='5V_MQ2'
    'F6.1'='5V_MQ'; 'F6.2'='5V_MQ4'
    'F7.1'='5V_MQ'; 'F7.2'='5V_MQ7'
    'F8.1'='5V_LOGIC'; 'F8.2'='5V_WS'
    'F9.1'='5V_LOGIC'; 'F9.2'='5V_SENSORS'
    'F10.1'='5V_LOGIC'; 'F10.2'='5V_RELAY'
    'U1.1'='SW_LOGIC'; 'U1.2'='SW_LOGIC'; 'U1.3'='SW_LOGIC'
    'U1.4'='BOOT_LOGIC'; 'U1.7'='FB_LOGIC'; 'U1.8'='GND'
    'U1.9'='12V_PROTECTED'; 'U1.10'='12V_PROTECTED'; 'U1.11'='12V_PROTECTED'; 'U1.12'='12V_PROTECTED'; 'U1.13'='GND'
    'U2.1'='SW_MQ'; 'U2.2'='SW_MQ'; 'U2.3'='SW_MQ'
    'U2.4'='BOOT_MQ'; 'U2.7'='FB_MQ'; 'U2.8'='GND'
    'U2.9'='12V_MQ_BRANCH'; 'U2.10'='12V_MQ_BRANCH'; 'U2.11'='12V_MQ_BRANCH'; 'U2.12'='12V_MQ_BRANCH'; 'U2.13'='GND'
    'L1.1'='SW_LOGIC'; 'L1.2'='5V_LOGIC'
    'L2.1'='SW_MQ'; 'L2.2'='5V_MQ'
    'C3.1'='12V_PROTECTED'; 'C19.1'='12V_PROTECTED'
    'C6.1'='5V_LOGIC'; 'C20.1'='5V_LOGIC'
    'C8.1'='12V_MQ_BRANCH'; 'C21.1'='12V_MQ_BRANCH'
    'C11.1'='5V_MQ'; 'C22.1'='5V_MQ'
    'U3.1'='5V_LOGIC'; 'U3.2'='GND'; 'U3.3'='5V_LOGIC'; 'U3.5'='ESP_A_RAW'
    'U4.1'='5V_LOGIC'; 'U4.2'='GND'; 'U4.3'='5V_LOGIC'; 'U4.5'='ESP_B_RAW'
    'JP1.1'='ESP_A_RAW'; 'JP1.2'='3V3_ESP_A'
    'JP3.1'='ESP_B_RAW'; 'JP3.2'='3V3_ESP_B'
}

$errors = @()
foreach ($key in $expected.Keys) {
    if ($pinToNet[$key] -ne $expected[$key]) {
        $errors += "$key expected $($expected[$key]), got $($pinToNet[$key])"
    }
}

$labels = (& $tool sch query list $Schematic labels --format json | ConvertFrom-Json).items
if ($LASTEXITCODE -ne 0) { throw 'Unable to query schematic labels.' }
foreach ($group in ($labels | Group-Object { "$($_.at.x),$($_.at.y)" })) {
    $names = @($group.Group.text | Sort-Object -Unique)
    if ($names.Count -gt 1) {
        $errors += "Conflicting labels at $($group.Name): $($names -join ', ')"
    }
}

foreach ($ref in @('U1', 'U2')) {
    $symbol = & $tool sch query symbol $Schematic $ref --format json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Unable to query $ref." }
    if ($symbol.lib_id -ne 'Carrier32:LMR51450FSQDRRRQ1') {
        $errors += "$ref uses $($symbol.lib_id), expected reviewed Carrier32 buck symbol"
    }
    $numbers = @($symbol.pins | ForEach-Object { [int]$_.number } | Sort-Object)
    if (($numbers -join ',') -ne ((1..13) -join ',')) {
        $errors += "$ref must have exactly TI pins 1..13; found $($numbers -join ',')"
    }
    foreach ($pin in @(5, 6)) {
        $modelPin = $symbol.pins | Where-Object { [int]$_.number -eq $pin }
        if ($modelPin.electrical_type -ne 'no_connect') {
            $errors += "$ref pin $pin intentionally open but symbol type is $($modelPin.electrical_type)"
        }
    }
}
$reverseFet = & $tool sch query symbol $Schematic Q1 --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Unable to query Q1.' }
if ($reverseFet.lib_id -ne 'Carrier32:AO4443') {
    $errors += "Q1 uses $($reverseFet.lib_id), expected reviewed Carrier32 AO4443 symbol"
}
$fetNumbers = @($reverseFet.pins | ForEach-Object { [int]$_.number } | Sort-Object)
if (($fetNumbers -join ',') -ne ((1..8) -join ',')) {
    $errors += "Q1 must have exactly AO4443 pins 1..8; found $($fetNumbers -join ',')"
}

# These footprints are intentionally unresolved until exact, rated MPNs or
# measured holder geometry have been reviewed. A generic-looking footprint
# here would create an unsafe false path to board sync and fabrication.
foreach ($ref in @('F1', 'U1', 'U2', 'L1', 'L2', 'C6', 'C20', 'C11', 'C22')) {
    $symbol = & $tool sch query symbol $Schematic $ref --format json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Unable to query $ref." }
    $footprint = @($symbol.properties | Where-Object { $_.key -eq 'Footprint' })[0].value
    if ($footprint) {
        $errors += "$ref has unresolved footprint '$footprint'; clear it or explicitly retire this release gate after sourcing review"
    }
}

if ($errors.Count) { throw ($errors -join [Environment]::NewLine) }
Write-Output "Power netlist contract PASS: $($expected.Count) pin assertions, TI 13-pin models, no conflicting labels, and provisional footprints blank."
