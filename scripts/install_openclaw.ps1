param(
    [Parameter(Mandatory = $true)]
    [string]$Model,

    [Parameter(Mandatory = $true)]
    [string]$SetupCommand,

    [string]$ConfigCommand,

    [string]$ApiKey,

    [switch]$PersistModel,
    [switch]$AutoConfigure
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[OpenClaw] $Message"
}

Set-Location -Path (Get-Location)

if ($ApiKey) {
    Write-Step "Passing OPENAI_API_KEY into the installer environment."
    $env:OPENAI_API_KEY = $ApiKey
}

if ($PersistModel) {
    Write-Step "Persisting OPENCLAW_OPENAI_MODEL for this install session."
    $env:OPENCLAW_OPENAI_MODEL = $Model
}

# Keep a generic OpenAI model env var available for installers that read it directly.
$env:OPENAI_MODEL = $Model
$env:OPENAI_PROVIDER = "openai"
$env:OPENCLAW_PROVIDER = "openai"

$resolvedCommand = $SetupCommand.Replace("{model}", $Model)

Write-Step "OpenAI-only model selected: $Model"
Write-Step "Working directory: $(Get-Location)"
Write-Step "Executing setup command:"
Write-Host $resolvedCommand

try {
    Invoke-Expression $resolvedCommand
}
catch {
    Write-Error $_
    exit 1
}

Write-Step "Setup command completed."

if (Get-Command openclaw -ErrorAction SilentlyContinue) {
    Write-Step "Preconfiguring OpenClaw default model to $Model"
    try {
        & openclaw config set agents.defaults.model.primary $Model
    }
    catch {
        Write-Warning "Could not preconfigure agents.defaults.model.primary: $($_.Exception.Message)"
    }
}

if ($AutoConfigure -and $ConfigCommand) {
    $resolvedConfig = $ConfigCommand.Replace("{model}", $Model)
    Write-Step "Starting OpenClaw config..."
    Write-Host $resolvedConfig

    try {
        Invoke-Expression $resolvedConfig
    }
    catch {
        Write-Error $_
        exit 1
    }

    Write-Step "Config command completed."
}
