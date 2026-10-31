$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$path = Join-Path $projectRoot '.hardware-live\processes.json'
if (!(Test-Path -LiteralPath $path)) { Write-Output 'No recorded hardware-profile processes.'; return }
foreach ($entry in (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json)) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if ($process -and [Math]::Abs(($process.StartTime.ToUniversalTime() - ([DateTimeOffset]$entry.startedAtUtc).UtcDateTime).TotalSeconds) -lt 1) {
        Stop-Process -Id $process.Id
        Write-Output "Stopped hardware profile $($entry.name)"
    }
}
