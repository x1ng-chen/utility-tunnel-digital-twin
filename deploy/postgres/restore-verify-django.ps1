param(
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [Parameter(Mandatory = $true)][string]$TargetDatabaseUrl,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmRestore) { throw 'Restore is destructive. Re-run with -ConfirmRestore against an isolated verification database.' }
$resolvedBackup = Resolve-Path -LiteralPath $BackupFile -ErrorAction Stop
if (-not (Test-Path -LiteralPath $resolvedBackup -PathType Leaf)) { throw 'BackupFile must be a file.' }
if ($TargetDatabaseUrl -notmatch '^postgres(ql)?://') { throw 'TargetDatabaseUrl must use PostgreSQL.' }
$checksumFile = "$($resolvedBackup.Path).sha256"
if (Test-Path -LiteralPath $checksumFile -PathType Leaf) {
    $expectedHash = ((Get-Content -LiteralPath $checksumFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedBackup.Path).Hash.ToLowerInvariant()
    if ($expectedHash -ne $actualHash) { throw 'Backup SHA-256 checksum does not match the sidecar file.' }
}

& pg_restore --exit-on-error --clean --if-exists --no-owner --dbname $TargetDatabaseUrl $resolvedBackup.Path
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE." }
& psql --set=ON_ERROR_STOP=1 --dbname $TargetDatabaseUrl --command "SELECT COUNT(*) AS asset_count FROM operations_asset; SELECT COUNT(*) AS applied_migrations FROM django_migrations;"
if ($LASTEXITCODE -ne 0) { throw "Post-restore verification failed with exit code $LASTEXITCODE." }
Write-Output 'Restore verification completed. Keep this target isolated until application smoke tests pass.'
