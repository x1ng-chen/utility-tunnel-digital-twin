param(
    [string]$RuntimeRoot = 'D:\shixi\utility-tunnel-runtime\anyjev',
    [int]$Port = 8110
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$runtime = [IO.Path]::GetFullPath($RuntimeRoot)
$python = Join-Path $runtime 'venv\Scripts\python.exe'
$tokenFile = Join-Path $runtime 'service-token.txt'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $tokenFile)) { throw '请先执行install.ps1。' }
$pidFile = Join-Path $runtime 'service-process.json'
if (Test-Path -LiteralPath $pidFile) {
    $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    if (Get-Process -Id $record.pid -ErrorAction SilentlyContinue) { throw 'PID记录仍有进程，请先检查health或使用stop.ps1。' }
}
$lock = Get-Content -LiteralPath (Join-Path $projectRoot 'services\decision-router\model.lock.json') -Raw | ConvertFrom-Json
$modelDir = Join-Path $runtime ('models\Tacit-1.7B\' + $lock.modelRevision)
$service = Join-Path $projectRoot 'services\decision-router\router_service.py'
$env:ANYJEV_TOKEN = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$arguments = @('"' + $service + '"', '--model-dir', '"' + $modelDir + '"', '--port', "$Port")
$process = Start-Process -FilePath $python -ArgumentList $arguments -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtime 'service.stdout.log') -RedirectStandardError (Join-Path $runtime 'service.stderr.log')
$record = [pscustomobject]@{pid=$process.Id;startTimeUtc=$process.StartTime.ToUniversalTime().ToString('o');startTimeTicks=$process.StartTime.ToUniversalTime().Ticks;service=$service;port=$Port}
$record | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
Write-Output ('模型预加载中，进程ID ' + $process.Id + '；health地址 http://127.0.0.1:' + $Port + '/health')
Write-Output '服务没有自动启用Django路由；请按README配置服务端ANYJEV_ENABLED、ANYJEV_URL和ANYJEV_TOKEN。'
