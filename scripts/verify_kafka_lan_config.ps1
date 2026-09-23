[CmdletBinding()]
param(
    [string]$ComposeFile = "docker-compose.yml",
    [string]$ExpectedHost = "192.168.1.198",
    [int]$ExpectedPort = 29092
)

$ErrorActionPreference = "Stop"

if (-not [System.Net.IPAddress]::TryParse($ExpectedHost, [ref]$null)) {
    throw "KAFKA_LAN_HOST must be a valid IPv4 address: $ExpectedHost"
}

$octets = $ExpectedHost.Split('.') | ForEach-Object { [int]$_ }
$isPrivate =
    $octets[0] -eq 10 -or
    ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
    ($octets[0] -eq 192 -and $octets[1] -eq 168)
if (-not $isPrivate) {
    throw "KAFKA_LAN_HOST must be an RFC1918 IPv4 address: $ExpectedHost"
}

$env:KAFKA_LAN_HOST = $ExpectedHost
$env:KAFKA_EXTERNAL_PORT = "$ExpectedPort"
$env:KAFKA_EXTERNAL_BIND_ADDRESS = "0.0.0.0"
$config = docker compose -f $ComposeFile config 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    throw "docker compose config failed:`n$config"
}

$requiredPatterns = @(
    [regex]::Escape("EXTERNAL://${ExpectedHost}:${ExpectedPort}"),
    "host_ip:\s+0\.0\.0\.0\s+target:\s+29092\s+published:\s+`"?$ExpectedPort`"?",
    [regex]::Escape("PLAINTEXT://kafka:9092")
)
$forbiddenPatterns = @(
    [regex]::Escape("EXTERNAL://localhost:${ExpectedPort}"),
    "host_ip:\s+127\.0\.0\.1\s+target:\s+29092"
)

foreach ($pattern in $requiredPatterns) {
    if ($config -notmatch $pattern) {
        throw "Compose configuration is missing required pattern: $pattern"
    }
}
foreach ($pattern in $forbiddenPatterns) {
    if ($config -match $pattern) {
        throw "Compose configuration contains forbidden pattern: $pattern"
    }
}

Write-Output "Kafka LAN listener configuration is valid for ${ExpectedHost}:${ExpectedPort}."
