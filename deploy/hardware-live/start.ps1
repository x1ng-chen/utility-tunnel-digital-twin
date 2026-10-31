param(
    [string]$PythonPath = 'python',
    [string]$NodePath = 'node',
    [string]$MqttUrl = 'mqtt://127.0.0.1:1884',
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runtimeRoot = Join-Path $projectRoot '.hardware-live'
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$bridgeRoot = Join-Path $projectRoot 'services\iotda-gateway'
$PythonPath = (Get-Command $PythonPath -ErrorAction Stop).Source
$NodePath = (Get-Command $NodePath -ErrorAction Stop).Source
function Invoke-Python([string[]]$Arguments) {
    & $PythonPath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python operation failed: $($Arguments[0])" }
}
function Read-Ready {
    try { return (Invoke-RestMethod 'http://127.0.0.1:8000/api/ready/' -TimeoutSec 2) }
    catch { return $null }
}
$ready = Read-Ready
if ($ready -and $ready.profile -ne 'hardware-live') { throw 'Port 8000 belongs to another profile; it was not stopped.' }
if (!$ready -and (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)) {
    throw 'Port 8000 is occupied by an unrecognized service.'
}
if (Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue) {
    throw 'Port 5173 is occupied; inspect the existing frontend before starting this profile.'
}
if ($ready) { throw 'Hardware profile is already running. Use its current page; do not launch duplicate bridge processes.' }
Invoke-Python @('-c', 'import django,daphne,dotenv; print("Python dependencies ready")')
if (!(Test-Path (Join-Path $frontendRoot 'node_modules\vite\bin\vite.js')) -or !(Test-Path (Join-Path $bridgeRoot 'node_modules\mqtt'))) {
    throw 'Install locked frontend/gateway dependencies before starting.'
}
Invoke-Python @((Join-Path $PSScriptRoot 'prepare_runtime.py'), '--mqtt-url', $MqttUrl)
$savedEnv = @{}
$privateConfig = @{}
foreach ($line in (Get-Content -LiteralPath (Join-Path $runtimeRoot '.env'))) {
    $pair = $line.Split('=', 2)
    if ($pair.Count -eq 2) { $privateConfig[$pair[0]] = $pair[1] }
}
foreach ($name in (@('DJANGO_SETTINGS_MODULE','DOTENV_CONFIG_PATH','VITE_API_BASE_URL') + @($privateConfig.Keys))) {
    $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    foreach ($name in $privateConfig.Keys) { [Environment]::SetEnvironmentVariable($name, $privateConfig[$name], 'Process') }
    $env:DJANGO_SETTINGS_MODULE = 'config.hardware_live_settings'
    $env:DOTENV_CONFIG_PATH = Join-Path $runtimeRoot '.env'
    $env:VITE_API_BASE_URL = 'http://127.0.0.1:8000/api'
    Push-Location $backendRoot
    try {
        Invoke-Python @('manage.py', 'check')
        Invoke-Python @('manage.py', 'migrate', '--noinput')
        Invoke-Python @('manage.py', 'prepare_hardware_live', '--install-model')
    } finally { Pop-Location }
    if ($PrepareOnly) { return }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $started = @()
    $specs = @(
        @{name='api'; file=$PythonPath; arguments='-m daphne -b 127.0.0.1 -p 8000 config.asgi:application'; cwd=$backendRoot},
        @{name='frontend'; file=$NodePath; arguments='node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5173 --strictPort'; cwd=$frontendRoot},
        @{name='bridge'; file=$NodePath; arguments='src\index.js'; cwd=$bridgeRoot},
        @{name='connectivity'; file=$PythonPath; arguments='manage.py run_connectivity_monitor'; cwd=$backendRoot}
    )
    foreach ($spec in $specs) {
        $process = Start-Process -FilePath $spec.file -ArgumentList $spec.arguments -WorkingDirectory $spec.cwd -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeRoot "$stamp-$($spec.name).out.log") -RedirectStandardError (Join-Path $runtimeRoot "$stamp-$($spec.name).err.log")
        $started += @{name=$spec.name; pid=$process.Id; startedAtUtc=$process.StartTime.ToUniversalTime().ToString('o')}
    }
    $started | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'processes.json') -Encoding utf8
    $deadline = [DateTime]::UtcNow.AddSeconds(35)
    do {
        $state = Read-Ready
        $webReady = $false
        try { $webReady = (Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 2).Content -match '/src/main.ts' } catch {}
        if ($state -and $state.profile -eq 'hardware-live' -and $webReady) {
            Write-Output 'Hardware telemetry page: http://127.0.0.1:5173/telemetry'
            Write-Output "Local account file: $(Join-Path $runtimeRoot 'access.json')"
            return
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'API readiness timeout; inspect .hardware-live logs. Existing services and databases were not removed.'
} finally {
    foreach ($name in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process') }
}
