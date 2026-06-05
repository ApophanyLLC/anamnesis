"""Optional local web UI for searching Anamnesis indexes."""


import json
from dataclasses import asdict, is_dataclass
from typing import Any
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import webbrowser
from urllib.parse import parse_qs, urlparse

from .models import SearchResult


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _source_status_by_id(sources_payload: list[dict]) -> dict[str, dict]:
    return {entry.get("source_id", ""): entry for entry in sources_payload}


def _prepare_search_results(
    results: tuple[SearchResult, ...], *, status_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    source_status_by_id = _source_status_by_id(
        status_payload.get("sources", [])  # type: ignore[arg-type]
    )
    prepared: list[dict] = []
    for item in results:
        source_status = source_status_by_id.get(item.source_id, {})
        parser_mode = source_status.get("parser_mode", "unknown")
        parser_mode_label = source_status.get("parser_mode_label", "Structured Chat")
        tooltip = source_status.get(
            "parser_mode_chunking_tooltip",
            "Structured parser mode was used for this source.",
        )
        prepared.append(
            {
                **asdict(item),
                "parser_mode": parser_mode,
                "source_mode_label": parser_mode_label,
                "title_with_mode": f"[{parser_mode_label}] {item.title}",
                "chunking_tooltip": tooltip,
            }
        )
    return prepared


def _index_sync_badge(sync_health: dict[str, object]) -> str:
    if not sync_health.get("has_issues"):
        return "Indexed sources are healthy."
    issues = sync_health.get("issues", [])
    if not isinstance(issues, list) or not issues:
        return "Index health could not be evaluated."
    return f"{len(issues)} source sync issue(s) are currently reported."


def _render_page(initial_port: int) -> str:
    title = "Anamnesis Search"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f5f7ff;
      --card: #ffffff;
      --text: #111827;
      --muted: #6b7280;
      --accent: #2563eb;
      --bad: #b91c1c;
      --good: #166534;
    }}
    body {{
      margin: 0;
      background: linear-gradient(140deg, #f5f7ff 0%, #eef3ff 52%, #f7fbff 100%);
      color: var(--text);
      font: 14px/1.4 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    }}
    .wrap {{
      max-width: 860px;
      margin: 2rem auto;
      padding: 0 1rem 1.5rem;
    }}
    .card {{
      background: var(--card);
      border-radius: 12px;
      border: 1px solid #dbeafe;
      box-shadow: 0 20px 35px -24px rgba(30, 58, 138, 0.45);
      padding: 1rem 1.2rem;
      margin-bottom: 1rem;
    }}
    h1 {{
      margin: 0 0 0.45rem;
      font-size: 1.4rem;
      letter-spacing: 0.01em;
    }}
    .row {{
      display: flex;
      gap: 0.5rem;
      align-items: center;
      margin: 0.65rem 0 1rem;
    }}
    input {{
      flex: 1;
      padding: 0.6rem;
      border: 1px solid #d6ddff;
      border-radius: 8px;
      background: #fff;
    }}
    button {{
      padding: 0.6rem 0.9rem;
      border-radius: 8px;
      border: 0;
      background: var(--accent);
      color: #fff;
      cursor: pointer;
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.92rem;
      margin-bottom: 0.65rem;
    }}
    .list {{
      border-top: 1px solid #edf2ff;
      margin-top: 0.6rem;
      padding-top: 0.6rem;
    }}
    .row-item {{
      border-radius: 10px;
      border: 1px solid #e5eaf8;
      background: #fcfdff;
      padding: 0.65rem;
      margin: 0.5rem 0;
    }}
    .title {{
      margin: 0;
      font-size: 1rem;
      font-weight: 600;
    }}
    .source {{
      color: var(--muted);
      font-size: 0.86rem;
      margin-top: 0.15rem;
    }}
    .chunk {{
      margin-top: 0.45rem;
      white-space: pre-wrap;
      background: #f8fbff;
      border: 1px solid #e2e8ff;
      border-radius: 8px;
      padding: 0.55rem;
    }}
    .badge {{
      display: inline-block;
      border-radius: 999px;
      border: 1px solid #dbeafe;
      padding: 0.1rem 0.5rem;
      margin-right: 0.35rem;
      font-size: 0.75rem;
      color: #1e3a8a;
      background: #eff6ff;
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <h1>{title}</h1>
      <div class=\"meta\">Local Anamnesis web UI · listening on port {initial_port}</div>
      <div class=\"row\">
        <input id=\"query\" placeholder=\"Search indexed sessions...\" />
        <button onclick=\"runSearch()\">Search</button>
      </div>
      <div id=\"status\"></div>
      <div id=\"results\" class=\"list\"></div>
    </div>
    <div class=\"meta\">Tip: use the CLI for scripting and export workflows; this UI is a read-only convenience layer.</div>
  </div>
  <script>
    const statusBox = document.getElementById('status');
    const resultsBox = document.getElementById('results');
    const queryInput = document.getElementById('query');

    async function runSearch() {{
      const q = queryInput.value.trim();
      statusBox.textContent = q ? `Searching: ${'{'}q{'}'}` : 'Enter a search query.';
      resultsBox.innerHTML = '';
      if (!q) {{
        return;
      }}
      try {{
        const resp = await fetch('/api/search?q=' + encodeURIComponent(q));
        const payload = await resp.json();
        statusBox.textContent = payload.status_message || '';
        const items = payload.results || [];
        if (!items.length) {{
          resultsBox.innerHTML = '<p>No matches. Verify the query and index freshness.</p>';
          return;
        }}
        for (const item of items) {{
          const block = document.createElement('div');
          block.className = 'row-item';
          const title = document.createElement('div');
          title.innerHTML = `<div class=\"title\">[${'{'}item.source_mode_label{'}'}] ${'{'}escapeHtml(item.title){'}'}</div>`;
          const source = document.createElement('div');
          source.className = 'source';
          source.textContent = `${'{'}item.path{'}'} · ${'{'}item.source_id{'}'} · mode: ${'{'}item.parser_mode{'}'}`;
          const snippet = document.createElement('div');
          snippet.className = 'chunk';
          snippet.textContent = item.content || '';
          block.appendChild(title);
          block.appendChild(source);
          block.appendChild(snippet);
          resultsBox.appendChild(block);
        }}
      }} catch (error) {{
        statusBox.textContent = 'Search request failed: ' + error;
      }}
    }}

    function escapeHtml(value) {{
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
    }}

    queryInput.addEventListener('keydown', (event) => {{
      if (event.key === 'Enter') {{
        runSearch();
      }}
    }});
  </script>
</body>
</html>"""


def run_web_ui(
    service: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
) -> None:
    """Start a tiny local HTTP server for querying the existing search flow."""

    class _AnamnesisWebHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: object, *, status: int = 200) -> None:
            body = json.dumps(payload, default=_json_default).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_page(self) -> None:
            body = _render_page(port).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - http API
            parsed = urlparse(self.path)
            if parsed.path in {"", "/"}:
                self._send_page()
                return

            if parsed.path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0].strip()
                if not query:
                    self._send_json({"error": "query parameter is required", "results": []}, status=400)
                    return
                results = service.search(query)
                status_payload = service.status()
                sync_health = service.sync_health()
                self._send_json(
                    {
                        "query": query,
                        "results": _prepare_search_results(
                            results,
                            status_payload=status_payload,
                        ),
                        "status_message": _index_sync_badge(sync_health),
                    }
                )
                return

            if parsed.path == "/api/health":
                self._send_json(service.sync_health())
                return

            if parsed.path == "/api/status":
                self._send_json(service.status())
                return

            self.send_error(404, "not found")

        def log_message(self, fmt: str, *args: object) -> None:
            # Intentionally quiet in local single-user environments.
            return

    server = HTTPServer((host, port), _AnamnesisWebHandler)
    url = f"http://{host}:{port}/"
    if open_browser:
        webbrowser.open(url)
    print(f"Anamnesis web UI listening on {url}")
    print("Press Ctrl+C to stop the web server.")

    try:
        server.serve_forever()
    finally:
        server.server_close()
