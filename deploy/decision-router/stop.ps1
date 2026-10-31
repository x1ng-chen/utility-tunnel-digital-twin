param([string]$RuntimeRoot = 'D:\shixi\utility-tunnel-runtime\anyjev')
$ErrorActionPreference = 'Stop'
$runtime = [IO.Path]::GetFullPath($RuntimeRoot)
$pidFile = Join-Path $runtime 'service-process.json'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output '没有本服务进程记录。'; exit 0 }
$record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
$process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
if (-not $process) { Write-Output '记录中的服务已经退出。'; exit 0 }
$details = Get-CimInstance Win32_Process -Filter ('ProcessId=' + [int]$record.pid)
$recordedTicks = if ($record.startTimeTicks) { [long]$record.startTimeTicks } else { ([datetime]$record.startTimeUtc).ToUniversalTime().Ticks }
if ($process.StartTime.ToUniversalTime().Ticks -ne $recordedTicks -or
    -not $details.CommandLine.Contains($record.service)) { throw 'PID身份不匹配，拒绝停止其他进程。' }
Stop-Process -Id $process.Id
Write-Output '已停止本地决策服务；其他项目进程未处理。'
