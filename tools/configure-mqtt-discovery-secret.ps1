param(
    [Parameter(Mandatory = $true)]
    [string[]]$EspSecretsPaths,

    [Parameter(Mandatory = $true)]
    [string]$GatewayEnvPath
)

$ErrorActionPreference = 'Stop'

$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$key = [Convert]::ToHexString($bytes).ToLowerInvariant()

function Set-HeaderSecret([string]$Path, [string]$Secret) {
    $resolved = [System.IO.Path]::GetFullPath($Path)
    if (-not [System.IO.File]::Exists($resolved)) {
        throw "ESP secrets file does not exist: $resolved"
    }
    $text = [System.IO.File]::ReadAllText($resolved)
    $line = "#define DISCOVERY_HMAC_KEY `"$Secret`""
    if ($text -match '(?m)^\s*#define\s+DISCOVERY_HMAC_KEY\s+.*$') {
        $text = [regex]::Replace($text, '(?m)^\s*#define\s+DISCOVERY_HMAC_KEY\s+.*$', $line)
    } else {
        if (-not $text.EndsWith("`n")) { $text += "`r`n" }
        $text += "$line`r`n"
    }
    [System.IO.File]::WriteAllText($resolved, $text, [System.Text.UTF8Encoding]::new($false))
}

function Set-EnvironmentSecret([string]$Path, [string]$Secret) {
    $resolved = [System.IO.Path]::GetFullPath($Path)
    if (-not [System.IO.File]::Exists($resolved)) {
        throw "Gateway environment file does not exist: $resolved"
    }
    $text = [System.IO.File]::ReadAllText($resolved)
    $line = "MQTT_DISCOVERY_HMAC_KEY=$Secret"
    if ($text -match '(?m)^MQTT_DISCOVERY_HMAC_KEY=.*$') {
        $text = [regex]::Replace($text, '(?m)^MQTT_DISCOVERY_HMAC_KEY=.*$', $line)
    } else {
        if (-not $text.EndsWith("`n")) { $text += "`r`n" }
        $text += "$line`r`n"
    }
    [System.IO.File]::WriteAllText($resolved, $text, [System.Text.UTF8Encoding]::new($false))
}

foreach ($path in $EspSecretsPaths) {
    Set-HeaderSecret -Path $path -Secret $key
}
Set-EnvironmentSecret -Path $GatewayEnvPath -Secret $key

# Do not print the secret. Only report the paths that were updated.
Write-Output "Configured one shared MQTT discovery secret in $($EspSecretsPaths.Count) ESP file(s) and one gateway environment file."
