param([string]$PythonPath = 'python', [string]$NodePath = 'node')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runtimeRoot = Join-Path $projectRoot '.hardware-live'
$processFile = Join-Path $runtimeRoot 'processes.json'
$PythonPath = (Get-Command $PythonPath -ErrorAction Stop).Source
$NodePath = (Get-Command $NodePath -ErrorAction Stop).Source
$ready = Invoke-RestMethod 'http://127.0.0.1:8000/api/ready/' -TimeoutSec 3
if ($ready.profile -ne 'hardware-live') { throw 'This test is restricted to the isolated hardware profile.' }
$reportRoot = Join-Path $runtimeRoot ('transport-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $reportRoot | Out-Null
function Restart-Bridge([string]$Ids) {
    $entries = @(Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json)
    $matches = @($entries | Where-Object {$_.name -eq 'bridge'})
    if ($matches.Count -ne 1) { throw 'Expected exactly one managed bridge.' }
    $entry = $matches[0]
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if (!$process -or [Math]::Abs(($process.StartTime.ToUniversalTime() - ([DateTimeOffset]$entry.startedAtUtc).UtcDateTime).TotalSeconds) -ge 1) {
        throw 'Recorded bridge process no longer matches; no unrelated process was stopped.'
    }
    Stop-Process -Id $process.Id
    $privateConfig = @{}
    foreach ($line in (Get-Content -LiteralPath (Join-Path $runtimeRoot '.env'))) {
        $pair = $line.Split('=',2)
        if ($pair.Count -eq 2) { $privateConfig[$pair[0]] = $pair[1] }
    }
    $privateConfig['LOCAL_DEVICE_IDS'] = $Ids
    $privateConfig['DOTENV_CONFIG_PATH'] = Join-Path $runtimeRoot '.env'
    $saved = @{}
    try {
        foreach ($name in $privateConfig.Keys) {
            $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            [Environment]::SetEnvironmentVariable($name, $privateConfig[$name], 'Process')
        }
        $stamp = [Guid]::NewGuid().ToString('N')
        $child = Start-Process -FilePath $NodePath -ArgumentList 'src\index.js' -WorkingDirectory (Join-Path $projectRoot 'services\iotda-gateway') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeRoot "$stamp-bridge.out.log") -RedirectStandardError (Join-Path $runtimeRoot "$stamp-bridge.err.log")
        $entry.pid = $child.Id
        $entry.startedAtUtc = $child.StartTime.ToUniversalTime().ToString('o')
        $entries | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding utf8
    } finally {
        foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    }
}
function Verify([string]$Name, [string[]]$Extra = @()) {
    $arguments = @((Join-Path $PSScriptRoot 'verify_ingestion.py'), '--seconds', '6') + $Extra
    & $PythonPath @arguments | Set-Content -LiteralPath (Join-Path $reportRoot "$Name.json") -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "Transport verification failed at $Name." }
}
Verify 'before'
try {
    Restart-Bridge 'CTRL-01,CTRL-02,CTRL-04'
    Start-Sleep -Seconds 20
    Verify 'ctrl03-forwarding-paused' @('--expect-offline', 'CTRL-03')
} finally {
    Restart-Bridge 'CTRL-01,CTRL-02,CTRL-03,CTRL-04'
}
Start-Sleep -Seconds 5
Verify 'restored'
@{mode='real_hardware_transport_fault_injection'; pausedController='CTRL-03';
    hardwareCommands=0; modelCalls=0; allFourSubscriptionsRestored=$true;
    boundary='Only the local CTRL-03 forwarding subscription was paused. This is not physical RS485 disconnection acceptance.'} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $reportRoot 'summary.json') -Encoding utf8
Write-Output "Transport interruption/recovery verification: $reportRoot"
