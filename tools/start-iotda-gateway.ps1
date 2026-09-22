[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$serviceDirectory = Join-Path $projectRoot 'services\iotda-gateway'
$entryPoint = Join-Path $serviceDirectory 'src\index.js'
$environmentFile = Join-Path $serviceDirectory '.env'
$logDirectory = Join-Path $projectRoot '.runtime-logs'
$pidFile = Join-Path $logDirectory 'iotda-gateway.pid'

if (-not (Test-Path -LiteralPath $entryPoint)) {
    throw "IoTDA gateway entry point not found: $entryPoint"
}
if (-not (Test-Path -LiteralPath $environmentFile)) {
    throw "IoTDA gateway environment file not found: $environmentFile"
}

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

if (Test-Path -LiteralPath $pidFile) {
    $savedPid = 0
    if ([int]::TryParse((Get-Content -Raw -LiteralPath $pidFile).Trim(), [ref]$savedPid)) {
        $savedProcess = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($savedProcess -and $savedProcess.ProcessName -eq 'node') {
            exit 0
        }
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

$nodeCommand = Get-Command node.exe -ErrorAction Stop
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdoutLog = Join-Path $logDirectory "iotda-gateway-autostart-$timestamp.out.log"
$stderrLog = Join-Path $logDirectory "iotda-gateway-autostart-$timestamp.err.log"

$process = Start-Process `
    -FilePath $nodeCommand.Source `
    -ArgumentList @('src/index.js', '--utility-tunnel-autostart') `
    -WorkingDirectory $serviceDirectory `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii
Start-Sleep -Seconds 2

if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    $details = if (Test-Path -LiteralPath $stderrLog) {
        Get-Content -Raw -LiteralPath $stderrLog
    } else {
        'No stderr log was produced.'
    }
    throw "IoTDA gateway exited during startup. $details"
}
