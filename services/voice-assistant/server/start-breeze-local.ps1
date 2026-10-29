[CmdletBinding()]
param(
    [string]$BreezeRoot = 'D:\ut-voice\breeze-tts2',
    [string]$VoiceVenv = 'D:\ut-voice\voice-server-venv',
    [switch]$CheckOnly,
    [switch]$VerifyModelHash,
    [switch]$Cpu
)
$ErrorActionPreference = 'Stop'
$voicePython = Join-Path $VoiceVenv 'Scripts\python.exe'
$voiceRunner = Join-Path $PSScriptRoot 'run_breeze_local.py'
if (-not (Test-Path -LiteralPath $voicePython -PathType Leaf)) {
    throw 'The independent voice Python environment is unavailable.'
}
$voiceArguments = @('-B', $voiceRunner, '--breeze-root', $BreezeRoot,
    '--preferred-manifest', (Join-Path $PSScriptRoot 'preferred-voice.json'))
if ($CheckOnly) { $voiceArguments += '--check-only' }
if ($VerifyModelHash) { $voiceArguments += '--verify-model-hash' }
if ($Cpu) { $voiceArguments += '--cpu' }
# Direct argument-array invocation, no shell-built command or global PATH edit.
# The runner owns one hidden child and stops only that child on Ctrl+C/exit.
& $voicePython @voiceArguments
exit $LASTEXITCODE
