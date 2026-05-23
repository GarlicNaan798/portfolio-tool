from __future__ import annotations

import argparse
import csv
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


STATE_DIR = Path("state")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local dashboard for portfolio agent progress.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", default="state")
    args = parser.parse_args()

    handler = make_handler(Path(args.state_dir))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Dashboard running at http://{args.host}:{args.port}", flush=True)
    print("Press Ctrl+C to stop the dashboard.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.", flush=True)
    finally:
        server.server_close()


def make_handler(state_dir: Path):
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self.respond_html(page_html())
            elif path == "/api/status":
                self.respond_json(build_status(state_dir))
            elif path.startswith("/api/csv/"):
                name = path.removeprefix("/api/csv/")
                self.respond_json({"rows": read_csv(state_dir / name)})
            else:
                self.send_error(404)

        def log_message(self, format: str, *args) -> None:
            return

        def respond_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def respond_json(self, payload) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return DashboardHandler


def build_status(state_dir: Path) -> dict:
    scores = read_csv(state_dir / "opportunity_scores.csv")
    agent_scores = read_csv(state_dir / "agent_scores.csv")
    ledger = read_csv(state_dir / "research_ledger.csv")
    memory = read_csv(state_dir / "research_memory.csv")
    execution_plan = read_csv(state_dir / "execution_plan.csv")
    exit_plan = read_csv(state_dir / "exit_plan.csv")
    portfolio = read_csv(state_dir / "alpaca_portfolio.csv")
    decision_book = read_json(state_dir / "decision_book.json")
    execute_log = state_dir / "continuous_research_execute.out.log"
    execute_err = state_dir / "continuous_research_execute.err.log"
    dry_run_log = state_dir / "continuous_research.out.log"
    active_log = execute_log if execute_log.exists() else dry_run_log

    latest_score_timestamp = scores[-1]["timestamp"] if scores else ""
    latest_scores = [row for row in scores if row.get("timestamp") == latest_score_timestamp]
    latest_ledger_timestamp = ledger[-1]["timestamp"] if ledger else ""
    latest_ledger = [row for row in ledger if row.get("timestamp") == latest_ledger_timestamp]
    latest_agent_timestamp = agent_scores[-1]["timestamp"] if agent_scores else ""
    latest_agent_scores = [row for row in agent_scores if row.get("timestamp") == latest_agent_timestamp]

    disposed = [row for row in latest_ledger if row.get("memory_status") == "DISPOSED"]
    active = [row for row in latest_ledger if row.get("memory_status") == "ACTIVE"]
    average_score = float(latest_scores[-1].get("average_top_score", 0.0)) if latest_scores else 0.0

    return {
        "latest_score_timestamp": latest_score_timestamp,
        "latest_research_timestamp": latest_ledger_timestamp,
        "average_score": average_score,
        "target_score": 7.0,
        "score_rows": len(scores),
        "ledger_rows": len(ledger),
        "memory_rows": len(memory),
        "active_count": len(active),
        "disposed_count": len(disposed),
        "top_scores": latest_scores[:15],
        "agents": group_agent_scores(latest_agent_scores),
        "disposed": disposed[:25],
        "memory": memory[:50],
        "execution_plan": execution_plan,
        "exit_plan": exit_plan,
        "portfolio": portfolio,
        "decision_count": len(decision_book.get("decisions", [])) if isinstance(decision_book, dict) else 0,
        "runner": runner_status(active_log, execute_err),
        "files": file_info(state_dir),
    }


