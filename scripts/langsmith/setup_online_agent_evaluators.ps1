#Requires -Version 7.0
<#
.SYNOPSIS
    Provision dedicated LangSmith online evaluators for synthetic agent traces.

.DESCRIPTION
    Creates or updates smart-rag-agent-online-hard-metrics-v1 and
    smart-rag-agent-online-judge-v1 on smart-rag-agent-eval-online only.
    Does not accept or print provider/API secrets. A second run is
    idempotent.

.PARAMETER Profile
    LangSmith CLI profile name. Optional.

.PARAMETER ModelConfigurationId
    Existing LangSmith gpt-4o-mini playground/model configuration UUID.

.PARAMETER DryRun
    Validate local contracts only. No CLI, SDK, or remote writes.

.PARAMETER SkipCliInstall
    Do not attempt to install the official Windows CLI when it is absent.
#>
[CmdletBinding()]
param(
    [Parameter()]
    [string] $Profile,

    [Parameter(Mandatory = $true)]
    [string] $ModelConfigurationId,

    [Parameter()]
    [switch] $DryRun,

    [Parameter()]
    [switch] $SkipCliInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-SecretFreeError {
    param([string] $Token)
    Write-Error -Message $Token
}

if ([string]::IsNullOrWhiteSpace($ModelConfigurationId)) {
    Write-SecretFreeError -Token "model_configuration_required"
    exit 2
}

$cli = Get-Command langsmith -ErrorAction SilentlyContinue
if (-not $cli) {
    if ($SkipCliInstall) {
        Write-SecretFreeError -Token "langsmith_cli_missing"
        exit 2
    }
    try {
        Invoke-RestMethod https://cli.langsmith.com/install.ps1 | Invoke-Expression
    }
    catch {
        Write-SecretFreeError -Token "langsmith_cli_install_failed"
        exit 2
    }
    $cli = Get-Command langsmith -ErrorAction SilentlyContinue
    if (-not $cli) {
        Write-SecretFreeError -Token "langsmith_cli_missing"
        exit 2
    }
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $repoRoot) {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
$pythonScript = Join-Path $PSScriptRoot "setup_online_agent_evaluators.py"
$argsList = @(
    "run",
    "python",
    $pythonScript,
    "--model-configuration-id",
    $ModelConfigurationId
)
if ($Profile) {
    $argsList += @("--profile", $Profile)
}
if ($DryRun) {
    $argsList += "--dry-run"
}

& uv @argsList
exit $LASTEXITCODE
