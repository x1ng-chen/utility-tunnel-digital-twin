param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$schematic = Join-Path $projectRoot 'carrier32.kicad_sch'
$tool = Join-Path $projectRoot '.venv/Scripts/kicad-tool.exe'
$env:KICAD_CLI = 'D:/KiCad/bin/kicad-cli.exe'
$env:PYTHONUTF8 = '1'

$modules = @(
    @('J_MCU_A','Connector_Generic:Conn_02x20_Odd_Even','STM32F103RCT6-A','Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical',250,70),
    @('J_MCU_B','Connector_Generic:Conn_02x20_Odd_Even','STM32F103RCT6-B','Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical',345,70),
    @('J_ESP_A','Connector_Generic:Conn_02x04_Odd_Even','ESP-01S-A','Connector_PinSocket_2.54mm:PinSocket_2x04_P2.54mm_Vertical',235,127),
    @('J_ESP_B','Connector_Generic:Conn_02x04_Odd_Even','ESP-01S-B','Connector_PinSocket_2.54mm:PinSocket_2x04_P2.54mm_Vertical',280,127),
    @('J_TFT_A','Connector_Generic:Conn_01x08','ST7735S-A','Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical',330,127),
    @('J_TFT_B','Connector_Generic:Conn_01x08','ST7735S-B','Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical',385,127),
    @('J_JOY','Connector_Generic:Conn_01x05','JOYSTICK-B','Connector_PinSocket_2.54mm:PinSocket_1x05_P2.54mm_Vertical',225,170),
    @('J_FAN_A','Connector_Generic:Conn_01x04','FAN-A-12V-0.2A','Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical',260,170),
    @('J_FAN_B','Connector_Generic:Conn_01x04','FAN-B-12V-0.2A','Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical',290,170),
    @('J_INA_A','Connector_Generic:Conn_01x06','INA226-A','Connector_PinSocket_2.54mm:PinSocket_1x06_P2.54mm_Vertical',320,170),
    @('J_INA_B','Connector_Generic:Conn_01x06','INA226-B','Connector_PinSocket_2.54mm:PinSocket_1x06_P2.54mm_Vertical',350,170),
    @('J_RELAY','Connector_Generic:Conn_01x03','RELAY','Connector_PinSocket_2.54mm:PinSocket_1x03_P2.54mm_Vertical',380,170),
    @('J_BUZZER','Connector_Generic:Conn_01x02','BUZZER','Connector_PinSocket_2.54mm:PinSocket_1x02_P2.54mm_Vertical',405,170)
)
for ($i = 1; $i -le 18; $i++) {
    $ref = 'D_WS{0:00}' -f $i
    $x = 220 + 22 * (($i - 1) % 9)
    $y = 220 + 22 * [math]::Floor(($i - 1) / 9)
    $modules += ,@($ref,'LED:WS2812B',('WS2812-{0:00}' -f $i),'LED_SMD:LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm',$x,$y)
}

foreach ($module in $modules) {
    $ref,$lib,$value,$footprint,$x,$y = $module
    $existing = & $tool sch query symbol $schematic $ref --format json 2>$null
    if ($LASTEXITCODE -eq 0) { continue }
    $libFile = if ($lib.StartsWith('LED:')) {'D:/KiCad/share/kicad/symbols/LED.kicad_sym'} else {'D:/KiCad/share/kicad/symbols/Connector_Generic.kicad_sym'}
    $addArgs = @('sch','edit','symbol','add',$schematic,$lib,$ref,($x.ToString()+','+$y.ToString()),'--lib-file',$libFile)
    & $tool @addArgs --dry-run --format json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Dry-run add failed: $ref" }
    if ($DryRun) { Write-Output "would add $ref"; continue }
    & $tool @addArgs --format json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Add failed: $ref" }
    foreach ($entry in @(@('Value',$value),@('Footprint',$footprint))) {
        & $tool sch edit symbol set-property $schematic $ref $entry[0] $entry[1] --format json | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Property failed: $ref $($entry[0])" }
    }
    Write-Output "added $ref"
}
Write-Output "Demo modules processed: $($modules.Count)"
