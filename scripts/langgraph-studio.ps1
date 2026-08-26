# UTF-8: pinned langgraph-cli help/dev banners include emoji that crash
# Windows cp1252 consoles (UnicodeEncodeError). Paths in langgraph.json are
# relative to apps/agents. See docs/development/LANGGRAPH_STUDIO.md.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Import-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        if ($line.StartsWith("export ")) {
            $line = $line.Substring(7).Trim()
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) {
            return
        }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        elseif ($value.StartsWith("'") -and $value.EndsWith("'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($name) {
            Set-Item -Path ("Env:{0}" -f $name) -Value $value
        }
    }
}

Import-DotEnvFile -Path (Join-Path $root ".env")
Import-DotEnvFile -Path (Join-Path $root ".env.compose")

$composeEnv = Join-Path $root ".env.compose"
if (-not $env:LANGSMITH_API_KEY) {
    Write-Warning "LANGSMITH_API_KEY is unset. Add it to $composeEnv so Studio can show traces."
}
else {
    $project = $env:LANGSMITH_PROJECT
    if (-not $project) { $project = "smart-rag" }
    $tracing = $env:LANGSMITH_TRACING
    if (-not $tracing) { $tracing = "unset" }
    Write-Host ("Studio LangSmith: key=set tracing={0} project={1}" -f $tracing, $project)
}

Set-Location (Join-Path $root "apps\agents")
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
uv run langgraph dev --config langgraph.json --no-browser --no-reload --allow-blocking @args
