[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "setup", "lint", "format", "typecheck", "test", "test-unit",
        "test-integration", "up", "down", "reset", "logs", "demo", "verify",
        "kafka-topics", "db-shell", "config", "agent-build", "agent-validate",
        "agent-test", "stream-build", "stream-run", "stream-once", "stream-verify",
        "classifier-build", "classifier-run", "classifier-once", "classifier-verify",
        "analytics-build", "analytics-all", "analytics-verify"
    )]
    [string]$Command = "config"
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Compose = @("compose", "-f", (Join-Path $RepositoryRoot "docker-compose.yml"))

function Invoke-DockerCompose {
    param([string[]]$Arguments)
    & docker @Compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop and ensure 'docker' is on PATH."
}

switch ($Command) {
    "setup" {
        if (-not (Test-Path (Join-Path $RepositoryRoot ".env"))) {
            Copy-Item (Join-Path $RepositoryRoot ".env.example") (Join-Path $RepositoryRoot ".env")
            Write-Host "Created .env from safe local defaults. Change its passwords before shared use."
        }
        Invoke-DockerCompose @("build")
    }
    "lint" {
        Invoke-DockerCompose @("--profile", "test", "run", "--rm", "--entrypoint", "ruff", "tests", "check", ".")
    }
    "format" {
        Invoke-DockerCompose @("--profile", "test", "run", "--rm", "--entrypoint", "ruff", "tests", "format", ".")
    }
    "typecheck" {
        Invoke-DockerCompose @("--profile", "test", "run", "--rm", "--entrypoint", "mypy", "tests")
    }
    "test" {
        Invoke-DockerCompose @("--profile", "test", "run", "--rm", "tests", "-p", "no:cacheprovider", "-m", "not integration", "--cov", "--cov-report=term-missing")
    }
    "test-unit" {
        Invoke-DockerCompose @("--profile", "test", "run", "--rm", "tests", "-p", "no:cacheprovider", "-m", "not integration")
    }
    "test-integration" {
        Invoke-DockerCompose @("up", "-d", "--wait", "event-ingestor")
        Invoke-DockerCompose @("--profile", "test", "run", "--rm", "-e", "NETPULSE_INTEGRATION=1", "tests", "-p", "no:cacheprovider", "-m", "integration")
    }
    "up" {
        Invoke-DockerCompose @("up", "-d", "--build", "--wait", "event-ingestor")
    }
    "down" {
        Invoke-DockerCompose @("down")
    }
    "reset" {
        Write-Warning "Removing NetPulse containers and persistent Kafka/PostgreSQL volumes."
        Invoke-DockerCompose @("down", "--volumes", "--remove-orphans")
    }
    "logs" {
        Invoke-DockerCompose @("logs", "--follow", "--tail", "200")
    }
    "demo" {
        Invoke-DockerCompose @("up", "-d", "--build", "--wait", "event-ingestor")
        Invoke-DockerCompose @("--profile", "demo", "run", "--rm", "simulator", "run", "--scenario", "healthy", "--duration", "10")
        Invoke-DockerCompose @("--profile", "demo", "run", "--rm", "simulator", "run", "--scenario", "wifi-degradation", "--duration", "5")
        Invoke-DockerCompose @("--profile", "test", "run", "--rm", "--entrypoint", "python", "tests", "scripts/verify_stack.py")
    }
    "verify" {
        Invoke-DockerCompose @("up", "-d", "--build", "--wait", "event-ingestor")
        Invoke-DockerCompose @("--profile", "demo", "run", "--rm", "simulator", "run", "--scenario", "malformed-events", "--duration", "2")
        Invoke-DockerCompose @("--profile", "test", "run", "--rm", "--entrypoint", "python", "tests", "scripts/verify_stack.py")
    }
    "kafka-topics" {
        Invoke-DockerCompose @("exec", "-T", "kafka", "/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server", "localhost:9092", "--describe")
    }
    "db-shell" {
        Invoke-DockerCompose @("exec", "postgres", "psql", "-U", "netpulse_admin", "-d", "netpulse")
    }
    "config" {
        Invoke-DockerCompose @("config", "--quiet")
    }
    "agent-build" {
        Invoke-DockerCompose @("build", "network-agent")
    }
    "agent-validate" {
        Invoke-DockerCompose @("--profile", "agent", "run", "--rm", "--no-deps", "network-agent", "--config", "/etc/netpulse-agent/agent.yaml", "validate-config")
    }
    "agent-test" {
        Invoke-DockerCompose @("--profile", "test", "run", "--rm", "tests", "-p", "no:cacheprovider", "services/network-agent/tests")
    }
    "stream-build" {
        Invoke-DockerCompose @("build", "stream-processor")
    }
    "stream-run" {
        Invoke-DockerCompose @("up", "-d", "--build", "--wait", "event-ingestor")
        Invoke-DockerCompose @("--profile", "streaming", "up", "-d", "--build", "stream-processor")
    }
    "stream-once" {
        Invoke-DockerCompose @("up", "-d", "--build", "--wait", "event-ingestor")
        Invoke-DockerCompose @(
            "--profile", "streaming", "run", "--rm",
            "-e", "NETPULSE_STREAM_TRIGGER_MODE=available-now",
            "stream-processor"
        )
    }
    "stream-verify" {
        Invoke-DockerCompose @("up", "-d", "--build", "--wait", "event-ingestor")
        Invoke-DockerCompose @(
            "--profile", "demo", "run", "--rm", "simulator",
            "run", "--scenario", "healthy", "--duration", "2", "--seed", "42"
        )
        Invoke-DockerCompose @(
            "--profile", "demo", "run", "--rm", "simulator",
            "run", "--scenario", "malformed-events", "--duration", "1", "--seed", "43"
        )
        Invoke-DockerCompose @(
            "--profile", "streaming", "run", "--rm",
            "-e", "NETPULSE_STREAM_TRIGGER_MODE=available-now",
            "stream-processor"
        )
        Invoke-DockerCompose @(
            "--profile", "test", "run", "--rm", "--entrypoint", "python",
            "tests", "scripts/verify_streaming.py"
        )
    }
    "classifier-build" {
        Invoke-DockerCompose @("build", "incident-classifier")
    }
    "classifier-run" {
        Invoke-DockerCompose @("up", "-d", "--build", "--wait", "event-ingestor")
        Invoke-DockerCompose @(
            "--profile", "classification", "up", "-d", "--build", "incident-classifier"
        )
    }
    "classifier-once" {
        Invoke-DockerCompose @("up", "-d", "--build", "--wait", "event-ingestor")
        Invoke-DockerCompose @(
            "--profile", "classification", "run", "--rm", "--no-deps",
            "incident-classifier", "once"
        )
    }
    "classifier-verify" {
        Invoke-DockerCompose @("up", "-d", "--build", "--wait", "event-ingestor")
        Invoke-DockerCompose @("build", "incident-classifier")
        Invoke-DockerCompose @(
            "--profile", "demo", "run", "--rm", "--no-deps", "simulator",
            "run", "--scenario", "wifi-degradation", "--duration", "3", "--seed", "71"
        )
        Start-Sleep -Seconds 1
        1..2 | ForEach-Object {
            Invoke-DockerCompose @(
                "--profile", "classification", "run", "--rm", "--no-deps",
                "-e", "NETPULSE_CLASSIFIER_LOOKBACK_SECONDS=15",
                "incident-classifier", "once"
            )
        }
        Invoke-DockerCompose @(
            "--profile", "demo", "run", "--rm", "--no-deps", "simulator",
            "run", "--scenario", "healthy", "--duration", "6", "--seed", "72"
        )
        Start-Sleep -Seconds 1
        1..2 | ForEach-Object {
            Invoke-DockerCompose @(
                "--profile", "classification", "run", "--rm", "--no-deps",
                "-e", "NETPULSE_CLASSIFIER_LOOKBACK_SECONDS=5",
                "incident-classifier", "once"
            )
        }
        Invoke-DockerCompose @(
            "--profile", "test", "run", "--rm", "--no-deps", "--entrypoint", "python",
            "tests", "scripts/verify_classification.py"
        )
    }
    "analytics-build" {
        Invoke-DockerCompose @("--profile", "analytics", "build", "analytics")
    }
    "analytics-all" {
        Invoke-DockerCompose @("up", "-d", "--wait", "postgres")
        Invoke-DockerCompose @("--profile", "analytics", "build", "migrate", "analytics")
        Invoke-DockerCompose @("run", "--rm", "migrate")
        Invoke-DockerCompose @("--profile", "analytics", "run", "--rm", "analytics", "--all")
    }
    "analytics-verify" {
        Invoke-DockerCompose @("up", "-d", "--wait", "postgres")
        Invoke-DockerCompose @("--profile", "analytics", "--profile", "test", "build", "migrate", "analytics", "tests")
        Invoke-DockerCompose @("run", "--rm", "migrate")
        Invoke-DockerCompose @("--profile", "analytics", "run", "--rm", "analytics", "--all")
        Invoke-DockerCompose @(
            "--profile", "test", "run", "--rm", "--no-deps", "--entrypoint", "python",
            "tests", "scripts/verify_analytics.py"
        )
    }
}
