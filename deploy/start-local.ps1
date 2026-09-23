param([switch]$CheckOnly)

# Local development only: never installs packages, migrates, seeds or resets data.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot 'backend'
$frontendPath = Join-Path $projectRoot 'frontend'
$pythonPath = Join-Path $backendPath '.venv\Scripts\python.exe'
$daphnePath = Join-Path $backendPath '.venv\Scripts\daphne.exe'
$vitePath = Join-Path $frontendPath 'node_modules\vite\bin\vite.js'
$logPath = Join-Path $projectRoot '.runtime'
$apiProcess = $null
$webProcess = $null

function Read-Service([string]$Url) {
    try { return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 } catch { return $null }
}
function Test-Port([int]$Port) {
    $socket = [Net.Sockets.TcpClient]::new()
    try { return $socket.ConnectAsync('127.0.0.1', $Port).Wait(500) -and $socket.Connected }
    catch { return $false }
    finally { $socket.Dispose() }
}
function Test-Backend {
    $response = Read-Service 'http://127.0.0.1:8000/api/ready/'
    if (!$response) { return $false }
    try {
        $health = $response.Content | ConvertFrom-Json
        return $health.service -eq 'utility-tunnel-django' -and $health.status -eq 'ready'
    } catch { return $false }
}
function Test-Frontend {
    $response = Read-Service 'http://127.0.0.1:5173/'
    return $response -and $response.Content -match '/src/main.ts'
}

if ($env:DJANGO_ENV -eq 'production') { throw 'This launcher is for local development, not production.' }
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Missing backend/.venv. Follow README environment setup first.' }
if (!(Test-Path -LiteralPath $daphnePath)) { throw 'Missing backend/.venv daphne executable. Install the locked backend dependencies first.' }
if (!(Test-Path -LiteralPath $vitePath)) { throw 'Missing frontend dependencies. Run npm ci in frontend first.' }
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
# Check the effective settings too: production may be configured in backend/.env.
Push-Location $backendPath
try {
    & $pythonPath -c "from config.settings import DJANGO_ENV; raise SystemExit(0 if DJANGO_ENV == 'development' else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Effective Django environment is not development, or settings could not load.' }
} finally { Pop-Location }
$backendReady = Test-Backend
$frontendReady = Test-Frontend
if (!$backendReady -and (Test-Port 8000)) { throw 'Port 8000 is occupied or API is not ready. Inspect the existing service; it was not stopped.' }
if (!$frontendReady -and (Test-Port 5173)) { throw 'Port 5173 is occupied by an unrecognized service. It was not stopped.' }
Write-Output "Backend ready: $backendReady; frontend ready: $frontendReady"
if ($CheckOnly) { return }

if (!$backendReady) {
    Push-Location $backendPath
    try {
        & $pythonPath manage.py check
        if ($LASTEXITCODE -ne 0) { throw 'Django configuration check failed.' }
        & $pythonPath manage.py migrate --check
        if ($LASTEXITCODE -ne 0) { throw 'Pending migrations. Review and apply them manually before starting.' }
    } finally { Pop-Location }
}
New-Item -ItemType Directory -Path $logPath -Force | Out-Null
$runStamp = [Guid]::NewGuid().ToString('N')
if (!$backendReady) {
    $apiProcess = Start-Process -FilePath $daphnePath -ArgumentList @('-b', '127.0.0.1', '-p', '8000', 'config.asgi:application') -WorkingDirectory $backendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logPath "$runStamp-api.out.log") -RedirectStandardError (Join-Path $logPath "$runStamp-api.err.log")
    Write-Output "Started ASGI API (Daphne) PID $($apiProcess.Id)"
}
if (!$frontendReady) {
    $viteArguments = '"' + $vitePath + '" --host 127.0.0.1 --port 5173 --strictPort'
    $webProcess = Start-Process -FilePath $nodePath -ArgumentList $viteArguments -WorkingDirectory $frontendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logPath "$runStamp-web.out.log") -RedirectStandardError (Join-Path $logPath "$runStamp-web.err.log")
    Write-Output "Started frontend PID $($webProcess.Id)"
}
$deadline = [DateTime]::UtcNow.AddSeconds(40)
do {
    if ($apiProcess -and $apiProcess.HasExited) { throw "API exited before becoming ready. Inspect $logPath." }
    if ($webProcess -and $webProcess.HasExited) { throw "Frontend exited before becoming ready. Inspect $logPath." }
    $backendReady = Test-Backend
    $frontendReady = Test-Frontend
    if ($backendReady -and $frontendReady) {
        Write-Output 'Ready: http://127.0.0.1:5173/ (API: http://127.0.0.1:8000/api)'
        return
    }
    Start-Sleep -Milliseconds 500
} while ([DateTime]::UtcNow -lt $deadline)
throw "Services did not become ready. Inspect logs in $logPath. No existing processes or data were removed."
