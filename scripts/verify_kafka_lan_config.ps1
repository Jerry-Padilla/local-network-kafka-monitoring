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
$config = docker compose -f $ComposeFile config 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    throw "docker compose config failed:`n$config"
}

$required = @(
    "EXTERNAL://${ExpectedHost}:${ExpectedPort}",
    "0.0.0.0:${ExpectedPort}:29092",
    "PLAINTEXT://kafka:9092"
)
$forbidden = @(
    "EXTERNAL://localhost:${ExpectedPort}",
    "127.0.0.1:${ExpectedPort}:29092"
)

foreach ($value in $required) {
    if (-not $config.Contains($value)) {
        throw "Compose configuration is missing required value: $value"
    }
}
foreach ($value in $forbidden) {
    if ($config.Contains($value)) {
        throw "Compose configuration contains forbidden value: $value"
    }
}

Write-Output "Kafka LAN listener configuration is valid for ${ExpectedHost}:${ExpectedPort}."
