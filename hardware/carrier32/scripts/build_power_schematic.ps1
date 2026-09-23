param(
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$schematic = Join-Path $projectRoot 'carrier32.kicad_sch'
$tool = Join-Path $projectRoot '.venv/Scripts/kicad-tool.exe'
$seedTemplate = 'D:/KiCad/share/kicad/template/API_Series-500/API_Series-500.kicad_sch'
$symbolRoot = 'D:/KiCad/share/kicad/symbols'
$projectSymbolFile = Join-Path $projectRoot 'lib/carrier32.kicad_sym'
$env:KICAD_CLI = 'D:/KiCad/bin/kicad-cli.exe'
$env:PYTHONUTF8 = '1'

if (-not (Test-Path $tool)) {
    throw "kicad-tool is missing: $tool"
}

function Assert-NativeSuccess {
    param([string]$Action)
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE"
    }
}

New-Item -ItemType Directory -Force (Split-Path -Parent $schematic) | Out-Null

if ($Rebuild -or -not (Test-Path $schematic)) {
    # kicad-tool adds labels by cloning an existing same-kind item. The official
    # API template provides a valid local-label seed; all template circuitry is
    # removed below through kicad-tool before carrier circuitry is added.
    Copy-Item -LiteralPath $seedTemplate -Destination $schematic -Force

    $seedLabels = (& $tool sch query list $schematic labels --format json | ConvertFrom-Json).items
    Assert-NativeSuccess 'query seed labels'
    if (-not $seedLabels) { throw 'Seed template contains no local label.' }
    $script:seedLabelUuid = $seedLabels[0].uuid

    (& $tool sch query list $schematic symbols --format json | ConvertFrom-Json).items | ForEach-Object {
        & $tool sch edit symbol delete $schematic $_.ref --format json | Out-Null
        Assert-NativeSuccess "delete seed symbol $($_.ref)"
    }
    (& $tool sch query list $schematic wires --format json | ConvertFrom-Json).items | ForEach-Object {
        & $tool sch edit wire delete $schematic $_.uuid --format json | Out-Null
        Assert-NativeSuccess "delete seed wire $($_.uuid)"
    }
    (& $tool sch query list $schematic junctions --format json | ConvertFrom-Json).items | ForEach-Object {
        & $tool sch edit junction delete $schematic $_.uuid --format json | Out-Null
        Assert-NativeSuccess "delete seed junction $($_.uuid)"
    }
    $seedLabels | Select-Object -Skip 1 | ForEach-Object {
        & $tool sch edit label delete $schematic $_.uuid --format json | Out-Null
        Assert-NativeSuccess "delete seed label $($_.uuid)"
    }
}

function Add-Symbol {
    param(
        [string]$Library,
        [string]$Id,
        [string]$Reference,
        [string]$At,
        [string]$Value,
        [string]$Footprint = '',
        [string]$Datasheet = ''
    )

    if ($Library -eq 'Carrier32') { $libFile = $projectSymbolFile }
    else { $libFile = Join-Path $symbolRoot "$Library.kicad_sym" }
    & $tool sch edit symbol add $schematic "${Library}:$Id" $Reference $At --lib-file $libFile --format json | Out-Null
    Assert-NativeSuccess "add symbol $Reference"
    if ($Value) {
        & $tool sch edit symbol set-property $schematic $Reference Value $Value --format json | Out-Null
        Assert-NativeSuccess "set $Reference value"
    }
    if ($Footprint) {
        & $tool sch edit symbol set-property $schematic $Reference Footprint $Footprint --format json | Out-Null
        Assert-NativeSuccess "set $Reference footprint"
    }
    if ($Datasheet) {
        & $tool sch edit symbol set-property $schematic $Reference Datasheet $Datasheet --format json | Out-Null
        Assert-NativeSuccess "set $Reference datasheet"
    }
}

function Add-Label {
    param([string]$Name, [string]$At, [int]$Rotation = 0)
    & $tool sch edit label add $schematic local $Name $At --rotation $Rotation --format json | Out-Null
    Assert-NativeSuccess "add label $Name at $At"
}