def runner_status(stdout_path: Path, stderr_path: Path) -> dict:
    stdout_exists = stdout_path.exists()
    stderr_exists = stderr_path.exists()
    stdout_mtime = stdout_path.stat().st_mtime if stdout_exists else 0.0
    stderr_mtime = stderr_path.stat().st_mtime if stderr_exists else 0.0
    age_seconds = max(0.0, time.time() - stdout_mtime) if stdout_mtime else 0.0
    stderr_tail = tail_text(stderr_path, 80)
    stdout_tail = tail_text(stdout_path, 120)
    latest_cycle = ""
    for line in reversed(stdout_tail.splitlines()):
        if "Running portfolio model" in line:
            latest_cycle = line.strip()
            break
    fatal = bool(stderr_tail.strip())
    stale = not stdout_exists or age_seconds > 25 * 60
    return {
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "stdout_modified": stdout_mtime,
        "stderr_modified": stderr_mtime,
        "age_seconds": age_seconds,
        "status": "ERROR" if fatal else ("STALE" if stale else "RUNNING"),
        "latest_cycle": latest_cycle,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


def group_agent_scores(rows: list[dict[str, str]]) -> list[dict]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row.get("agent", ""), []).append(row)
    agents = []
    for agent, agent_rows in grouped.items():
        first = agent_rows[0]
        agents.append(
            {
                "agent": agent,
                "agent_name": first.get("agent_name", agent),
                "industry": first.get("industry", ""),
                "average_score": float(first.get("agent_average_score") or 0.0),
                "researched": int(float(first.get("researched") or 0)),
                "skipped": int(float(first.get("skipped") or 0)),
                "errors": int(float(first.get("errors") or 0)),
                "top": agent_rows[:8],
            }
        )
    return sorted(agents, key=lambda item: item["agent_name"])


def file_info(state_dir: Path) -> list[dict]:
    files = []
    for path in sorted(state_dir.glob("*")):
        if path.is_file():
            stat = path.stat()
            files.append({"name": path.name, "size": stat.st_size, "modified": stat.st_mtime})
    return files


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def tail_text(path: Path, max_lines: int) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:])


