#!/usr/bin/env python3
"""
build.py — Generate docs-static/site/api.html from Documentation.md.

Parses the API Catalog section (## 5.) and emits a fully styled HTML
reference page with per-endpoint cards including method badges and
short descriptions.  Run automatically by the Docker builder stage so
rebuilding the docs-static image always picks up the latest markdown.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC_MD = ROOT.parent / "Documentation.md"
OUT_HTML = ROOT / "site" / "api.html"

# ── Short descriptions for each endpoint ────────────────────────────────────
DESCRIPTIONS: dict[str, str] = {
    "GET /health": "Returns 200 if the backend is alive",
    "POST /auth/register": "Register a new local user account",
    "POST /auth/login": "Authenticate with username/password — returns access token and sets refresh cookie",
    "POST /auth/refresh": "Exchange refresh cookie for a fresh access token",
    "POST /auth/logout": "Invalidate the refresh token and clear the cookie",
    "GET /auth/me": "Return current authenticated user info",
    "POST /auth/change-password": "Change password for the currently authenticated user",
    "GET /auth/sso/microsoft/start": "Initiate Microsoft OIDC authorization flow",
    "GET /auth/sso/microsoft/callback": "Complete Microsoft OIDC exchange and issue session cookie",
    "GET /users": "List all users (admin only)",
    "POST /users": "Create a new local user (admin only)",
    "PATCH /users/{user_id}": "Update a user's profile or role assignment (admin only)",
    "DELETE /users/{user_id}": "Delete a user (admin only)",
    "GET /users/roles": "List all roles",
    "POST /users/roles": "Create a role (admin only)",
    "PATCH /users/roles/{role_id}": "Update a role (admin only)",
    "DELETE /users/roles/{role_id}": "Delete a role (admin only)",
    "GET /users/permissions": "List all available permission identifiers",
    "GET /servers": "List all configured Jamf server entries",
    "POST /servers": "Add a new Jamf server configuration",
    "PATCH /servers/{server_id}": "Update server credentials or metadata",
    "DELETE /servers/{server_id}": "Remove a Jamf server config",
    "POST /servers/provision": "Run provisioning flow for a server (credentials and role setup)",
    "POST /servers/{server_id}/sync": "Trigger manual data sync for one server",
    "POST /servers/sync-all": "Trigger data sync across all configured servers",
    "GET /servers/{server_id}/sync/status": "Check last sync time and result for a server",
    "GET /dashboard/stats": "Aggregate counts: devices, policies, smart groups, patches",
    "GET /devices": "List managed devices with optional server filter and pagination",
    "GET /devices/{device_id}": "Get full device inventory record",
    "GET /policies": "List Jamf policies",
    "GET /policies/{policy_id}": "Get policy detail",
    "GET /smart-groups": "List smart groups",
    "GET /smart-groups/{group_id}": "Get smart group membership and criteria",
    "GET /patches": "List patch management titles",
    "GET /patches/{patch_id}": "Get patch title detail",
    "GET /assets/scripts": "List scripts from the selected Jamf server",
    "GET /assets/scripts/{script_id}": "Full script content, parameters, and Jamf deep link",
    "GET /assets/packages": "List packages from the selected Jamf server",
    "POST /knowledge/scrape": "Create a scrape job from a URL or domain",
    "GET /knowledge/scrape": "List all scrape jobs",
    "GET /knowledge/scrape/system": "System-level scrape overview and stats",
    "GET /knowledge/scrape/{job_id}": "Get detail for a specific scrape job",
    "GET /knowledge/scrape/{job_id}/logs": "Retrieve logs from a scrape job",
    "GET /knowledge/scrape/{job_id}/runtime": "Live CPU/memory/progress of a running job",
    "PATCH /knowledge/scrape/{job_id}": "Pause, resume, or cancel a running scrape job",
    "DELETE /knowledge/scrape/{job_id}": "Delete a scrape job record",
    "GET /knowledge/sources": "List ingested knowledge sources in the vector store",
    "DELETE /knowledge/sources/{source_id}": "Remove a knowledge source from ChromaDB",
    "GET /migrator/objects": "List migratable objects from the source Jamf server",
    "POST /migrator/migrate": "Execute a migration of selected objects to the target server",
    "GET /ai/sessions": "List AI chat sessions for the current user",
    "POST /ai/sessions": "Create a new AI chat session",
    "DELETE /ai/sessions/{session_id}": "Delete a session and its full message history",
    "GET /ai/sessions/{session_id}/messages": "Retrieve message history for a session",
    "POST /ai/chat": "Send a message and receive an AI-generated response",
    "POST /ai/chat/stream": "Send a message and stream the AI response via SSE",
    "GET /logs": "List audit log entries — supports ?category= and ?limit= filters",
}


# ── Parser ───────────────────────────────────────────────────────────────────

def parse_api_catalog(md: str) -> list[dict]:
    """Extract API Catalog sub-sections and their endpoints from Documentation.md."""
    section_match = re.search(
        r"^## 5\. API Catalog\s*\n(.*?)(?=^## \d+\.|\Z)",
        md,
        re.MULTILINE | re.DOTALL,
    )
    if not section_match:
        return []

    section_text = section_match.group(1)
    parts = re.split(r"^### \d+\.\d+ (.+)$", section_text, flags=re.MULTILINE)

    groups: list[dict] = []
    i = 1
    while i < len(parts):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        endpoints = []
        for line in body.strip().splitlines():
            m = re.match(r"-\s+(GET|POST|PATCH|DELETE|PUT)\s+(/\S+)", line.strip())
            if m:
                endpoints.append({"method": m.group(1), "path": m.group(2)})
        if endpoints:
            groups.append({"title": title, "endpoints": endpoints})
        i += 2

    return groups


# ── HTML builders ────────────────────────────────────────────────────────────

def badge(method: str) -> str:
    return f'<span class="badge badge-{method.lower()}">{method}</span>'


def endpoint_card(ep: dict, base: str = "/api/v1") -> str:
    key = f"{ep['method']} {ep['path']}"
    desc = DESCRIPTIONS.get(key, "")
    desc_html = f'<span class="ep-desc">{desc}</span>' if desc else ""
    return (
        f'          <div class="ep-card">\n'
        f'            {badge(ep["method"])}\n'
        f'            <code class="ep-path">{base}{ep["path"]}</code>\n'
        f"            {desc_html}\n"
        f"          </div>"
    )


def section_html(group: dict) -> str:
    sid = "api-" + re.sub(r"[^a-z0-9]+", "-", group["title"].lower()).strip("-")
    n = len(group["endpoints"])
    cards = "\n".join(endpoint_card(ep) for ep in group["endpoints"])
    return (
        f'        <article id="{sid}" class="card section api-section">\n'
        f'          <div class="section-head">\n'
        f'            <h2>{group["title"]}</h2>\n'
        f'            <p>{n} endpoint{"s" if n != 1 else ""}'
        f' &mdash; all paths prefixed with <code class="inline-code">/api/v1</code></p>\n'
        f"          </div>\n"
        f'          <div class="ep-list">\n'
        f"{cards}\n"
        f"          </div>\n"
        f"        </article>"
    )


def nav_item(group: dict) -> str:
    sid = "api-" + re.sub(r"[^a-z0-9]+", "-", group["title"].lower()).strip("-")
    return f'          <a href="#{sid}" class="nav-link">{group["title"]}</a>'


def generate_html(groups: list[dict]) -> str:
    total = sum(len(g["endpoints"]) for g in groups)
    sections = "\n".join(section_html(g) for g in groups)
    nav = "\n".join(nav_item(g) for g in groups)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>API Reference \u2014 Jamf AI Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap"
      rel="stylesheet"
    />
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body>
    <header class="hero hero-sm">
      <div class="hero-inner">
        <p class="eyebrow"><a href="index.html" class="eyebrow-link">\u2190 Docs Home</a></p>
        <h1>API Reference</h1>
        <p class="lead">
          Full endpoint catalog \u2014 {total} endpoints across {len(groups)} domains,
          all mounted under <code class="inline-code">/api/v1</code>.
          Interactive Swagger UI is also available at
          <code class="inline-code">:8000/docs</code>.
        </p>
        <div class="hero-meta">
          <span>Backend: :8000</span>
          <span>Swagger UI: :8000/docs</span>
          <span>{total} endpoints</span>
        </div>
      </div>
      <div class="hero-orb orb-a"></div>
      <div class="hero-orb orb-b"></div>
    </header>

    <main class="layout">
      <aside class="sidebar card">
        <div class="nav-search-wrap">
          <input id="navSearch" type="search" class="nav-search" placeholder="Search\u2026" autocomplete="off" />
        </div>
        <nav id="sidebarNav">
{nav}
          <hr class="nav-divider" />
          <a href="index.html" class="nav-link nav-link-accent">\u2190 Docs Home</a>
        </nav>
      </aside>

      <section class="content" id="mainContent">
{sections}
      </section>
    </main>

    <script>
      // \u2500\u2500 Active link via Intersection Observer \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
      const sections = document.querySelectorAll('.api-section');
      const links    = document.querySelectorAll('.nav-link');
      const observer = new IntersectionObserver(entries => {{
        entries.forEach(e => {{
          if (e.isIntersecting) {{
            links.forEach(l => l.classList.remove('active'));
            const active = document.querySelector(`.nav-link[href="#${{e.target.id}}"]`);
            if (active) active.classList.add('active');
          }}
        }});
      }}, {{ rootMargin: '-20% 0px -70% 0px' }});
      sections.forEach(s => observer.observe(s));

      // \u2500\u2500 Search filter (sections + nav + endpoint paths) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
      document.getElementById('navSearch').addEventListener('input', function () {{
        const q = this.value.toLowerCase().trim();
        links.forEach(link => {{
          if (!link.getAttribute('href')?.startsWith('#')) return;
          link.style.display = !q || link.textContent.toLowerCase().includes(q) ? '' : 'none';
        }});
        sections.forEach(sec => {{
          const heading = sec.querySelector('h2')?.textContent.toLowerCase() || '';
          const paths = [...sec.querySelectorAll('.ep-path')].map(c => c.textContent.toLowerCase()).join(' ');
          const descs = [...sec.querySelectorAll('.ep-desc')].map(c => c.textContent.toLowerCase()).join(' ');
          sec.style.display = !q || heading.includes(q) || paths.includes(q) || descs.includes(q) ? '' : 'none';
        }});
      }});
    </script>
  </body>
</html>
"""


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    if not SRC_MD.exists():
        sys.exit(f"ERROR: Documentation.md not found at {SRC_MD}")

    md = SRC_MD.read_text(encoding="utf-8")
    groups = parse_api_catalog(md)

    if not groups:
        sys.exit("ERROR: Could not parse API Catalog (## 5.) from Documentation.md")

    html = generate_html(groups)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")

    total = sum(len(g["endpoints"]) for g in groups)
    print(f"[build.py] Generated {OUT_HTML.relative_to(ROOT.parent)}")
    print(f"           {len(groups)} sections, {total} endpoints")


if __name__ == "__main__":
    main()