# Input protection and protected branches.
Add-Symbol Connector_Generic Conn_01x02 J1 '25.4,30.48' '12V INPUT' 'TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal'
Add-Symbol Device Fuse F1 '40.64,27.94' 'SELECT_BY_TEST'
Add-Symbol Carrier32 AO4443 Q1 '55.88,27.94' 'AO4443' 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'
Add-Symbol Device D_Zener D1 '55.88,40.64' '12V GATE CLAMP' 'Diode_SMD:D_SOD-123'
Add-Symbol Device R_Small R1 '48.26,40.64' '100k' 'Resistor_SMD:R_0603_1608Metric'
Add-Symbol Device D_TVS D2 '68.58,40.64' 'SMBJ18CA' 'Diode_SMD:D_SMB'
Add-Symbol Device C_Small C1 '76.2,40.64' '470u/25V' 'Capacitor_SMD:CP_Elec_10x10'
Add-Symbol Device C_Small C2 '83.82,40.64' '100n/50V' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device Fuse F2 '96.52,25.4' 'FAN_A_SELECT_BY_TEST' 'Fuse:Fuse_1812_4532Metric'
Add-Symbol Device Fuse F3 '109.22,25.4' 'FAN_B_SELECT_BY_TEST' 'Fuse:Fuse_1812_4532Metric'
Add-Symbol Device Fuse F4 '121.92,25.4' 'MQ_SELECT_BY_TEST' 'Fuse:Fuse_1812_4532Metric'
Add-Symbol Device Fuse F5 '109.22,139.7' 'MQ2_SELECT_BY_TEST' 'Fuse:Fuse_1812_4532Metric'
Add-Symbol Device Fuse F6 '121.92,139.7' 'MQ4_SELECT_BY_TEST' 'Fuse:Fuse_1812_4532Metric'
Add-Symbol Device Fuse F7 '134.62,139.7' 'MQ7_SELECT_BY_TEST' 'Fuse:Fuse_1812_4532Metric'
Add-Symbol Device Fuse F8 '109.22,91.44' 'WS2812_SELECT_BY_TEST' 'Fuse:Fuse_1812_4532Metric'
Add-Symbol Device Fuse F9 '121.92,91.44' 'SENSORS_SELECT_BY_TEST' 'Fuse:Fuse_1812_4532Metric'
Add-Symbol Device Fuse F10 '134.62,91.44' 'RELAY_SELECT_BY_TEST' 'Fuse:Fuse_1812_4532Metric'

# Two independent 5 V buck stages. Custom 13-pad electrical model follows
# TI's pin table; the exact DRR land pattern remains a mechanical review gate.
Add-Symbol Carrier32 LMR51450FSQDRRRQ1 U1 '50.8,76.2' 'LMR51450FSQDRRRQ1 (LOGIC)'
Add-Symbol Device L_Small L1 '76.2,71.12' '4.7uH >=6A RMS, >=10A ISAT'
Add-Symbol Device C_Small C3 '35.56,68.58' '4.7u/50V X7R' 'Capacitor_SMD:C_1210_3225Metric'
Add-Symbol Device C_Small C19 '27.94,68.58' '4.7u/50V X7R' 'Capacitor_SMD:C_1210_3225Metric'
Add-Symbol Device C_Small C4 '35.56,76.2' '100n/50V X7R' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device C_Small C5 '63.5,63.5' '100n/16V X7R BOOT' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device C_Small C6 '88.9,76.2' '>=33u effective/16V X7R'
Add-Symbol Device C_Small C20 '96.52,76.2' '>=33u effective/16V X7R'
Add-Symbol Device R_Small R2 '83.82,83.82' '100k 1%' 'Resistor_SMD:R_0603_1608Metric'
Add-Symbol Device R_Small R3 '83.82,91.44' '19.1k 1%' 'Resistor_SMD:R_0603_1608Metric'
Add-Symbol Device C_Small C7 '91.44,83.82' '33pF CFF' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device R_Small R4 '71.12,91.44' '1k RFF' 'Resistor_SMD:R_0603_1608Metric'

Add-Symbol Carrier32 LMR51450FSQDRRRQ1 U2 '50.8,119.38' 'LMR51450FSQDRRRQ1 (MQ)'
Add-Symbol Device L_Small L2 '76.2,114.3' '4.7uH >=6A RMS, >=10A ISAT'
Add-Symbol Device C_Small C8 '35.56,111.76' '4.7u/50V X7R' 'Capacitor_SMD:C_1210_3225Metric'
Add-Symbol Device C_Small C21 '27.94,111.76' '4.7u/50V X7R' 'Capacitor_SMD:C_1210_3225Metric'
Add-Symbol Device C_Small C9 '35.56,119.38' '100n/50V X7R' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device C_Small C10 '63.5,106.68' '100n/16V X7R BOOT' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device C_Small C11 '88.9,119.38' '>=33u effective/16V X7R'
Add-Symbol Device C_Small C22 '96.52,119.38' '>=33u effective/16V X7R'
Add-Symbol Device R_Small R5 '83.82,127' '100k 1%' 'Resistor_SMD:R_0603_1608Metric'
Add-Symbol Device R_Small R6 '83.82,134.62' '19.1k 1%' 'Resistor_SMD:R_0603_1608Metric'
Add-Symbol Device C_Small C12 '91.44,127' '33pF CFF' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device R_Small R7 '71.12,134.62' '1k RFF' 'Resistor_SMD:R_0603_1608Metric'

