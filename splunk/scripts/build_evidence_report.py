#!/usr/bin/env python3
"""Build a self-contained, read-only HTML report from evidence/."""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
OUTPUT = EVIDENCE / "report.html"


def pretty_json(path: Path) -> str:
    try:
        return json.dumps(json.loads(path.read_text()), indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, OSError):
        return path.read_text(errors="replace")


def text_preview(path: Path, limit: int = 50000) -> str:
    content = path.read_text(errors="replace")
    return content if len(content) <= limit else content[:limit] + "\n… preview truncated …"


def badge(label: str, value: str, tone: str = "blue") -> str:
    return f'<div class="badge {tone}"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'


def main() -> None:
    files = sorted(p for p in EVIDENCE.iterdir() if p.is_file() and p.name != OUTPUT.name)
    validation = json.loads((EVIDENCE / "validation.json").read_text())
    image = base64.b64encode((EVIDENCE / "dashboard.png").read_bytes()).decode()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    cards = "".join([
        badge("Splunk", f"{validation['version']} / {validation['build']}", "green"),
        badge("Service", "active", "green"),
        badge("KV Store", validation["kvstore"], "green"),
        badge("Dashboard panels", str(validation["dashboard_panels_completed"]), "green"),
        badge("Boot changed", "no", "green"),
        badge("Existing failed unit", "1", "amber"),
    ])

    inv_rows = "".join(
        f"<tr><td><code>{html.escape(p.name)}</code></td><td>{p.stat().st_size:,}</td>"
        f"<td>{html.escape(p.suffix.lstrip('.').upper() or 'FILE')}</td></tr>" for p in files
    )
    sections = []
    for path in files:
        if path.suffix.lower() == ".png":
            body = '<img class="screenshot" src="data:image/png;base64,' + image + '" alt="Captured Splunk Server Health dashboard">'
        elif path.suffix.lower() == ".json":
            body = f"<pre>{html.escape(pretty_json(path))}</pre>"
        elif path.suffix.lower() in {".txt", ".jsonl", ".pem"}:
            body = f"<pre>{html.escape(text_preview(path))}</pre>"
        else:
            body = f"<pre>{html.escape(text_preview(path))}</pre>"
        sections.append(f'<details><summary><code>{html.escape(path.name)}</code><span>{path.stat().st_size:,} bytes</span></summary>{body}</details>')

    report = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Splunk server evidence report</title>
<style>
:root {{ color-scheme: dark; --bg:#0c1117; --panel:#151d27; --panel2:#1c2733; --text:#e6edf3; --muted:#9fb0c0; --line:#304052; --blue:#62b0ff; --green:#48d597; --amber:#f2bd63; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:linear-gradient(135deg,#0c1117,#101a25); color:var(--text); font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif }}
main {{ max-width:1280px; margin:auto; padding:42px 24px 72px }} h1 {{ font-size:clamp(30px,5vw,52px); line-height:1.05; margin:0 0 10px }} h2 {{ margin:34px 0 12px; font-size:22px }} h3 {{ margin:0 0 8px }} p {{ color:var(--muted); max-width:980px }}
.eyebrow {{ color:var(--blue); letter-spacing:.12em; text-transform:uppercase; font-size:12px; font-weight:700 }} .meta {{ color:var(--muted); font-size:13px }}
.badges {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:28px 0 }} .badge {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px 15px }} .badge span {{ display:block; color:var(--muted); font-size:12px }} .badge strong {{ display:block; margin-top:4px; font-size:18px }} .green strong {{ color:var(--green) }} .amber strong {{ color:var(--amber) }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px }} .card {{ background:rgba(21,29,39,.92); border:1px solid var(--line); border-radius:14px; padding:18px }} table {{ border-collapse:collapse; width:100%; margin-top:8px }} th,td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line) }} th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em }} code {{ color:#a8d3ff; font-family:ui-monospace,SFMono-Regular,Menlo,monospace }}
details {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; margin:10px 0; overflow:hidden }} summary {{ cursor:pointer; padding:13px 15px; display:flex; justify-content:space-between; gap:12px; font-weight:650 }} summary span {{ color:var(--muted); font-size:12px; font-weight:400 }} pre {{ margin:0; padding:15px; max-height:520px; overflow:auto; background:#0a0f14; border-top:1px solid var(--line); white-space:pre-wrap; overflow-wrap:anywhere; font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; color:#d7e2ed }}
.screenshot {{ width:100%; display:block; background:#000 }} .note {{ border-left:3px solid var(--amber); padding:10px 14px; background:rgba(242,189,99,.08); color:#e8d7b2 }} footer {{ margin-top:42px; color:var(--muted); font-size:12px }}
</style></head><body><main>
<div class="eyebrow">Evidence review · single-page report</div><h1>Splunk server health deployment</h1>
<div class="meta">Generated {html.escape(now)} UTC · source directory <code>evidence/</code> · {len(files)} evidence files · {sum(p.stat().st_size for p in files):,} bytes</div>
<p>This report is a self-contained presentation of the captured installation, validation, telemetry, dashboard, and certificate evidence. Expand any file below to inspect its retained content.</p>
<div class="badges">{cards}</div>
<div class="note"><strong>Known condition:</strong> <code>systemd-networkd-wait-online.service</code> was already failed in the baseline and remains visible in the dashboard. No repair or reboot was performed.</div>
<h2>Evidence inventory</h2><div class="card"><table><thead><tr><th>File</th><th>Size (bytes)</th><th>Type</th></tr></thead><tbody>{inv_rows}</tbody></table></div>
<h2>Key findings</h2><div class="grid">
<div class="card"><h3>Runtime and ingestion</h3><p>Splunk {html.escape(validation['version'])} is active with KV Store ready. Live indexes report {html.escape(', '.join(x['index'] + ' (' + x['count'] + ' events)' for x in validation['live_ingestion']))}. The journal verification event was indexed once.</p></div>
<div class="card"><h3>Resource controls</h3><p>Service limits are captured in <code>validation.json</code>: 2 CPU equivalents, 5 GiB memory high watermark, 6 GiB hard ceiling, 512 MiB swap ceiling, and 4,096 tasks.</p></div>
<div class="card"><h3>Dashboard validation</h3><p>{validation['dashboard_panels_completed']} panels completed with no browser JavaScript errors. Query results and the captured browser text are included below.</p></div>
<div class="card"><h3>License</h3><p>The trial quota is {int(validation['trial_quota_bytes_per_day']) // 1048576} MiB/day and expires {html.escape(validation['trial_expires_utc'])}. The exact license and download verification records are retained.</p></div>
</div>
<h2>Captured dashboard</h2><div class="card">{('<img class="screenshot" src="data:image/png;base64,' + image + '" alt="Splunk dashboard screenshot">')}</div>
<h2>File contents</h2>{''.join(sections)}
<footer>Generated locally from evidence files. This page does not make network requests; the dashboard image is embedded as a data URI.</footer>
</main></body></html>'''
    OUTPUT.write_text(report, encoding="utf-8")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
