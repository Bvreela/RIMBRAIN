# run-event-map -- event mapping round-trip gate (US-4, SC-004): canonical wrap/unwrap over the corpus.
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
Push-Location $root
uv run --with jsonschema,pyyaml,pytest pytest components/contracts/tests/test_event_roundtrip.py components/contracts/tests/test_schema_drift.py -q
$rc = $LASTEXITCODE
Pop-Location
exit $rc