# Independent ESP rails, each with a removable current link and LED-disable bridge.
# AP2112K-3.3 inherits its drawing/pins from AP2204K-1.5 in KiCad's standard
# library, so import the fully defined parent electrical model and set the exact MPN.
Add-Symbol Regulator_Linear 'AP2204K-1.5' U3 '127,71.12' 'AP2112K-3.3TRG1' 'Package_TO_SOT_SMD:SOT-23-5'
& $tool sch edit symbol set-property $schematic U3 Datasheet 'https://www.diodes.com/datasheet/download/AP2112.pdf' --format json | Out-Null
Assert-NativeSuccess 'set U3 AP2112 datasheet'
& $tool sch edit symbol set-property $schematic U3 Description '600mA AP2112K-3.3 fixed-output LDO; 3.8V-6V input; SOT-23-5' --format json | Out-Null
Assert-NativeSuccess 'set U3 AP2112 description'
Add-Symbol Device C_Small C13 '114.3,76.2' '1u X7R' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device C_Small C14 '139.7,76.2' '1u X7R' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device C_Small C15 '147.32,76.2' '100u LOW-ESR' 'Capacitor_SMD:CP_Elec_6.3x5.8'
Add-Symbol Jumper SolderJumper_2_Open JP1 '154.94,68.58' 'ESP_A_CURRENT_LINK' 'Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm'
Add-Symbol Connector TestPoint TP1 '165.1,68.58' '3V3_ESP_A_TEST' 'TestPoint:TestPoint_Plated_Hole_D2.0mm'
Add-Symbol Jumper SolderJumper_2_Open JP2 '154.94,76.2' 'ESP_A_LED_DISABLE' 'Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm'

Add-Symbol Regulator_Linear 'AP2204K-1.5' U4 '127,114.3' 'AP2112K-3.3TRG1' 'Package_TO_SOT_SMD:SOT-23-5'
& $tool sch edit symbol set-property $schematic U4 Datasheet 'https://www.diodes.com/datasheet/download/AP2112.pdf' --format json | Out-Null
Assert-NativeSuccess 'set U4 AP2112 datasheet'
& $tool sch edit symbol set-property $schematic U4 Description '600mA AP2112K-3.3 fixed-output LDO; 3.8V-6V input; SOT-23-5' --format json | Out-Null
Assert-NativeSuccess 'set U4 AP2112 description'
Add-Symbol Device C_Small C16 '114.3,119.38' '1u X7R' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device C_Small C17 '139.7,119.38' '1u X7R' 'Capacitor_SMD:C_0603_1608Metric'
Add-Symbol Device C_Small C18 '147.32,119.38' '100u LOW-ESR' 'Capacitor_SMD:CP_Elec_6.3x5.8'
Add-Symbol Jumper SolderJumper_2_Open JP3 '154.94,111.76' 'ESP_B_CURRENT_LINK' 'Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm'
Add-Symbol Connector TestPoint TP2 '165.1,111.76' '3V3_ESP_B_TEST' 'TestPoint:TestPoint_Plated_Hole_D2.0mm'
Add-Symbol Jumper SolderJumper_2_Open JP4 '154.94,119.38' 'ESP_B_LED_DISABLE' 'Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm'
Add-Symbol power PWR_FLAG '#FLG01' '76.2,73.66' 'PWR_FLAG'
Add-Symbol power PWR_FLAG '#FLG02' '88.9,116.84' 'PWR_FLAG'
Add-Symbol power PWR_FLAG '#FLG03' '114.3,78.74' 'PWR_FLAG'
Add-Symbol power PWR_FLAG '#FLG04' '83.82,38.1' 'PWR_FLAG'
Add-Symbol power PWR_FLAG '#FLG05' '121.92,29.21' 'PWR_FLAG'

