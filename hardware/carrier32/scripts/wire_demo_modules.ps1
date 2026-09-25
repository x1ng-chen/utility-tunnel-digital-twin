$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$schematic = Join-Path $projectRoot 'carrier32.kicad_sch'
$tool = Join-Path $projectRoot '.venv/Scripts/kicad-tool.exe'
$contract = @(Import-Csv (Join-Path $projectRoot 'config/connector-contract.csv'))
$env:KICAD_CLI = 'D:/KiCad/bin/kicad-cli.exe'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$culture = [System.Globalization.CultureInfo]::InvariantCulture

function Invoke-Tool([string[]]$toolArgs) {
    & $tool @toolArgs --format json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "kicad-tool failed: $($toolArgs -join ' ')" }
}
function Add-PinLabel([object]$symbol, [int]$number, [string]$name) {
    $pin = @($symbol.pins | Where-Object { $_.number -eq [string]$number })
    if ($pin.Count -ne 1) { throw "Pin $number not found on $($symbol.ref)" }
    $x = [double]$pin[0].absolute.x
    $y = [double]$pin[0].absolute.y
    $xy = '{0},{1}' -f $x.ToString('0.####',$culture),$y.ToString('0.####',$culture)
    $key = "$name|$xy"
    if ($script:knownLabels.Contains($key)) { return }
    $rotation = if ($x -lt $symbol.at.x) {'180'} else {'0'}
    Invoke-Tool @('sch','edit','label','add',$schematic,'local',$name,$xy,'--rotation',$rotation)
    [void]$script:knownLabels.Add($key)
}
function Add-PinNC([object]$symbol, [int]$number) {
    $pin = @($symbol.pins | Where-Object { $_.number -eq [string]$number })
    if ($pin.Count -ne 1) { throw "Pin $number not found on $($symbol.ref)" }
    $xy = '{0},{1}' -f ([double]$pin[0].absolute.x).ToString('0.####',$culture),([double]$pin[0].absolute.y).ToString('0.####',$culture)
    Invoke-Tool @('sch','edit','no-connect','add',$schematic,$xy)
}
function Get-Symbol([string]$ref) {
    $symbol = & $tool sch query symbol $schematic $ref --format json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or -not $symbol.found) { throw "Symbol missing: $ref" }
    return $symbol
}
function Label-Module([string]$ref,[string[]]$names) {
    $symbol = Get-Symbol $ref
    for ($i=0; $i -lt $names.Count; $i++) {
        if ($names[$i] -eq 'NC') { Add-PinNC $symbol ($i+1) }
        else { Add-PinLabel $symbol ($i+1) $names[$i] }
    }
    Write-Output "wired $ref ($($names.Count) pins)"
}

$script:knownLabels = [System.Collections.Generic.HashSet[string]]::new()
$labelList = & $tool sch query list $schematic labels --format json | ConvertFrom-Json
foreach ($label in $labelList.items) {
    $xy = '{0},{1}' -f ([double]$label.at.x).ToString('0.####',$culture),([double]$label.at.y).ToString('0.####',$culture)
    [void]$script:knownLabels.Add("$($label.text)|$xy")
}

foreach ($row in $contract) {
    if ($row.pin4 -eq 'NC') { Add-PinNC (Get-Symbol $row.board_ref) 4 }
}

$aSignals = @($contract | ForEach-Object { $_.pin3; if ($_.pin4 -ne 'NC') { $_.pin4 } } | Where-Object { $_ -like 'A_*' } | Sort-Object -Unique)
$bSignals = @($contract | ForEach-Object { $_.pin3; if ($_.pin4 -ne 'NC') { $_.pin4 } } | Where-Object { $_ -like 'B_*' } | Sort-Object -Unique)
$aExtra = @('GND','5V_LOGIC','3V3_SENSORS','A_ESP_TX','A_ESP_RX','A_TFT_SCK','A_TFT_MOSI','A_TFT_CS','A_TFT_DC','A_TFT_RST','A_JOY_X','A_JOY_Y','A_JOY_SW','A_WS_DATA','A_FAN_PWM','A_FAN_TACH','A_INA_SCL','A_INA_SDA','A_RELAY_CTRL','A_BUZZ_CTRL')
$bExtra = @('GND','5V_LOGIC','3V3_SENSORS','B_ESP_TX','B_ESP_RX','B_TFT_SCK','B_TFT_MOSI','B_TFT_CS','B_TFT_DC','B_TFT_RST','B_WS_DATA','B_FAN_PWM','B_FAN_TACH','B_INA_SCL','B_INA_SDA')
$aPins = @($aSignals) + $aExtra
$bPins = @($bSignals) + $bExtra + @('NC') * (40 - $bSignals.Count - $bExtra.Count)
if ($aPins.Count -ne 40 -or $bPins.Count -ne 40) { throw "Unexpected MCU pin counts: A=$($aPins.Count), B=$($bPins.Count)" }
Label-Module 'J_MCU_A' $aPins
Label-Module 'J_MCU_B' $bPins

Label-Module 'J_ESP_A' @('GND','3V3_ESP_A','A_ESP_TX','A_ESP_RX','3V3_ESP_A','3V3_ESP_A','3V3_ESP_A','3V3_ESP_A')
Label-Module 'J_ESP_B' @('GND','3V3_ESP_B','B_ESP_TX','B_ESP_RX','3V3_ESP_B','3V3_ESP_B','3V3_ESP_B','3V3_ESP_B')
Label-Module 'J_TFT_A' @('GND','3V3_SENSORS','A_TFT_SCK','A_TFT_MOSI','A_TFT_CS','A_TFT_DC','A_TFT_RST','3V3_SENSORS')
Label-Module 'J_TFT_B' @('GND','3V3_SENSORS','B_TFT_SCK','B_TFT_MOSI','B_TFT_CS','B_TFT_DC','B_TFT_RST','3V3_SENSORS')
Label-Module 'J_JOY' @('GND','3V3_SENSORS','A_JOY_X','A_JOY_Y','A_JOY_SW')
Label-Module 'J_FAN_A' @('GND','12V_FAN_A','A_FAN_TACH','A_FAN_PWM')
Label-Module 'J_FAN_B' @('GND','12V_FAN_B','B_FAN_TACH','B_FAN_PWM')
Label-Module 'J_INA_A' @('GND','3V3_SENSORS','A_INA_SCL','A_INA_SDA','12V_PROTECTED','12V_FAN_A')
Label-Module 'J_INA_B' @('GND','3V3_SENSORS','B_INA_SCL','B_INA_SDA','12V_PROTECTED','12V_FAN_B')
Label-Module 'J_RELAY' @('GND','5V_RELAY','A_RELAY_CTRL')
Label-Module 'J_BUZZER' @('GND','A_BUZZ_CTRL')

for ($i=1; $i -le 18; $i++) {
    $ref = 'D_WS{0:00}' -f $i
    $symbol = Get-Symbol $ref
    Add-PinLabel $symbol 1 '5V_WS'
    Add-PinLabel $symbol 3 'GND'
    if ($i -eq 1) { Add-PinLabel $symbol 4 'A_WS_DATA' }
    elseif ($i -eq 10) { Add-PinLabel $symbol 4 'B_WS_DATA' }
    else { Add-PinLabel $symbol 4 ('WS_LINK_{0:00}' -f ($i-1)) }
    if ($i -eq 9 -or $i -eq 18) { Add-PinNC $symbol 2 }
    else { Add-PinLabel $symbol 2 ('WS_LINK_{0:00}' -f $i) }
}
Write-Output 'Demo-module pin labels and no-connect markers complete'
