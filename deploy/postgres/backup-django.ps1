param(
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'backups')
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) { throw 'DATABASE_URL is required; provide it through the environment or parameter.' }
if ($DatabaseUrl -notmatch '^postgres(ql)?://') { throw 'DATABASE_URL must use PostgreSQL.' }

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupFile = Join-Path $OutputDirectory "utility-tunnel-django-$stamp.backup"
& pg_dump --format=custom --no-owner --no-privileges --file $backupFile $DatabaseUrl
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE." }

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $backupFile).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$backupFile.sha256" -Value "$hash  $(Split-Path -Leaf $backupFile)" -Encoding ascii
Write-Output "Backup created: $backupFile"
Write-Output "SHA256: $hash"