# kicad-tool clones an existing same-library symbol when adding another
# instance. Explicitly clear inherited footprints on parts that require an
# exact holder, WSON land pattern, rated inductor, or derated capacitor MPN.
foreach ($ref in @('F1', 'U1', 'U2', 'L1', 'L2', 'C6', 'C20', 'C11', 'C22')) {
    & $tool sch edit symbol set-property $schematic $ref Footprint '' --format json | Out-Null
    Assert-NativeSuccess "clear provisional footprint $ref"
}

# Input and branch protection nets.
Add-Label 12V_IN '20.32,30.48'
Add-Label GND '20.32,33.02'
Add-Label 12V_IN '40.64,24.13'
Add-Label 12V_FUSED '40.64,31.75'
Add-Label Q1_GATE '50.8,27.94'
Add-Label 12V_PROTECTED '58.42,33.02'
Add-Label 12V_FUSED '58.42,22.86'
Add-Label 12V_PROTECTED '52.07,40.64'
Add-Label Q1_GATE '59.69,40.64'
Add-Label Q1_GATE '48.26,38.1'
Add-Label GND '48.26,43.18'
Add-Label 12V_PROTECTED '64.77,40.64'
Add-Label GND '72.39,40.64'
Add-Label 12V_PROTECTED '76.2,38.1'
Add-Label GND '76.2,43.18'
Add-Label 12V_PROTECTED '83.82,38.1'
Add-Label GND '83.82,43.18'
Add-Label 12V_PROTECTED '96.52,21.59'
Add-Label 12V_FAN_A '96.52,29.21'
Add-Label 12V_PROTECTED '109.22,21.59'
Add-Label 12V_FAN_B '109.22,29.21'
Add-Label 12V_PROTECTED '121.92,21.59'
Add-Label 12V_MQ_BRANCH '121.92,29.21'
Add-Label 5V_MQ '109.22,135.89'
Add-Label 5V_MQ2 '109.22,143.51'
Add-Label 5V_MQ '121.92,135.89'
Add-Label 5V_MQ4 '121.92,143.51'
Add-Label 5V_MQ '134.62,135.89'
Add-Label 5V_MQ7 '134.62,143.51'
Add-Label 5V_LOGIC '109.22,87.63'
Add-Label 5V_WS '109.22,95.25'
Add-Label 5V_LOGIC '121.92,87.63'
Add-Label 5V_SENSORS '121.92,95.25'
Add-Label 5V_LOGIC '134.62,87.63'
Add-Label 5V_RELAY '134.62,95.25'

# LMR51450 pin map: 1-3 SW, 4 BOOT, 5 PG, 6 RT, 7 FB, 8 AGND,
# 9 EN, 10-12 VIN, 13 PGND/DAP. PG/RT intentionally left open (440 kHz).
foreach ($p in @('45.72,68.58','58.42,68.58','45.72,71.12')) { Add-Label SW_LOGIC $p }
Add-Label BOOT_LOGIC '58.42,71.12'
Add-Label FB_LOGIC '45.72,76.2'
Add-Label GND '58.42,76.2'
Add-Label 12V_PROTECTED '45.72,78.74'
foreach ($p in @('58.42,78.74','45.72,81.28','58.42,81.28')) { Add-Label 12V_PROTECTED $p }
Add-Label GND '45.72,83.82'
Add-Label SW_LOGIC '76.2,68.58'
Add-Label 5V_LOGIC '76.2,73.66'
Add-Label 12V_PROTECTED '35.56,66.04'
Add-Label GND '35.56,71.12'
Add-Label 12V_PROTECTED '27.94,66.04'
Add-Label GND '27.94,71.12'
Add-Label 12V_PROTECTED '35.56,73.66'
Add-Label GND '35.56,78.74'
Add-Label BOOT_LOGIC '63.5,60.96'
Add-Label SW_LOGIC '63.5,66.04'
Add-Label 5V_LOGIC '88.9,73.66'
Add-Label GND '88.9,78.74'
Add-Label 5V_LOGIC '96.52,73.66'
Add-Label GND '96.52,78.74'
Add-Label 5V_LOGIC '83.82,81.28'
Add-Label FB_LOGIC '83.82,86.36'
Add-Label FB_LOGIC '83.82,88.9'
Add-Label GND '83.82,93.98'
Add-Label 5V_LOGIC '91.44,81.28'
Add-Label FB_FF_LOGIC '91.44,86.36'
Add-Label FB_FF_LOGIC '71.12,88.9'
Add-Label FB_LOGIC '71.12,93.98'

