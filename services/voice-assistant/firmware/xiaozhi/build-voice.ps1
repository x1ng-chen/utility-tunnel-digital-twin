param(
    [string]$FirmwarePath = 'D:\ut-voice\xiaozhi-esp32',
    [string]$ActivationScript = 'C:\Espressif\tools\Microsoft.ut-voice-idf-v6.0.1.PowerShell_profile.ps1',
    [ValidateSet('Online', 'Offline')]
    [string]$Mode = 'Online'
)

$ErrorActionPreference = 'Stop'
$voiceSource = [IO.Path]::GetFullPath($FirmwarePath)
if (-not (Test-Path -LiteralPath (Join-Path $voiceSource 'main\boards\utility-tunnel-s3\utility_tunnel_s3.cc'))) {
    throw 'Apply the pinned-source registration patch and board overlay first.'
}
if (-not (Test-Path -LiteralPath $ActivationScript)) {
    throw 'ESP-IDF activation script was not found. Pass -ActivationScript for this computer.'
}
$voiceAdapter = $PSScriptRoot
foreach ($voiceRelative in @('config.h', 'utility_tunnel_s3.cc', 'config.json', 'wake_ack.h', 'provisioning.h', 'provisioning.cc', 'ut_wake_ack.ogg', 'ut_stop_ack.ogg')) {
    $voiceExpected = Join-Path $voiceAdapter ('overlay\main\boards\utility-tunnel-s3\' + $voiceRelative)
    $voiceActual = Join-Path $voiceSource ('main\boards\utility-tunnel-s3\' + $voiceRelative)
    if ((Get-FileHash -LiteralPath $voiceExpected).Hash -ne (Get-FileHash -LiteralPath $voiceActual).Hash) {
        throw "Board overlay differs from the project: $voiceRelative. Review and copy the intended source before building."
    }
}
$voiceIsOffline = $Mode -eq 'Offline'
$voiceBuildDirectory = if ($voiceIsOffline) { 'build-utility-tunnel-offline' } else { 'build-utility-tunnel' }
$voiceGeneratedName = if ($voiceIsOffline) { 'sdkconfig.utility-tunnel.offline.generated' } else { 'sdkconfig.utility-tunnel.generated' }
$voiceFragmentName = if ($voiceIsOffline) { 'sdkconfig.utility-tunnel.offline' } else { 'sdkconfig.utility-tunnel.online' }
$voiceDefaultsName = if ($voiceIsOffline) { 'sdkconfig.voice.defaults' } else { 'sdkconfig.voice.online.defaults' }
$voiceGeneratedPath = Join-Path $voiceSource $voiceGeneratedName
if (Test-Path -LiteralPath $voiceGeneratedPath) {
    $voiceExistingOffline = [bool](Select-String -LiteralPath $voiceGeneratedPath -Pattern '^CONFIG_UTILITY_TUNNEL_OFFLINE_WAKE_TEST=y$' -Quiet)
    if ($voiceExistingOffline -ne $voiceIsOffline) {
        throw "Generated configuration does not match -Mode $Mode. Select a separate generated configuration; do not silently reuse the other mode."
    }
}
Copy-Item -LiteralPath (Join-Path $voiceAdapter $voiceDefaultsName) -Destination (Join-Path $voiceSource $voiceFragmentName)
. $ActivationScript
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
# Temporary override for the official China storage endpoint; no machine-wide setting.
$env:IDF_COMPONENT_STORAGE_URL = 'https://components-file.espressif.cn'
$env:IDF_COMPONENT_API_TIMEOUT = '60'
$voicePython = Join-Path $env:IDF_PYTHON_ENV_PATH 'Scripts\python.exe'
$voiceIdf = Join-Path $env:IDF_PATH 'tools\idf.py'
$voiceLogs = Join-Path (Split-Path -Path $voiceSource -Parent) 'logs'
[IO.Directory]::CreateDirectory($voiceLogs) | Out-Null
$voiceArgs = @(
    '-B', $voiceBuildDirectory,
    '-D', 'IDF_TARGET=esp32s3',
    '-D', ('SDKCONFIG=' + $voiceGeneratedName),
    '-D', ('SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.esp32s3;' + $voiceFragmentName),
    '-D', 'CMAKE_NINJA_FORCE_RESPONSE_FILE=ON'
)
Push-Location -LiteralPath $voiceSource
try {
    & $voicePython $voiceIdf --version
    if ($LASTEXITCODE -ne 0) { throw 'IDF version check failed.' }
    & $voicePython $voiceIdf @voiceArgs reconfigure 2>&1 |
        Tee-Object -FilePath (Join-Path $voiceLogs 'reconfigure.log')
    if ($LASTEXITCODE -ne 0) { throw 'Voice firmware reconfigure failed.' }
    $voiceActualOffline = [bool](Select-String -LiteralPath $voiceGeneratedPath -Pattern '^CONFIG_UTILITY_TUNNEL_OFFLINE_WAKE_TEST=y$' -Quiet)
    if ($voiceActualOffline -ne $voiceIsOffline) { throw 'Reconfigured mode differs from the requested mode.' }
    & $voicePython $voiceIdf @voiceArgs build 2>&1 |
        Tee-Object -FilePath (Join-Path $voiceLogs 'build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Voice firmware build failed.' }
} finally {
    Pop-Location
}
