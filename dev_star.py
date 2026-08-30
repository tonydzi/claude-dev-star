#!/usr/bin/env python3
"""dev_star.py — a strategy radar for your Claude Code sessions.

Most Claude Code dashboards answer "how many tokens did I burn and what did it cost?"
This one answers a different question: "where is my effort actually going — and is it
moving me FORWARD, or just keeping the lights on?"

It reads your local Claude Code transcripts (~/.claude/projects/*/*.jsonl), classifies
each session into a direction with deterministic keyword rules (no LLM calls, nothing
leaves your machine), and renders a star chart: one spike per direction, spike length =
share of output tokens. Gold spikes move you forward (sales, product, content, research);
grey spikes are support work (infra, ops). A forward direction starving below 10% gets a
pulsing red ring — that's the spike you should be feeding.

Usage:
    python3 dev_star.py                  # last 50 sessions -> dev-star.html + dev-star.json
    python3 dev_star.py --n 200          # bigger window
    python3 dev_star.py --config my.json # custom directions/keywords (see README)

Zero dependencies, Python 3.8+. Output: dev-star.html (open in a browser), dev-star.json
(machine-readable — feed it back to your agents so they know where the effort goes).
"""
import argparse, glob, json, os, re, time
from collections import defaultdict

DEFAULT_DIRECTIONS = {
    "sales": dict(label="Sales & customers", forward=True, kw=[
        "lead", "crm", "outreach", "customer", "client", "deal", "demo", "pricing",
        "invoice", "follow-up", "followup", "prospect", "pipeline", "onboarding"]),
    "product": dict(label="Product & features", forward=True, kw=[
        "feature", "implement", "build", "app ", "api", "endpoint", "ui", "ux",
        "release", "ship", "prototype", "mvp", "integration", "launch"]),
    "content": dict(label="Content & audience", forward=True, kw=[
        "post", "blog", "article", "newsletter", "tweet", "thread", "video",
        "landing", "seo", "audience", "readme", "announce"]),
    "research": dict(label="Research", forward=True, kw=[
        "research", "explore", "investigate", "benchmark", "evaluate", "compare",
        "analysis", "analyze", "spike", "study", "survey"]),
    "infra": dict(label="Infra & maintenance", forward=False, kw=[
        "fix", "bug", "refactor", "test", "ci", "deploy", "docker", "config",
        "migration", "upgrade", "dependency", "cleanup", "lint", "debug", "error",
        "flaky", "pipeline failure", "hook", "cron", "backup", "monitoring"]),
    "ops": dict(label="Ops & admin", forward=False, kw=[
        "email", "calendar", "meeting", "notes", "summarize", "organize", "rename",
        "expense", "admin", "schedule"]),
}
FEED_THRESHOLD = 0.10  # a forward direction below this share is flagged as starving


def _hits(text, kw):
    # short ASCII keywords match on word boundaries only ("api" must not match "capital")
    if kw.isascii() and kw.isalpha() and len(kw) <= 4:
        return len(re.findall(r"\b" + re.escape(kw) + r"\b", text))
    return text.count(kw)


def classify(text, directions):
    t = (text or "").lower()
    scores = {}
    for key, d in directions.items():
        s = sum(_hits(t, k) for k in d["kw"])
        if s:
            scores[key] = s
    return max(scores, key=scores.get) if scores else "other"


def scan_session(path):
    """One transcript -> metrics. Output tokens are deduped by message.id — Claude Code
    repeats the same usage block on every record of a message, so naive summing
    overcounts by a lot."""
    title, first_user, msgs = None, "", 0
    out_by_msg = {}
    t0 = t1 = None
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts = rec.get("timestamp")
                if ts:
                    t0, t1 = t0 or ts, ts
                rt = rec.get("type")
                if rt == "custom-title" and not title:
                    title = rec.get("title") or rec.get("value")
                elif rt == "user" and not first_user and not rec.get("isSidechain"):
                    c = rec.get("message", {}).get("content")
                    if isinstance(c, str):
                        first_user = c[:2000]
                    elif isinstance(c, list):
                        first_user = " ".join(x.get("text", "") for x in c if isinstance(x, dict))[:2000]
                elif rt == "assistant" and not rec.get("isSidechain"):
                    m = rec.get("message", {})
                    u = m.get("usage") or {}
                    mid = m.get("id") or rec.get("uuid")
                    if u.get("output_tokens"):
                        out_by_msg[mid] = u["output_tokens"]
                    msgs += 1
    except Exception:
        return None
    return dict(id=os.path.basename(path)[:-6], title=title or first_user[:90].replace("\n", " ") or "(untitled)",
                first_user=first_user[:300], start=t0, end=t1,
                out_tokens=sum(out_by_msg.values()), msgs=msgs)


