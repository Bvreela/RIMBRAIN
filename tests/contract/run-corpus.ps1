# Quickstart section 5 entry point: validate the contract primitive corpus.
# Runs corpus_runner.py through uv with its declared deps; no game/model/network needed.
$ErrorActionPreference = 'Stop'
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
uv run --with jsonschema,pyyaml --no-project python tests/contract/corpus_runner.py validate-corpus
exit $LASTEXITCODE
