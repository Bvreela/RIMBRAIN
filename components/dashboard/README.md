# rimbrainagent-dashboard

Future `rimbrainagent-dashboard` submodule — telemetry + control surfaces over public contracts. Build specification: [Dashboard](../../specs/20-submodules/DASHBOARD.md).

Current contents: the **settings UI for model endpoints** (feature 002): a zero-build stdlib page + JSON API over `profiles/endpoints.yaml` and `profiles/bindings.yaml`.

```powershell
$env:PYTHONPATH = "components/dashboard/src;components/runtime/src"
uv run --with pyyaml python -m dashboard.server --port 8771
# open http://127.0.0.1:8771
```

Endpoints table (probe/del per row), add-endpoint form, "scan local" discovery with one-click add, role-bindings editor. YAML stays authoritative — the page re-reads files per request and never displays secrets.
