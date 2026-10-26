# Flash the RS-485 diagnostic firmware to the STM32 board with the given number via ST-Link (SWD).
# Usage:
#   powershell -ExecutionPolicy Bypass -File firmware/rs485-bench/flash-stlink.ps1 -Board 1
# Check the connection only, without writing:
#   powershell -ExecutionPolicy Bypass -File firmware/rs485-bench/flash-stlink.ps1 -Board 1 -CheckOnly

param(
    [Parameter(Mandatory = $true)][ValidateSet(1, 2, 3, 4)][int]$Board,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ocd = Join-Path $env:USERPROFILE ".platformio\packages\tool-openocd\bin\openocd.exe"
$scripts = Join-Path $env:USERPROFILE ".platformio\packages\tool-openocd\openocd\scripts"
$image = Join-Path $root ("build\rs485-{0}\rs485_ctrl0{0}_bench.bin" -f $Board)
$backupDir = Join-Path $root "build\rs485-backup"
$backup = Join-Path $backupDir ("board{0}-before.bin" -f $Board)
$config = @("-s", $scripts, "-f", "interface/stlink.cfg", "-f", "target/stm32f1x.cfg")

if (-not (Test-Path $ocd)) { throw "OpenOCD not found: $ocd" }
if (-not (Test-Path $image)) { throw "Image not found: $image . Build it first from the repository root." }

Write-Host ""
Write-Host "===== Target board: $Board ====="
Write-Host ("Image : {0} ({1} bytes)" -f $image, (Get-Item $image).Length)
Write-Host ("SHA256: {0}" -f (Get-FileHash $image -Algorithm SHA256).Hash)
Write-Host "Probing target..."
& $ocd @config -c "init; flash probe 0; shutdown"
if ($LASTEXITCODE -ne 0) { throw "Cannot connect. Check SWDIO=PA13, SWCLK=PA14, GND and target power." }

if ($CheckOnly) {
    Write-Host "Connection check only; nothing written."
    exit 0
}

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
if (-not (Test-Path $backup)) {
    Write-Host "Backing up 256 KiB flash to $backup ..."
    & $ocd @config -c "init; dump_image `"$backup`" 0x08000000 0x40000; shutdown"
    if (-not (Test-Path $backup)) { throw "Backup failed; nothing written." }
    Write-Host ("Backup SHA256: {0}" -f (Get-FileHash $backup -Algorithm SHA256).Hash)
} else {
    Write-Host "Keeping existing backup: $backup"
}

$answer = Read-Host "Write the board $Board image to the connected target? Type YES to continue"
if ($answer -ne "YES") { Write-Host "Cancelled."; exit 1 }

Write-Host "Writing and verifying..."
& $ocd @config -c "program `"$image`" 0x08000000 verify reset exit"
if ($LASTEXITCODE -ne 0) { throw "Flash or verify failed." }

Write-Host ""
Write-Host "Done. On USART1 (PA9/PA10, 115200 8N1) you should see:"
Write-Host ("  RS485_BENCH_V1 CTRL-0{0} SLAVE={0} ..." -f $Board)
Write-Host ("  CTRL0{0}_BENCH selftest=PASS ..." -f $Board)
