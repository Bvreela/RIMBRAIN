"""Settings UI + JSON API for the endpoint registry (feature 002, T064).

Stdlib ``http.server`` — no build step, no npm. YAML under ``profiles/`` stays
authoritative: every request re-reads the files (SC-003). Secrets never leave
the server — ``api_key_ref`` strings pass through as refs only (FR-002).

Runtime import via sys.path fallback to ``components/runtime/src``; when
unavailable, API routes return ``{ok:false,error:{code:"runtime.unavailable"}}``
but the page still serves.

    python -m dashboard.server --port 8771
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_DASH_SRC = Path(__file__).resolve().parents[1]
_RUNTIME_SRC = _DASH_SRC.parents[1] / "runtime" / "src"
if str(_RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_SRC))

try:
    # Public facade only (repo boundary: dashboard must not import internals).
    from runtime import api as _ra
    _RUNTIME_OK = True
except ImportError:
    _RUNTIME_OK = False

PAGE = """<!doctype html><meta charset=utf-8><title>RimBrainAgent — Model Endpoints</title>
<style>
body{font:14px/1.4 system-ui;margin:24px;max-width:1100px;color:#ddd;background:#16181d}
h1{font-size:18px} h2{font-size:15px;margin-top:28px}
table{border-collapse:collapse;width:100%} td,th{border:1px solid #333;padding:4px 8px;text-align:left}
button,input,select{background:#22242b;color:#ddd;border:1px solid #444;padding:4px 8px}
button{cursor:pointer} button:hover{border-color:#888}
.ok{color:#7d7}.bad{color:#e77}.dim{color:#888} code{color:#9cf}
</style>
<h1>Model Endpoints <span class=dim>(profiles/*.yaml authoritative)</span></h1>
<div id=eps></div>
<h2>Add endpoint</h2>
<form onsubmit="return addEp()">
<input id=neid placeholder=id required> <input id=nelabel placeholder=label>
<select id=neapi><option>openai-compat</option><option>systemone</option></select>
<input id=neurl placeholder=base_url size=40 required>
<input id=nekey placeholder="api_key_ref (env:NAME)" size=22>
<input id=nemodels placeholder="models,comma,separated" required>
<input id=necaps placeholder="caps,comma,separated" required>
<button>add</button>
<button type=button onclick="discover()">scan local</button></form>
<div id=disc></div>
<h2>Role bindings</h2><div id=binds></div>
<script>
async function j(u,o){const r=await fetch(u,o?{method:o.m||'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o.b)}:undefined);return r.json()}
async function load(){
 const e=await j('/api/endpoints'),b=await j('/api/bindings');
 let h='<table><tr><th>id</th><th>api</th><th>base_url</th><th>models</th><th>caps</th><th></th></tr>';
 const dups=new Set(e.duplicates||[]),pr=e.probes||{};
 for(const x of e.endpoints||[])h+=`<tr><td><code>${x.id}</code>${pr[x.id]?(pr[x.id].ok?' <span class=ok>ok</span>':' <span class=bad>fail</span>'):''}<div class=dim>${x.label||''}</div></td><td>${x.api}</td><td class=dim>${dups.has(x.base_url)?'<span class=bad title="duplicate base_url">[dup] </span>':''}${x.base_url}</td><td>${(x.models||[]).join(', ')}</td><td>${(x.capabilities||[]).join(', ')}</td><td><button onclick="probe('${x.id}',this)">probe</button> <button onclick="del('${x.id}')">del</button></td></tr>`;
 eps.innerHTML=h+'</table>';
 h='<table><tr><th>role</th><th>endpoint</th><th>model</th><th></th></tr>';
 const opts=(e.endpoints||[]).map(x=>`<option>${x.id}</option>`).join('');
 for(const[r,v]of Object.entries(b.bindings||{}))h+=`<tr><td><code>${r}</code></td><td><select id=bep_${r}>${opts.replace(`>${v.endpoint}<`,` selected>${v.endpoint}<`)}</select></td><td><input id=bmo_${r} value="${v.model}"></td><td><button onclick="bind('${r}')">set</button></td></tr>`;
 h+=`<tr><td><input id=nrole placeholder="rimbrain.role"></td><td><select id=nbep>${opts}</select></td><td><input id=nbmo placeholder=model></td><td><button onclick="bind2()">bind</button></td></tr></table>`;
 binds.innerHTML=h;
}
async function probe(id,btn){btn.textContent='...';const r=await j('/api/probe/'+id,{m:'POST'});btn.textContent=r.ok?('ok '+r.latency_ms+'ms'):('fail '+r.error.code);btn.className=r.ok?'ok':'bad'}
async function del(id){if(confirm('delete '+id+'?')){await j('/api/endpoints/'+id,{m:'DELETE'});load()}}
async function addEp(){const r=await j('/api/endpoints',{b:{id:neid.value,label:nelabel.value,api:neapi.value,base_url:neurl.value,api_key_ref:nekey.value||null,models:nemodels.value.split(',').map(s=>s.trim()).filter(Boolean),capabilities:necaps.value.split(',').map(s=>s.trim()).filter(Boolean),...(neapi.value==='systemone'?{decide_path:'/v1/systemone'}:{})}});if(!r.ok)alert(r.error.code);else load();return false}
async function bind(r){const res=await j('/api/bindings',{b:{role:r,endpoint:document.getElementById('bep_'+r).value,model:document.getElementById('bmo_'+r).value}});if(!res.ok)alert(res.error.code)}
async function bind2(){bind(nrole.value)}
async function discover(){disc.innerHTML='<i>scanning…</i>';const r=await j('/api/discover');disc.innerHTML=(r.result||[]).map(c=>`<div>found <code>${c.label}</code> @ ${c.base_url} — models: ${c.models.join(', ')||'(none)'} <button onclick='addCand(${JSON.stringify(c)})'>add</button></div>`).join('')||'<i>nothing found</i>'}
async function addCand(c){c.id=c.id.replace(/[^a-z0-9._-]/g,'-');await j('/api/endpoints',{b:c});load()}
load()</script>"""


def _json(h, status, obj):
    body = json.dumps(obj).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _unavailable(h):
    _json(h, 503, {"ok": False, "error": {
        "code": "runtime.unavailable",
        "message": "runtime package not importable",
        "retryable": False}})


class Handler(BaseHTTPRequestHandler):
    def _call(self, fn, *a, **kw):
        if not _RUNTIME_OK:
            return _unavailable(self)
        try:
            _json(self, 200, fn(*a, **kw))
        except Exception as exc:  # RegistryError etc. carry envelopes
            env = getattr(exc, "envelope", None)
            _json(self, 500, env or {"ok": False, "error": {
                "code": "ui.error", "message": str(exc), "retryable": False}})

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/endpoints":
            self._call(_ra.list_endpoints)
        elif path == "/api/bindings":
            self._call(_ra.list_bindings)
        elif path == "/api/discover":
            self._call(lambda: {"ok": True, "result": _ra.scan_local()})
        elif path.startswith("/api/resolve/"):
            role = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            self._call(lambda: _ra.resolve_role(role))
        else:
            _json(self, 404, {"ok": False, "error": {
                "code": "ui.not_found", "message": path, "retryable": False}})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/endpoints":
            self._call(_ra.add_endpoint, self._body())
        elif path == "/api/bindings":
            b = self._body()
            self._call(_ra.bind_role, b.get("role"), b.get("endpoint"),
                       b.get("model"))
        elif path.startswith("/api/probe/"):
            eid = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            self._call(lambda: _ra.probe(eid))
        else:
            _json(self, 404, {"ok": False, "error": {
                "code": "ui.not_found", "message": path, "retryable": False}})

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/endpoints/"):
            eid = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            self._call(_ra.update_endpoint, eid, self._body())
        else:
            _json(self, 404, {"ok": False, "error": {
                "code": "ui.not_found", "message": path, "retryable": False}})

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/endpoints/"):
            eid = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            force = "force=1" in urllib.parse.urlparse(self.path).query
            self._call(_ra.delete_endpoint, eid, force=force)
        else:
            _json(self, 404, {"ok": False, "error": {
                "code": "ui.not_found", "message": path, "retryable": False}})

    def log_message(self, *a):
        pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dashboard.server", description=__doc__)
    p.add_argument("--port", type=int, default=8771)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args(argv)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"settings UI on http://{args.host}:{args.port} "
          f"(runtime={'ok' if _RUNTIME_OK else 'unavailable'})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