foreach ($p in @('45.72,111.76','58.42,111.76','45.72,114.3')) { Add-Label SW_MQ $p }
Add-Label BOOT_MQ '58.42,114.3'
Add-Label FB_MQ '45.72,119.38'
Add-Label GND '58.42,119.38'
Add-Label 12V_MQ_BRANCH '45.72,121.92'
foreach ($p in @('58.42,121.92','45.72,124.46','58.42,124.46')) { Add-Label 12V_MQ_BRANCH $p }
Add-Label GND '45.72,127'
Add-Label SW_MQ '76.2,111.76'
Add-Label 5V_MQ '76.2,116.84'
Add-Label 12V_MQ_BRANCH '35.56,109.22'
Add-Label GND '35.56,114.3'
Add-Label 12V_MQ_BRANCH '27.94,109.22'
Add-Label GND '27.94,114.3'
Add-Label 12V_MQ_BRANCH '35.56,116.84'
Add-Label GND '35.56,121.92'
Add-Label BOOT_MQ '63.5,104.14'
Add-Label SW_MQ '63.5,109.22'
Add-Label 5V_MQ '88.9,116.84'
Add-Label GND '88.9,121.92'
Add-Label 5V_MQ '96.52,116.84'
Add-Label GND '96.52,121.92'
Add-Label 5V_MQ '83.82,124.46'
Add-Label FB_MQ '83.82,129.54'
Add-Label FB_MQ '83.82,132.08'
Add-Label GND '83.82,137.16'
Add-Label 5V_MQ '91.44,124.46'
Add-Label FB_FF_MQ '91.44,129.54'
Add-Label FB_FF_MQ '71.12,132.08'
Add-Label FB_MQ '71.12,137.16'

# ESP-A independent 3.3 V branch.
Add-Label 5V_LOGIC '119.38,68.58'
Add-Label 5V_LOGIC '119.38,71.12'
Add-Label GND '127,78.74'
Add-Label ESP_A_RAW '134.62,68.58'
Add-Label 5V_LOGIC '114.3,73.66'
Add-Label GND '114.3,78.74'
Add-Label ESP_A_RAW '139.7,73.66'
Add-Label GND '139.7,78.74'
Add-Label ESP_A_RAW '147.32,73.66'
Add-Label GND '147.32,78.74'
Add-Label ESP_A_RAW '149.86,68.58'
Add-Label 3V3_ESP_A '160.02,68.58'
Add-Label 3V3_ESP_A '165.1,68.58'
Add-Label 3V3_ESP_A '149.86,76.2'
Add-Label ESP_A_LED_SUPPLY '160.02,76.2'

# ESP-B independent 3.3 V branch.
Add-Label 5V_LOGIC '119.38,111.76'
Add-Label 5V_LOGIC '119.38,114.3'
Add-Label GND '127,121.92'
Add-Label ESP_B_RAW '134.62,111.76'
Add-Label 5V_LOGIC '114.3,116.84'
Add-Label GND '114.3,121.92'
Add-Label ESP_B_RAW '139.7,116.84'
Add-Label GND '139.7,121.92'
Add-Label ESP_B_RAW '147.32,116.84'
Add-Label GND '147.32,121.92'
Add-Label ESP_B_RAW '149.86,111.76'
Add-Label 3V3_ESP_B '160.02,111.76'
Add-Label 3V3_ESP_B '165.1,111.76'
Add-Label 3V3_ESP_B '149.86,119.38'
Add-Label ESP_B_LED_SUPPLY '160.02,119.38'

if ($script:seedLabelUuid) {
    & $tool sch edit label delete $schematic $script:seedLabelUuid --format json | Out-Null
    Assert-NativeSuccess 'delete final seed label'
}

$symbols = (& $tool sch query list $schematic symbols --format json | ConvertFrom-Json).items
Assert-NativeSuccess 'query final symbols'
$labels = (& $tool sch query list $schematic labels --format json | ConvertFrom-Json).items
Assert-NativeSuccess 'query final labels'
if ($symbols.Count -ne 60) { throw "Expected 60 symbols, found $($symbols.Count)." }
if ($labels.Count -ne 131) { throw "Expected 131 labels, found $($labels.Count)." }

$buildDir = Join-Path $projectRoot 'build'
New-Item -ItemType Directory -Force $buildDir | Out-Null
$netlist = Join-Path $buildDir 'power.net'
& $env:KICAD_CLI sch export netlist -o $netlist $schematic
Assert-NativeSuccess 'KiCad power netlist export'
Write-Output "power schematic generated: 60 symbols, 131 labels, netlist=$netlist"
