"""Small server-rendered pages for the dashboard and placeholders."""

from html import escape

from .registry import Tool


def layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} · PF2e GM Toolkit</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="/static/app.js" defer></script>
</head>
<body>
  <header class="site-header"><div class="container">
    <a class="brand" href="/">PF2e GM Toolkit</a>
    <span class="tagline">A local workspace for the Game Master</span>
  </div></header>
  <main class="container">{body}</main>
</body>
</html>"""


def dashboard(tools: list[Tool]) -> str:
    cards = "\n".join(
        f'<li class="tool-card" data-tool-search="{escape((tool.name + " " + tool.purpose).lower(), quote=True)}">'
        f'<a href="/tools/{escape(tool.slug, quote=True)}">'
        f'<h2>{escape(tool.name)}</h2><p>{escape(tool.purpose)}</p>'
        f'<span class="card-link">{"Open tool" if tool.implemented else "Open placeholder"} →</span></a></li>'
        for tool in tools
    )
    body = f"""
    <section class="intro">
      <h1>GM tools</h1>
      <p>Choose a tool to open its workspace. More tools are planned for later phases.</p>
    </section>
    <section id="dashboard-xp" class="dashboard-xp" hidden aria-live="polite"><a href="/tools/treasure-xp">Party progress</a><span id="dashboard-xp-text"></span></section>
    <label class="search-label" for="tool-search">Find a tool</label>
    <input id="tool-search" type="search" placeholder="Search by name or purpose" autocomplete="off">
    <p id="no-results" hidden>No matching tools.</p>
    <ul class="tool-grid" id="tool-grid">{cards}</ul>
    """
    return layout("Dashboard", body)


def placeholder(tool: Tool) -> str:
    body = f"""
    <nav aria-label="Breadcrumb"><a class="back-link" href="/">← All tools</a></nav>
    <article class="placeholder">
      <h1>{escape(tool.name)}</h1>
      <p>{escape(tool.purpose)}</p>
      <p class="status">Not implemented yet</p>
    </article>
    """
    return layout(tool.name, body)