def page_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Portfolio Agent Dashboard</title>
  <style>
    :root { color-scheme: light; --bg:#f6f7f9; --ink:#18202a; --muted:#657080; --line:#d9dee7; --panel:#ffffff; --good:#147a3f; --warn:#a15c00; }
    body { margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--ink); }
    header { padding:22px 28px; background:#101820; color:white; display:flex; justify-content:space-between; gap:20px; align-items:center; }
    h1 { margin:0; font-size:22px; letter-spacing:0; }
    main { max-width:1280px; margin:0 auto; padding:24px; }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:14px; }
    .agents { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:14px; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }
    .metric { font-size:28px; font-weight:750; margin-top:6px; }
    .label { color:var(--muted); font-size:13px; }
    .target { height:10px; background:#e7ebf0; border-radius:999px; overflow:hidden; margin-top:10px; }
    .bar { height:100%; background:#1d6f8f; width:0%; }
    section { margin-top:18px; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
    th { color:var(--muted); font-weight:650; background:#fafbfc; position:sticky; top:0; }
    .table-wrap { overflow:auto; max-height:420px; }
    .pill { display:inline-block; border-radius:999px; padding:2px 8px; font-weight:700; font-size:12px; }
    .buy { color:var(--good); background:#e7f5ed; }
    .trim,.sell { color:#9c2f21; background:#fae9e7; }
    .hold { color:#31556b; background:#e7f0f5; }
    .watch { color:#6c4a00; background:#fff3cc; }
    .pass { color:#6f7782; background:#edf0f3; }
    .muted { color:var(--muted); }
    .row { display:flex; justify-content:space-between; gap:16px; align-items:baseline; }
    select, button { font:inherit; padding:8px 10px; border:1px solid var(--line); background:white; border-radius:6px; }
    pre { background:#0f1720; color:#dce7f3; border-radius:8px; padding:14px; overflow:auto; max-height:520px; line-height:1.42; font-size:12px; }
    .status { display:inline-block; border-radius:999px; padding:4px 10px; font-weight:800; font-size:12px; }
    .RUNNING { color:#075c31; background:#dff5e8; }
    .STALE { color:#815000; background:#fff1c2; }
    .ERROR { color:#8f1f18; background:#ffe1de; }
    @media (max-width: 900px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } header { align-items:flex-start; flex-direction:column; } }
    @media (max-width: 900px) { .agents { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Portfolio Agent Dashboard</h1>
      <div class="muted" id="last-updated">Loading...</div>
    </div>
    <div>Auto-refresh: 10s</div>
  </header>
  <main>
    <div class="grid">
      <div class="panel"><div class="label">Average Opportunity Score</div><div class="metric" id="avg">0.00/10</div><div class="target"><div class="bar" id="avgbar"></div></div></div>
      <div class="panel"><div class="label">Active Memory</div><div class="metric" id="active">0</div></div>
      <div class="panel"><div class="label">Disposed This Cycle</div><div class="metric" id="disposed">0</div></div>
      <div class="panel"><div class="label">Decision Book Names</div><div class="metric" id="decisions">0</div></div>
    </div>
    <section class="panel">
      <div class="row"><h2>Live Runner</h2><span id="runner-status" class="status">Loading</span></div>
      <div class="grid" style="margin-top:12px">
        <div><div class="label">Latest Cycle</div><div id="runner-cycle"></div></div>
        <div><div class="label">Log Age</div><div id="runner-age"></div></div>
        <div><div class="label">Output Log</div><div id="runner-out-file"></div></div>
        <div><div class="label">Error Log</div><div id="runner-err-file"></div></div>
      </div>
      <pre id="runner-log"></pre>
      <pre id="runner-err" style="display:none"></pre>
    </section>
    <section class="panel">
      <div class="row"><h2>Alpaca Portfolio Awareness</h2><span class="muted">Live snapshot read by agents</span></div>
      <div class="table-wrap"><table id="portfolio-table"></table></div>
    </section>
    <section class="panel">
      <div class="row"><h2>Execution Coordinator</h2><span class="muted">Validated allocation signals</span></div>
      <div class="table-wrap"><table id="execution-table"></table></div>
    </section>
    <section class="panel">
      <div class="row"><h2>Exit Manager</h2><span class="muted">Profit-taking and stop-loss plan</span></div>
      <div class="table-wrap"><table id="exit-table"></table></div>
    </section>
    <section class="panel">
      <div class="row"><h2>Top Opportunities</h2><span class="muted" id="score-cycle"></span></div>
      <div class="table-wrap"><table id="top-table"></table></div>
    </section>
    <section>
      <div class="row"><h2>Industry Agents</h2><span class="muted">Separated statistics per agent</span></div>
      <div class="agents" id="agent-board"></div>
    </section>
    <section class="panel">
      <div class="row"><h2>Disposed From Memory</h2><span class="muted">Current research cycle</span></div>
      <div class="table-wrap"><table id="disposed-table"></table></div>
    </section>
    <section class="panel">
      <div class="row">
        <h2>CSV Viewer</h2>
        <select id="csv-select">
          <option value="opportunity_scores.csv">opportunity_scores.csv</option>
          <option value="agent_scores.csv">agent_scores.csv</option>
          <option value="execution_plan.csv">execution_plan.csv</option>
          <option value="exit_plan.csv">exit_plan.csv</option>
          <option value="alpaca_portfolio.csv">alpaca_portfolio.csv</option>
          <option value="research_ledger.csv">research_ledger.csv</option>
          <option value="research_memory.csv">research_memory.csv</option>
        </select>
      </div>
      <div class="table-wrap"><table id="csv-table"></table></div>
    </section>
  </main>
  <script>
    const fmtScore = value => Number(value || 0).toFixed(2);
    const fmtAge = seconds => {
      seconds = Number(seconds || 0);
      if (seconds < 60) return `${seconds.toFixed(0)}s`;
      if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
      return `${(seconds / 3600).toFixed(1)}h`;
    };
    async function getJson(url) { const r = await fetch(url, {cache:'no-store'}); return await r.json(); }
    function pill(action) { return `<span class="pill ${(action || '').toLowerCase()}">${action || ''}</span>`; }
    function renderTable(id, rows, cols) {
      const table = document.getElementById(id);
      if (!rows.length) { table.innerHTML = '<tr><td class="muted">No rows yet</td></tr>'; return; }
      table.innerHTML = '<thead><tr>' + cols.map(c => `<th>${c.label}</th>`).join('') + '</tr></thead><tbody>' +
        rows.map(row => '<tr>' + cols.map(c => `<td>${c.render ? c.render(row) : (row[c.key] ?? '')}</td>`).join('') + '</tr>').join('') + '</tbody>';
    }
    function renderAgentBoard(agents) {
      const board = document.getElementById('agent-board');
      if (!agents.length) { board.innerHTML = '<div class="panel muted">Agent stats will appear after the next research cycle.</div>'; return; }
      board.innerHTML = agents.map(agent => `
        <div class="panel">
          <div class="row">
            <div>
              <h3>${agent.agent_name}</h3>
              <div class="muted">${agent.industry}</div>
            </div>
            <div class="metric">${fmtScore(agent.average_score)}</div>
          </div>
          <div class="target"><div class="bar" style="width:${Math.min(100, agent.average_score / 7 * 100)}%"></div></div>
          <div class="row muted" style="margin-top:10px">
            <span>researched ${agent.researched}</span>
            <span>skipped ${agent.skipped}</span>
            <span>errors ${agent.errors}</span>
          </div>
          <div class="table-wrap" style="max-height:260px; margin-top:10px">
            <table>
              <thead><tr><th>Rank</th><th>Symbol</th><th>Score</th><th>DCF</th><th>Margin</th><th>Pred Ret</th><th>Action</th><th>Target</th></tr></thead>
              <tbody>
                ${agent.top.map(row => `<tr><td>${row.rank}</td><td>${row.symbol}</td><td>${fmtScore(row.opportunity_score)}</td><td>${fmtScore(Number(row.dcf || 0) * 10)}</td><td>${(Number(row.dcf_margin_safety || 0) * 100).toFixed(1)}%</td><td>${(Number(row.predicted_return_pct || 0) * 100).toFixed(1)}%</td><td>${pill(row.action)}</td><td>${(Number(row.target_weight || 0) * 100).toFixed(1)}%</td></tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `).join('');
    }
    async function refresh() {
      const data = await getJson('/api/status');
      document.getElementById('last-updated').textContent = `Latest file update: ${new Date().toLocaleTimeString()}`;
      document.getElementById('avg').textContent = `${fmtScore(data.average_score)}/10`;
      document.getElementById('avgbar').style.width = `${Math.min(100, data.average_score / data.target_score * 100)}%`;
      document.getElementById('active').textContent = data.active_count;
      document.getElementById('disposed').textContent = data.disposed_count;
      document.getElementById('decisions').textContent = data.decision_count;
      document.getElementById('score-cycle').textContent = data.latest_score_timestamp || 'No cycle yet';
      const runner = data.runner || {};
      const status = document.getElementById('runner-status');
      status.textContent = runner.status || 'UNKNOWN';
      status.className = `status ${runner.status || ''}`;
      document.getElementById('runner-cycle').textContent = runner.latest_cycle || 'No cycle found yet';
      document.getElementById('runner-age').textContent = fmtAge(runner.age_seconds);
      document.getElementById('runner-out-file').textContent = runner.stdout_file || '';
      document.getElementById('runner-err-file').textContent = runner.stderr_file || '';
      document.getElementById('runner-log').textContent = runner.stdout_tail || 'No runner log yet.';
      const err = document.getElementById('runner-err');
      err.style.display = runner.stderr_tail ? 'block' : 'none';
      err.textContent = runner.stderr_tail || '';
      renderTable('top-table', data.top_scores, [
        {key:'symbol', label:'Symbol'},
        {key:'opportunity_score', label:'Opportunity', render:r => fmtScore(r.opportunity_score)},
        {key:'average_top_score', label:'Avg', render:r => fmtScore(r.average_top_score)},
        {key:'dcf_component', label:'DCF', render:r => fmtScore(r.dcf_component)},
        {key:'dcf_margin_safety', label:'DCF Margin', render:r => `${(Number(r.dcf_margin_safety || 0) * 100).toFixed(1)}%`},
        {key:'dcf_intrinsic_value', label:'Intrinsic', render:r => `$${Number(r.dcf_intrinsic_value || 0).toFixed(2)}`},
        {key:'predicted_return_pct', label:'Pred Ret', render:r => `${(Number(r.predicted_return_pct || 0) * 100).toFixed(1)}%`},
        {key:'action', label:'Action', render:r => pill(r.action)},
        {key:'target_weight', label:'Target', render:r => `${(Number(r.target_weight || 0) * 100).toFixed(1)}%`},
        {key:'rationale', label:'Rationale'}
      ]);
      renderAgentBoard(data.agents || []);
      renderTable('portfolio-table', data.portfolio || [], [
        {key:'symbol', label:'Symbol', render:r => r.symbol || '<span class="muted">No positions</span>'},
        {key:'qty', label:'Qty'},
        {key:'market_value', label:'Market Value'},
        {key:'portfolio_value', label:'Portfolio Value'},
        {key:'weight', label:'Weight', render:r => `${(Number(r.weight || 0) * 100).toFixed(2)}%`},
        {key:'warning', label:'Warning'}
      ]);
      renderTable('execution-table', data.execution_plan || [], [
        {key:'agent_name', label:'Agent'},
        {key:'symbol', label:'Symbol'},
        {key:'opportunity_score', label:'Opportunity', render:r => fmtScore(r.opportunity_score)},
        {key:'action', label:'Action', render:r => pill(r.action)},
        {key:'source_action', label:'Research'},
        {key:'notional', label:'Allocation', render:r => `$${Number(r.notional || 0).toFixed(2)}`},
        {key:'cash', label:'Cash', render:r => `$${Number(r.cash || 0).toFixed(0)}`},
        {key:'buying_power', label:'Buying Power', render:r => `$${Number(r.buying_power || 0).toFixed(0)}`},
        {key:'predicted_return_pct', label:'Pred Ret', render:r => `${(Number(r.predicted_return_pct || 0) * 100).toFixed(1)}%`},
        {key:'predicted_profit', label:'Pred Profit', render:r => `$${Number(r.predicted_profit || 0).toFixed(2)}`},
        {key:'status', label:'Status'},
        {key:'allocation_note', label:'Sizing'},
        {key:'reason', label:'Reason'}
      ]);
      renderTable('exit-table', data.exit_plan || [], [
        {key:'symbol', label:'Symbol'},
        {key:'qty', label:'Qty', render:r => Number(r.qty || 0).toFixed(2)},
        {key:'unrealized_plpc', label:'Unrealized', render:r => `${(Number(r.unrealized_plpc || 0) * 100).toFixed(2)}%`},
        {key:'side', label:'Exit Side'},
        {key:'exit_fraction', label:'Exit %', render:r => `${(Number(r.exit_fraction || 0) * 100).toFixed(0)}%`},
        {key:'status', label:'Status'},
        {key:'reason', label:'Reason'}
      ]);
      renderTable('disposed-table', data.disposed, [
        {key:'symbol', label:'Symbol'},
        {key:'composite', label:'Composite', render:r => fmtScore(r.composite)},
        {key:'action', label:'Action', render:r => pill(r.action)},
        {key:'rationale', label:'Rationale'}
      ]);
      await refreshCsv();
    }
    async function refreshCsv() {
      const name = document.getElementById('csv-select').value;
      const data = await getJson(`/api/csv/${name}`);
      const rows = data.rows.slice(-100).reverse();
      const keys = rows.length ? Object.keys(rows[0]) : [];
      renderTable('csv-table', rows, keys.map(key => ({key, label:key})));
    }
    document.getElementById('csv-select').addEventListener('change', refreshCsv);
    refresh();
    setInterval(refresh, 10000);
  </script>
</body>
</html>"""


if __name__ == "__main__":
    main()
