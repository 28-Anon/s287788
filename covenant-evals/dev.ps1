# Windows convenience wrapper, so PowerShell users have a short command too.
#
#   .\dev.ps1 test                    -> python -m pytest -q
#   .\dev.ps1 lint                    -> ruff check + format check
#   .\dev.ps1 config check            -> python -m covenant_evals.cli config check
#   .\dev.ps1 corpus doctor           -> python -m covenant_evals.cli corpus doctor
#   .\dev.ps1 items stats             -> python -m covenant_evals.cli items stats
#
# Anything not listed below is passed straight through to the CLI, so this never needs
# updating when a new command is added.
#
# PowerShell will not run a script from the current directory without the leading .\ —
# that is a security feature, not a mistake in these instructions.

param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)

if (-not $Rest -or $Rest.Count -eq 0) {
    Write-Host "usage: .\dev.ps1 <command> [args...]"
    Write-Host "       .\dev.ps1 test | lint | <any covenant-evals command>"
    exit 2
}

switch ($Rest[0]) {
    "test" { & py -m pytest -q @($Rest[1..($Rest.Count - 1)]); break }
    "lint" {
        & py -m ruff check src tests
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & py -m ruff format --check src tests
        break
    }
    default { & py -m covenant_evals.cli @Rest }
}

exit $LASTEXITCODE
