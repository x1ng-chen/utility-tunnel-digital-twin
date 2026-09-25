param(
    [string[]]$Ports = @('COM3', 'COM6'),
    [ValidateRange(1, 3600)][int]$DurationSeconds = 20,
    [string]$OutputDirectory = 'artifacts/bench'
)

$ErrorActionPreference = 'Stop'
$target = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
[System.IO.Directory]::CreateDirectory($target) | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

$jobs = foreach ($portName in $Ports) {
    $path = Join-Path $target "$stamp-$portName-9600.log"
    Start-Job -ArgumentList $portName, $DurationSeconds, $path -ScriptBlock {
        param($name, $seconds, $logPath)
        $serial = [System.IO.Ports.SerialPort]::new($name, 9600, 'None', 8, 'One')
        $serial.DtrEnable = $false
        $serial.RtsEnable = $false
        $serial.ReadTimeout = 500
        $writer = [System.IO.StreamWriter]::new($logPath, $false, [System.Text.UTF8Encoding]::new($false))
        try {
            $serial.Open()
            $deadline = [DateTime]::UtcNow.AddSeconds($seconds)
            while ([DateTime]::UtcNow -lt $deadline) {
                try {
                    $line = $serial.ReadLine().TrimEnd("`r", "`n")
                    $writer.WriteLine(('{0:o} {1}' -f ([DateTimeOffset]::Now), $line))
                    $writer.Flush()
                } catch [System.TimeoutException] { }
            }
            "${name}: $logPath"
        } finally {
            if ($serial.IsOpen) { $serial.Close() }
            $serial.Dispose()
            $writer.Dispose()
        }
    }
}

$jobs | Wait-Job | Out-Null
$jobs | Receive-Job
$jobs | Remove-Job