def build(n, directions, projects_dir):
    files = []
    for proj in glob.glob(os.path.join(projects_dir, "*/")):
        files += glob.glob(proj + "*.jsonl")
    files.sort(key=os.path.getmtime, reverse=True)
    sessions = []
    for f in files:
        if len(sessions) >= n:
            break
        s = scan_session(f)
        if not s or s["out_tokens"] < 200:
            continue
        s["direction"] = classify(s["title"] + " " + s["first_user"], directions)
        sessions.append(s)
    agg = defaultdict(lambda: dict(sessions=0, out_tokens=0))
    for s in sessions:
        agg[s["direction"]]["sessions"] += 1
        agg[s["direction"]]["out_tokens"] += s["out_tokens"]
    total = sum(a["out_tokens"] for a in agg.values()) or 1
    dirs = {}
    for key in list(directions) + ["other"]:
        meta = directions.get(key, dict(label="Other", forward=False))
        a = agg.get(key, dict(sessions=0, out_tokens=0))
        dirs[key] = dict(label=meta["label"], forward=meta["forward"], sessions=a["sessions"],
                         out_tokens=a["out_tokens"], share=round(a["out_tokens"] / total, 4))
    return dict(generated=time.strftime("%Y-%m-%dT%H:%M:%S"), window_sessions=len(sessions),
                total_out_tokens=total, directions=dirs, sessions=sessions)


TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Dev Star</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Unbounded:wght@400;600&family=Golos+Text:wght@400;500;600&display=swap">
<style>
:root{--bg:#10151b;--panel:#171e26;--ink:#e8e5dd;--muted:#8b96a2;--gold:#e6b23c;--gold-soft:#e6b23c26;
--steel:#7e8b98;--steel-soft:#7e8b9826;--alert:#e05545;--line:#232c36;--grid:#ffffff12}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Golos Text",system-ui,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 60px}
h1{font-family:"Unbounded",sans-serif;font-weight:600;font-size:clamp(22px,4vw,34px);margin:0 0 6px}
.sub{color:var(--muted);margin:0 0 4px}
.verdict{margin:18px 0 26px;padding:14px 18px;border-left:3px solid var(--alert);background:var(--panel);border-radius:0 10px 10px 0}
.verdict b{color:var(--alert)}
.grid{display:grid;grid-template-columns:minmax(320px,1fr) minmax(300px,420px);gap:26px;align-items:start}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
.starbox{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:26px 14px}
svg{width:100%;height:auto;display:block;overflow:visible}
.cards{display:flex;flex-direction:column;gap:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.card .row{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.card .name{font-weight:600}
.tag{font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:2px 8px;border-radius:20px}
.tag.fwd{background:var(--gold-soft);color:var(--gold)}
.tag.sup{background:var(--steel-soft);color:var(--steel)}
.tag.feed{background:#e0554526;color:var(--alert)}
.nums{color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
.bar{height:6px;border-radius:3px;background:var(--grid);margin-top:8px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:3px}
.sessions{margin-top:34px}
h2{font-family:"Unbounded",sans-serif;font-weight:400;font-size:18px}
details{border-bottom:1px solid var(--line);padding:6px 0}
summary{cursor:pointer;display:flex;justify-content:space-between;gap:10px;list-style:none}
summary::-webkit-details-marker{display:none}
summary .n{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
td{padding:4px 8px;border-top:1px solid var(--line)}
td.t{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right}
footer{margin-top:20px;color:var(--muted);font-size:12px}
@media (prefers-reduced-motion:no-preference){.pulse{animation:pu 2.2s ease-in-out infinite}@keyframes pu{0%,100%{opacity:.35}50%{opacity:1}}}
</style></head><body>
<div class="wrap">
<h1>Dev Star</h1>
<p class="sub">__WINDOW__ recent sessions · __TOTAL__ output tokens · __GEN__</p>
<div class="verdict" id="verdict"></div>
<div class="grid">
  <div class="starbox"><svg id="star" viewBox="0 0 640 640" role="img" aria-label="direction star"></svg></div>
  <div class="cards" id="cards"></div>
</div>
<div class="sessions"><h2>Sessions by direction</h2><div id="sess"></div></div>
<footer>gold = moves you forward · grey = support work · red pulsing ring = forward direction starving below 10%.
Generated locally by dev_star.py — no LLM calls, nothing leaves your machine.</footer>
</div>
<script>
const DATA = __DATA__;
const FEED_T = __FEED__;
const fmt = n => n.toLocaleString('en-US');
const dirs = Object.entries(DATA.directions).filter(([k,d]) => d.out_tokens > 0)
  .sort((a,b) => b[1].out_tokens - a[1].out_tokens);
(function(){
  const under = dirs.filter(([k,d]) => d.forward && d.share < FEED_T).map(([k,d]) => d.label);
  const fwd = dirs.filter(([k,d]) => d.forward).reduce((s,[k,d]) => s + d.share, 0);
  const sup = 1 - fwd;
  document.getElementById('verdict').innerHTML =
    `<b style="color:var(--ink)">${Math.round(fwd*100)}%</b> of your effort moves you forward; ` +
    `<b>${Math.round(sup*100)}%</b> keeps the lights on.` +
    (under.length ? ` Starving: <b>${under.join(', ')}</b> — these spikes should grow.` : '');
})();
(function(){
  const svg = document.getElementById('star');
  const cx=320, cy=320, R=250, r0=36, n=dirs.length;
  const maxShare = Math.max(...dirs.map(([k,d]) => d.share));
  const pt = (i,rad) => { const a=-Math.PI/2+i*2*Math.PI/n; return [cx+rad*Math.cos(a), cy+rad*Math.sin(a)]; };
  const rad = s => r0 + (R-r0)*Math.sqrt(s/maxShare);
  let g = '';
  for (const f of [0.25,0.5,0.75,1]) g += `<circle cx="${cx}" cy="${cy}" r="${r0+(R-r0)*f}" fill="none" stroke="var(--grid)"/>`;
  dirs.forEach(([k,d],i) => { const [x,y]=pt(i,R); g += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="var(--grid)"/>`; });
  let path = '';
  dirs.forEach(([k,d],i) => {
    const [vx,vy]=pt(i,rad(d.share)); const [mx,my]=pt(i+0.5,r0*0.8);
    path += (i?'L':'M')+vx+' '+vy+' L'+mx+' '+my+' ';
  });
  g += `<path d="${path}Z" fill="var(--gold-soft)" stroke="var(--gold)" stroke-width="1.2" stroke-linejoin="round"/>`;
  dirs.forEach(([k,d],i) => {
    const [vx,vy]=pt(i,rad(d.share));
    const feed = d.forward && d.share < FEED_T;
    if (feed) g += `<circle class="pulse" cx="${vx}" cy="${vy}" r="14" fill="none" stroke="var(--alert)" stroke-width="2"/>`;
    g += `<circle cx="${vx}" cy="${vy}" r="6" fill="${d.forward?'var(--gold)':'var(--steel)'}"/>`;
    const [lx,ly]=pt(i,R+34);
    const anchor = Math.abs(lx-cx)<40 ? 'middle' : (lx>cx?'start':'end');
    g += `<text x="${lx}" y="${ly}" text-anchor="${anchor}" fill="${feed?'var(--alert)':'var(--ink)'}" font-size="14" font-weight="600">${d.label}</text>`;
    g += `<text x="${lx}" y="${ly+16}" text-anchor="${anchor}" fill="var(--muted)" font-size="12">${Math.round(d.share*100)}% · ${d.sessions} sessions</text>`;
  });
  svg.innerHTML = g;
})();
(function(){
  document.getElementById('cards').innerHTML = dirs.map(([k,d]) => {
    const feed = d.forward && d.share < FEED_T;
    const tag = feed ? '<span class="tag feed">feed me!</span>' : d.forward ? '<span class="tag fwd">forward</span>' : '<span class="tag sup">support</span>';
    const col = feed ? 'var(--alert)' : d.forward ? 'var(--gold)' : 'var(--steel)';
    return `<div class="card"><div class="row"><span class="name">${d.label}</span>${tag}</div>
      <div class="nums">${fmt(d.out_tokens)} tok · ${d.sessions} sessions · ${Math.round(d.share*100)}%</div>
      <div class="bar"><i style="width:${Math.max(2,d.share*100)}%;background:${col}"></i></div></div>`;
  }).join('');
})();
(function(){
  document.getElementById('sess').innerHTML = dirs.map(([k,d]) => {
    const rows = DATA.sessions.filter(s => s.direction===k).sort((a,b) => b.out_tokens-a.out_tokens)
      .map(s => `<tr><td>${(s.title||'').replace(/</g,'&lt;').slice(0,110)}</td><td class="t">${fmt(s.out_tokens)}</td></tr>`).join('');
    return `<details><summary><span>${d.label}</span><span class="n">${d.sessions} sessions · ${fmt(d.out_tokens)} tok</span></summary>
      <table><tbody>${rows}</tbody></table></details>`;
  }).join('');
})();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="strategy radar for Claude Code sessions")
    ap.add_argument("--n", type=int, default=50, help="how many recent sessions (default 50)")
    ap.add_argument("--config", help="JSON file with custom directions (see README)")
    ap.add_argument("--projects-dir", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--out", default="dev-star", help="output basename (default dev-star)")
    args = ap.parse_args()
    directions = DEFAULT_DIRECTIONS
    if args.config:
        directions = json.load(open(args.config))
    data = build(args.n, directions, args.projects_dir)
    with open(args.out + ".json", "w") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    html = (TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__WINDOW__", str(data["window_sessions"]))
            .replace("__TOTAL__", f"{data['total_out_tokens']:,}")
            .replace("__FEED__", str(FEED_THRESHOLD))
            .replace("__GEN__", data["generated"][:16].replace("T", " ")))
    with open(args.out + ".html", "w") as fh:
        fh.write(html)
    print(f"{args.out}.html  {args.out}.json")
    for k, d in sorted(data["directions"].items(), key=lambda x: -x[1]["out_tokens"]):
        if d["out_tokens"]:
            print(f"{d['out_tokens']:>12,}  {d['sessions']:>3} sessions  {'*' if d['forward'] else ' '} {d['label']}")


if __name__ == "__main__":
    main()
