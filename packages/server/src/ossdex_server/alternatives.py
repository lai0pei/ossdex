"""Personalized Open-Source Alternative Finder & Local Workflow Articulator.

Discovers, analyzes, and articulates tailored open-source alternatives for paid products
based on:
1. Current Operating System & Architecture (macOS, Linux, Windows, arm64, x86_64).
2. Installed package managers and runtime environments (Homebrew, Docker, uv, Cargo, npm...).
3. Local workflow tools (Neovim, tmux, fzf, ripgrep, lazygit, ollama, VS Code, etc.).
4. User habits (CLI-first, keyboard/Vim-driven, native GUI, local-first/offline, self-hosted Docker).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

from ossdex_core.licenses import LicenseKind, license_kind
from pydantic import BaseModel, Field

from . import repo_query as rq
from .brief_tools import classify_artifact
from .db import ReadDb
from .search import search

log = logging.getLogger("ossdex.alternatives")

OSName = Literal["macos", "linux", "windows"]
FormFactor = Literal[
    "cli_tui",
    "native_gui",
    "desktop_cross_platform",
    "self_hosted_web",
    "editor_plugin",
    "library_sdk",
    "unknown",
]
FitBadge = Literal[
    "Best Overall Match",
    "Best CLI / Terminal Match",
    "Best Native GUI Match",
    "Best Local-First Match",
    "Best Self-Hosted Match",
    "Strong Alternative",
    "Viable Contender",
]


# =============================================================================
# Curated Catalog of Common Paid Products
# =============================================================================

PAID_PRODUCT_CATALOG: dict[str, dict[str, Any]] = {
    # Knowledge, Notes & Collaboration
    "notion": {
        "name": "Notion",
        "category": "Knowledge Base & Workspace",
        "aliases": ["notion", "notion app"],
        "queries": [
            "open source notion alternative self-hosted",
            "block-based notes knowledge base local-first",
            "appflowy logseq affine outline",
        ],
        "topics": ["notion-alternative", "knowledge-base", "notes", "wiki", "pkm"],
        "known_repos": [
            "AppFlowy-IO/AppFlowy",
            "logseq/logseq",
            "toeverything/AFFiNE",
            "outline/outline",
        ],
        "core_features": ["Block editor", "Databases / Tables", "Collaborative wiki", "Markdown export"],
    },
    "roam": {
        "name": "Roam Research",
        "category": "Bi-directional Knowledge Base",
        "aliases": ["roam", "roam research"],
        "queries": ["networked thought bi-directional linking pkm", "logseq foam dendron"],
        "topics": ["pkm", "bi-directional-links", "zettelkasten", "markdown"],
        "known_repos": ["logseq/logseq", "foambubble/foam"],
        "core_features": ["Bi-directional links", "Graph view", "Outliner", "Daily notes"],
    },
    "obsidian-sync": {
        "name": "Obsidian Sync / Publish",
        "category": "Notes Sync & Publishing",
        "aliases": ["obsidian sync", "obsidian"],
        "queries": ["git sync markdown notes livesync", "self-hosted notes sync"],
        "topics": ["markdown", "pkm", "git-sync", "couchdb"],
        "known_repos": ["vrtmrz/obsidian-livesync", "denolehs/obsidian-git"],
        "core_features": ["End-to-end encrypted sync", "Conflict resolution", "Git backup"],
    },
    # API, Testing & DevTools
    "postman": {
        "name": "Postman",
        "category": "API Client & Testing",
        "aliases": ["postman", "postman app"],
        "queries": [
            "git-friendly api client offline alternative to postman",
            "bruno hoppscotch yaak insomnia rest api testing",
        ],
        "topics": ["api-client", "rest-client", "graphql", "http-client", "postman-alternative"],
        "known_repos": [
            "usebruno/bruno",
            "hoppscotch/hoppscotch",
            "anthonynsimon/yaak",
            "rest-client/rest-client",
        ],
        "core_features": ["REST / GraphQL requests", "Environment variables", "Offline / Git storage", "Test scripts"],
    },
    "insomnia": {
        "name": "Insomnia",
        "category": "API Client & Testing",
        "aliases": ["insomnia", "insomnia rest"],
        "queries": ["local-first git-friendly api client", "bruno yaak hoppscotch"],
        "topics": ["api-client", "rest", "graphql", "grpc"],
        "known_repos": ["usebruno/bruno", "anthonynsimon/yaak", "hoppscotch/hoppscotch"],
        "core_features": ["Local collection storage", "Lightweight REST/GraphQL", "Zero mandatory cloud account"],
    },
    "ngrok": {
        "name": "Ngrok",
        "category": "Reverse Proxy & Tunneling",
        "aliases": ["ngrok"],
        "queries": ["self-hosted tunnel reverse proxy expose localhost", "cloudflared frp boringproxy zrok"],
        "topics": ["tunnel", "reverse-proxy", "localhost", "nat-traversal"],
        "known_repos": ["fatedier/frp", "openziti/zrok", "rapiz1/rathole"],
        "core_features": ["Expose local ports to public internet", "Custom domain", "End-to-end encryption"],
    },
    # Database GUIs
    "tableplus": {
        "name": "TablePlus",
        "category": "Database GUI Client",
        "aliases": ["tableplus"],
        "queries": [
            "native database gui sql client sqlite postgres mysql",
            "beekeeper studio dbeaver dbgate",
        ],
        "topics": ["database-client", "sql-editor", "postgres", "mysql", "sqlite"],
        "known_repos": [
            "beekeeper-studio/beekeeper-studio",
            "dbgate/dbgate",
            "dbeaver/dbeaver",
        ],
        "core_features": ["Multi-database connections", "Fast SQL editor", "Data tab editing", "SSH tunneling"],
    },
    "datagrip": {
        "name": "DataGrip",
        "category": "Database IDE",
        "aliases": ["datagrip"],
        "queries": ["database ide sql editor autocomplete migrations", "dbeaver beekeeper dbgate"],
        "topics": ["database-ide", "sql", "postgres", "mysql"],
        "known_repos": ["dbeaver/dbeaver", "dbgate/dbgate", "beekeeper-studio/beekeeper-studio"],
        "core_features": ["Schema diffing", "Smart code completion", "Query plan visualizer"],
    },
    # Launchers, Utilities & Productivity
    "raycast": {
        "name": "Raycast",
        "category": "Command Launcher & Workflow Extender",
        "aliases": ["raycast"],
        "queries": [
            "open source spotlight launcher extensible scripts",
            "ulauncher albert cerebro vicmd rofi",
        ],
        "topics": ["launcher", "spotlight-alternative", "productivity", "shortcuts"],
        "known_repos": [
            "Ulauncher/Ulauncher",
            "albertlauncher/albert",
            "cerebroapp/cerebro",
        ],
        "core_features": ["Fuzzy app launching", "Script commands & extensions", "Clipboard history", "Calculator"],
    },
    "alfred": {
        "name": "Alfred",
        "category": "Application Launcher & Workflows",
        "aliases": ["alfred", "alfred app"],
        "queries": ["extensible application launcher workflow keyboard", "ulauncher albert"],
        "topics": ["launcher", "workflow", "productivity"],
        "known_repos": ["Ulauncher/Ulauncher", "albertlauncher/albert"],
        "core_features": ["Fast launcher", "Custom shell workflows", "Snippet expansion"],
    },
    "cleanshot": {
        "name": "CleanShot X",
        "category": "Screen Capture & Annotation",
        "aliases": ["cleanshot", "cleanshot x"],
        "queries": ["screen recording screenshot annotation tool", "kap sharex flameshot"],
        "topics": ["screenshot", "screen-recorder", "annotation"],
        "known_repos": ["flameshot-org/flameshot", "wulkano/kap", "ShareX/ShareX"],
        "core_features": ["Quick region capture", "Arrow/text annotation", "GIF/MP4 recording", "Cloud/local save"],
    },
    "loom": {
        "name": "Loom",
        "category": "Video Messaging & Screen Recording",
        "aliases": ["loom"],
        "queries": ["screen recording camera bubble instant share", "kap record obs"],
        "topics": ["screen-recording", "screen-capture", "video"],
        "known_repos": ["wulkano/kap", "obsproject/obs-studio"],
        "core_features": ["Webcam bubble overlay", "Screen recording", "Instant local file generation"],
    },
    # Containers & Virtualization
    "docker-desktop": {
        "name": "Docker Desktop",
        "category": "Container Runtime & GUI",
        "aliases": ["docker desktop", "docker"],
        "queries": [
            "lightweight docker desktop alternative macos linux",
            "colima podman desktop orbstack lima",
        ],
        "topics": ["docker-alternative", "containers", "podman", "colima", "virtualization"],
        "known_repos": [
            "abiosoft/colima",
            "containers/podman-desktop",
            "lima-vm/lima",
        ],
        "core_features": ["Container execution", "Kubernetes cluster", "Low CPU/battery overhead", "CLI compatible"],
    },
    # Terminals, Editors & Git
    "warp": {
        "name": "Warp Terminal",
        "category": "AI / Modern Terminal Emulator",
        "aliases": ["warp", "warp terminal"],
        "queries": [
            "fast modern terminal emulator gpu accelerated",
            "wezterm alacritty ghostty kitty zellij",
        ],
        "topics": ["terminal-emulator", "gpu-accelerated", "terminal", "zsh"],
        "known_repos": [
            "wez/wezterm",
            "alacritty/alacritty",
            "kovidgoyal/kitty",
            "zellij-org/zellij",
        ],
        "core_features": ["GPU accelerated rendering", "Tabs & split panes", "Vim mode / keyboard navigation"],
    },
    "cursor": {
        "name": "Cursor / Copilot",
        "category": "AI Code Editor & Pair Programmer",
        "aliases": ["cursor", "cursor editor", "github copilot"],
        "queries": [
            "open source ai coding assistant editor local models",
            "continue aider cline opencode",
        ],
        "topics": ["ai-assistant", "code-assistant", "llm-code", "copilot-alternative"],
        "known_repos": [
            "continuedev/continue",
            "Aider-AI/aider",
            "cline/cline",
        ],
        "core_features": ["In-editor multi-file editing", "Local model support (Ollama)", "Context grounding"],
    },
    "gitkraken": {
        "name": "GitKraken / Tower / Sublime Merge",
        "category": "Git GUI & Visual Client",
        "aliases": ["gitkraken", "tower", "sublime merge"],
        "queries": ["terminal git client visual commit branch graph", "lazygit gitbutler"],
        "topics": ["git", "git-client", "git-gui", "tui"],
        "known_repos": [
            "jesseduffield/lazygit",
            "gitbutlerapp/gitbutler",
            "extrawurst/gitui",
        ],
        "core_features": ["Interactive rebase", "Visual branch graph", "Staging chunks & lines", "Blame & diff"],
    },
    # Passwords & Security
    "1password": {
        "name": "1Password",
        "category": "Password Manager",
        "aliases": ["1password", "lastpass", "dashlane"],
        "queries": [
            "self-hosted end-to-end encrypted password manager",
            "bitwarden vaultwarden keepassxc",
        ],
        "topics": ["password-manager", "security", "encryption", "bitwarden"],
        "known_repos": [
            "bitwarden/clients",
            "dani-garcia/vaultwarden",
            "keepassxreboot/keepassxc",
        ],
        "core_features": ["Zero-knowledge vault", "Browser extensions", "CLI integration", "Self-hostable"],
    },
    # Team Communication & Project Tracking
    "slack": {
        "name": "Slack",
        "category": "Team Chat & Collaboration",
        "aliases": ["slack"],
        "queries": ["self-hosted team chat channels threads", "mattermost zulip rocketchat element"],
        "topics": ["chat", "collaboration", "team-chat", "slack-alternative"],
        "known_repos": [
            "mattermost/mattermost",
            "zulip/zulip",
            "RocketChat/Rocket.Chat",
            "element-hq/element-web",
        ],
        "core_features": ["Channels & direct messages", "Threaded conversations", "Webhooks & integrations", "Self-hosted"],
    },
    "linear": {
        "name": "Linear",
        "category": "Issue Tracking & Sprint Management",
        "aliases": ["linear", "jira", "trello", "asana"],
        "queries": [
            "keyboard-driven issue tracker project management",
            "plane focalboard wekan taiga",
        ],
        "topics": ["issue-tracker", "project-management", "kanban", "linear-alternative"],
        "known_repos": [
            "makeplane/plane",
            "mattermost/focalboard",
            "wekan/wekan",
            "taigaio/taiga-back",
        ],
        "core_features": ["Cycles / Sprints", "Kanban & list views", "Keyboard shortcuts", "GitHub sync"],
    },
    # Workflow Automation
    "zapier": {
        "name": "Zapier / Make.com",
        "category": "Workflow Automation & iPaaS",
        "aliases": ["zapier", "make.com", "integromat", "pipedream"],
        "queries": [
            "self-hosted workflow automation visual node triggers",
            "n8n activepieces huginn node-red",
        ],
        "topics": ["workflow-automation", "automation", "integration", "n8n", "zapier-alternative"],
        "known_repos": [
            "n8n-io/n8n",
            "activepieces/activepieces",
            "huginn/huginn",
            "node-red/node-red",
        ],
        "core_features": ["Hundreds of app connectors", "Visual drag-and-drop builder", "Webhook triggers", "Self-hostable"],
    },
    # Cloud, Hosting & Infra
    "vercel": {
        "name": "Vercel / Heroku / Netlify",
        "category": "PaaS & App Deployment Platform",
        "aliases": ["vercel", "heroku", "netlify", "render"],
        "queries": [
            "self-hosted paas deploy git push docker containers",
            "coolify dokku caprover kamal",
        ],
        "topics": ["paas", "self-hosted", "deployment", "devops", "docker"],
        "known_repos": [
            "coollabsio/coolify",
            "dokku/dokku",
            "caprover/caprover",
            "basecamp/kamal",
        ],
        "core_features": ["Git push to deploy", "Automatic SSL / Let's Encrypt", "Database provisioning", "Zero vendor markup"],
    },
    "datadog": {
        "name": "Datadog / New Relic",
        "category": "Observability, APM & Metrics",
        "aliases": ["datadog", "new relic"],
        "queries": [
            "open-source apm metrics distributed tracing logs",
            "signoz prometheus grafana open-telemetry",
        ],
        "topics": ["observability", "apm", "monitoring", "opentelemetry", "metrics"],
        "known_repos": [
            "SigNoz/signoz",
            "prometheus/prometheus",
            "grafana/grafana",
            "louislam/uptime-kuma",
        ],
        "core_features": ["OpenTelemetry native", "Traces, metrics and logs", "Alerting dashboards", "Self-hosted storage"],
    },
    "firebase": {
        "name": "Firebase",
        "category": "Backend-as-a-Service (BaaS)",
        "aliases": ["firebase"],
        "queries": [
            "open source backend as a service postgres auth realtime storage",
            "supabase appwrite pocketbase",
        ],
        "topics": ["baas", "backend", "postgres", "auth", "realtime"],
        "known_repos": [
            "supabase/supabase",
            "appwrite/appwrite",
            "pocketbase/pocketbase",
        ],
        "core_features": ["Auth & social logins", "Database & realtime subscriptions", "File storage", "Edge functions"],
    },
    "algolia": {
        "name": "Algolia",
        "category": "Instant Search Engine API",
        "aliases": ["algolia"],
        "queries": [
            "fast typo-tolerant search engine api",
            "meilisearch typesense",
        ],
        "topics": ["search-engine", "full-text-search", "meilisearch", "typesense"],
        "known_repos": [
            "meilisearch/meilisearch",
            "typesense/typesense",
        ],
        "core_features": ["Typo tolerance", "Sub-50ms instant results", "Faceted filtering", "Lightweight binary"],
    },
    "pinecone": {
        "name": "Pinecone",
        "category": "Managed Vector Database",
        "aliases": ["pinecone"],
        "queries": [
            "vector database embeddings similarity search hnsw",
            "qdrant milvus chroma weaviate",
        ],
        "topics": ["vector-database", "vector-search", "embeddings", "similarity-search"],
        "known_repos": [
            "qdrant/qdrant",
            "chroma-core/chroma",
            "milvus-io/milvus",
            "weaviate/weaviate",
        ],
        "core_features": ["Fast HNSW vector search", "Payload filtering", "Local or self-hosted deployment"],
    },
    # Design & Creative
    "figma": {
        "name": "Figma / Canva",
        "category": "Collaborative UI & Vector Design",
        "aliases": ["figma", "canva"],
        "queries": [
            "open source design and prototyping tool multi-user vector",
            "penpot excalidraw",
        ],
        "topics": ["design-tool", "ui-design", "prototyping", "vector-graphics"],
        "known_repos": [
            "penpot/penpot",
            "excalidraw/excalidraw",
        ],
        "core_features": ["Vector graphic editor", "Web-based collaborative canvas", "Design tokens & components"],
    },
}


# =============================================================================
# Tailored Alternative Search & Fit Scorer
# =============================================================================

class FindAlternativesArgs(BaseModel):
    paid_product: str = Field(max_length=100, description="Name of the paid product, e.g. 'Notion', 'Postman', 'Docker Desktop', or a category")
    os: OSName = Field("linux", description="Target OS the user runs: macos, linux or windows")
    habits: list[str] | None = Field(None, max_length=10, description="User habits: 'cli-first', 'keyboard-driven', 'native-gui', 'local-first', 'self-hosted-docker', 'lightweight'")
    installed_software: list[str] | None = Field(None, max_length=30, description="Software or tools present in user's workflow, e.g. 'brew', 'docker', 'cargo'")
    license_kinds: list[LicenseKind] | None = Field(None, description="Optional license filter (e.g. ['permissive'])")
    min_stars: int | None = Field(None, description="Minimum stars threshold")
    limit: int = Field(8, ge=1, le=25, description="Number of alternatives to return")


def _classify_form_factor(repo: dict, readme: str) -> FormFactor:
    """Classify the user-facing form factor of the open-source software."""
    topics = [t.lower() for t in (repo.get("topics") or [])]
    desc = (repo.get("description") or "").lower()
    readme_lower = readme.lower()
    lang = (repo.get("language") or "").lower()

    if any(t in ("tui", "cli", "terminal", "command-line") for t in topics) or \
       any(w in desc for w in ("command-line", "terminal ui", "cli tool", "terminal client")):
        return "cli_tui"

    if lang in ("swift", "objective-c") or "swiftui" in readme_lower or "cocoa" in readme_lower:
        return "native_gui"

    if any(t in ("tauri", "electron", "flutter", "qt", "gtk") for t in topics) or \
       any(w in readme_lower for w in ("download .dmg", "download .exe", "appimage", ".deb", ".rpm", "releases/download")):
        return "desktop_cross_platform"

    if any(t in ("self-hosted", "web-app", "docker", "webui", "dashboard") for t in topics) or \
       any(w in readme_lower for w in ("docker-compose", "docker run", "helm chart", "http://localhost")):
        return "self_hosted_web"

    if any(t in ("plugin", "extension", "vim-plugin", "neovim-plugin", "vscode-extension") for t in topics):
        return "editor_plugin"

    if any(t in ("library", "sdk", "framework") for t in topics):
        return "library_sdk"

    return "unknown"


def _check_os_compatibility(os_name: OSName, repo: dict, readme: str) -> tuple[bool, list[str]]:
    """Determine if repo supports target OS and return positive evidence."""
    lang = (repo.get("language") or "").lower()
    readme_lower = readme.lower()
    evidence: list[str] = []

    # Swift / ObjC is macOS native
    if os_name == "macos" and lang in ("swift", "objective-c"):
        evidence.append("Native macOS language (Swift / Objective-C)")

    # Explicit OS indicators in README
    if os_name == "macos":
        if any(w in readme_lower for w in ("brew install", "homebrew", "macos", "darwin", ".dmg")):
            evidence.append("Homebrew / macOS dmg / Darwin instructions present")
    elif os_name == "linux":
        if any(w in readme_lower for w in ("apt install", "pacman", "appimage", ".deb", ".rpm", "linux", "systemd")):
            evidence.append("Linux package / AppImage / systemd instructions present")
    elif os_name == "windows":
        if any(w in readme_lower for w in ("winget", "scoop", "choco", ".exe", ".msi", "windows", "powershell")):
            evidence.append("Windows installer / winget / PowerShell instructions present")

    # Docker / Web / Cross-platform runtimes support all OS
    if any(w in readme_lower for w in ("docker run", "docker-compose", "docker pull")):
        evidence.append("Docker container execution available on all platforms")

    if lang in ("python", "go", "rust", "typescript", "javascript"):
        evidence.append(f"Cross-platform {lang.capitalize()} runtime")

    compatible = len(evidence) > 0
    return compatible, evidence


def _extract_tailored_install(
    repo_name: str,
    readme: str,
    os_name: OSName,
    installed_pkg_mgrs: list[str],
) -> str | None:
    """Extract or formulate the exact install command matching user's installed package managers."""
    slug = repo_name.split("/")[1].lower() if "/" in repo_name else repo_name.lower()
    readme_lines = readme.split("\n")

    # 1. Homebrew on macOS / Linux
    if "brew" in installed_pkg_mgrs and os_name in ("macos", "linux"):
        for line in readme_lines:
            m = re.search(r"brew\s+install\s+(?:--cask\s+)?([a-zA-Z0-9_\-\/@]+)", line, re.IGNORECASE)
            if m:
                return m.group(0).strip()
        # Fallback heuristic
        if os_name == "macos":
            return f"brew install {slug}"

    # 2. Docker / Containers
    if any(p in installed_pkg_mgrs for p in ("docker", "podman", "orbstack", "colima")):
        for i, line in enumerate(readme_lines[:150]):
            if "docker run" in line.lower():
                clean = line.strip().strip("`$# ")
                if len(clean) < 120:
                    return clean
        for line in readme_lines[:150]:
            if "docker-compose up" in line.lower():
                return "docker compose up -d"

    # 3. Cargo (Rust)
    if "cargo" in installed_pkg_mgrs:
        for line in readme_lines[:120]:
            if "cargo install" in line.lower():
                return line.strip().strip("`$# ")

    # 4. uv / pipx (Python)
    if "uv" in installed_pkg_mgrs:
        for line in readme_lines[:120]:
            if "pip install" in line.lower():
                pkg = re.search(r"pip\s+install\s+([a-zA-Z0-9_\-]+)", line)
                if pkg:
                    return f"uv tool install {pkg.group(1)}"

    # 5. npm / bun / pnpm
    if "npm" in installed_pkg_mgrs or "bun" in installed_pkg_mgrs:
        for line in readme_lines[:120]:
            if "npm install -g" in line.lower() or "npx " in line.lower():
                return line.strip().strip("`$# ")

    # 6. Windows winget / scoop
    if os_name == "windows":
        if "winget" in installed_pkg_mgrs:
            for line in readme_lines[:120]:
                if "winget install" in line.lower():
                    return line.strip().strip("`$# ")
            return f"winget install {slug}"
        if "scoop" in installed_pkg_mgrs:
            for line in readme_lines[:120]:
                if "scoop install" in line.lower():
                    return line.strip().strip("`$# ")

    # Fallback to git clone
    return f"git clone https://github.com/{repo_name}.git"


def find_oss_alternatives(
    db: ReadDb,
    args: FindAlternativesArgs,
) -> dict[str, Any]:
    """Find, rank, and articulate open-source alternatives for a paid product."""
    # 1. The caller's own setup (the server never inspects its own machine)
    target_os: OSName = args.os
    user_habits: list[str] = args.habits if args.habits is not None else ["cli-first"]
    installed_software: list[str] = args.installed_software or []
    installed_pkg_ids = installed_software

    target_query = args.paid_product.strip()
    target_clean = re.sub(r"[^\w\s]", "", target_query.lower())

    # 2. Check if product matches our curated catalog
    catalog_hit: dict[str, Any] | None = None
    for key, item in PAID_PRODUCT_CATALOG.items():
        if key == target_clean or item["name"].lower() == target_clean or any(a in target_clean for a in item["aliases"]):
            catalog_hit = item
            break

    # 3. Candidate Gatherer
    candidate_slugs: list[str] = []
    if catalog_hit:
        candidate_slugs.extend(catalog_hit.get("known_repos", []))

    # Multi-angle search queries
    queries_to_run = []
    if catalog_hit:
        queries_to_run.extend(catalog_hit["queries"])
    else:
        queries_to_run.extend([
            f"open source alternative to {target_query}",
            f"{target_query} alternative self-hosted",
            f"{target_query}",
        ])

    filters = rq.RepoFilters(
        license_kinds=args.license_kinds or [],
        min_stars=args.min_stars,
    )

    gathered_dtos: dict[str, dict] = {}

    # Seed known repos from catalog
    if candidate_slugs:
        for slug in candidate_slugs:
            d = rq.repo_detail(db, slug)
            if d:
                gathered_dtos[d["full_name"]] = d

    # Run hybrid searches for remaining candidates
    for q_text in queries_to_run:
        hits = search(db, q_text, filters, limit=20)
        for h in hits:
            fn = h["full_name"]
            if fn not in gathered_dtos:
                gathered_dtos[fn] = h
        if len(gathered_dtos) >= 25:
            break

    # 4. Filter, score, and rank each candidate
    evaluated_candidates: list[dict[str, Any]] = []

    for fn, dto in gathered_dtos.items():
        # Prevent non-software artifacts
        art = classify_artifact(db, fn)
        if art["kind"] in ("awesome_list", "course", "dataset", "model"):
            continue

        readme = dto.get("readme") or ""
        form_factor = _classify_form_factor(dto, readme)
        os_compat, os_evidence = _check_os_compatibility(target_os, dto, readme)

        # Baseline score calculation (0 - 100)
        base_score = 65.0

        # Known curated matches get high confidence boost
        if catalog_hit and fn in catalog_hit.get("known_repos", []):
            base_score += 15.0

        # Star popularity & velocity (logarithmic contribution)
        stars = dto.get("stars") or 0
        if stars >= 20000:
            base_score += 10.0
        elif stars >= 5000:
            base_score += 7.0
        elif stars >= 1000:
            base_score += 4.0

        gain_1d = dto.get("gain_1d")
        gain_7d = dto.get("gain_7d")
        if gain_1d and gain_1d > 10:
            base_score += 4.0
        elif gain_7d and gain_7d > 50:
            base_score += 3.0

        habit_reasons: list[str] = []
        workflow_synergies: list[str] = []

        # Habit alignment scoring
        if "cli-first" in user_habits:
            if form_factor == "cli_tui":
                base_score += 12.0
                habit_reasons.append("Terminal / TUI interface perfectly aligns with your CLI-first habit.")
            elif form_factor in ("desktop_cross_platform", "native_gui"):
                base_score -= 5.0

        if "keyboard-driven" in user_habits:
            readme_low = readme.lower()
            if any(w in readme_low for w in ("vim", "keybinding", "shortcut", "modal", "j/k", "hotkey")):
                base_score += 8.0
                habit_reasons.append("Vim / keyboard shortcuts supported out-of-the-box.")

        if "native-gui" in user_habits:
            if form_factor in ("native_gui", "desktop_cross_platform"):
                base_score += 12.0
                habit_reasons.append("Desktop graphical interface matches your preference for native GUI apps.")
            elif form_factor == "cli_tui":
                base_score -= 8.0

        if "self-hosted-docker" in user_habits:
            if "docker" in readme.lower() or form_factor == "self_hosted_web":
                base_score += 10.0
                habit_reasons.append("Self-hosted Docker deployment supported with container compose templates.")

        if "local-first" in user_habits:
            readme_low = readme.lower()
            if any(w in readme_low for w in ("local-first", "offline", "sqlite", "git sync", "no account")):
                base_score += 10.0
                habit_reasons.append("Local-first storage: your data stays on your machine with zero cloud lock-in.")

        # Workflow tool synergies
        installed_set = set(installed_software)
        if "nvim" in installed_set and ("neovim" in readme.lower() or "lua" in (dto.get("language") or "").lower()):
            workflow_synergies.append("Integrates directly with your Neovim config.")
        if "tmux" in installed_set and form_factor == "cli_tui":
            workflow_synergies.append("Runs seamlessly inside your tmux sessions.")
        if "docker" in installed_set and "docker" in readme.lower():
            workflow_synergies.append("Ready to launch instantly via your local Docker daemon.")
        if "ollama" in installed_set and "ollama" in readme.lower():
            workflow_synergies.append("Connects with your local Ollama LLM runtime for private AI.")
        if "brew" in installed_set and "brew" in readme.lower():
            workflow_synergies.append("1-line install available via Homebrew.")

        # OS compatibility penalty/boost
        if os_compat:
            base_score += 4.0
        else:
            base_score -= 20.0
            habit_reasons.append(f"Warning: Primary documentation does not emphasize {target_os.capitalize()} support.")

        fit_score = max(20, min(99, int(round(base_score))))

        # Badge assignment
        fit_badge: FitBadge = "Viable Contender"
        if fit_score >= 90:
            if form_factor == "cli_tui" and "cli-first" in user_habits:
                fit_badge = "Best CLI / Terminal Match"
            elif form_factor in ("native_gui", "desktop_cross_platform") and "native-gui" in user_habits:
                fit_badge = "Best Native GUI Match"
            elif "local-first" in user_habits and any("local-first" in r.lower() for r in habit_reasons):
                fit_badge = "Best Local-First Match"
            elif "self-hosted-docker" in user_habits and form_factor == "self_hosted_web":
                fit_badge = "Best Self-Hosted Match"
            else:
                fit_badge = "Best Overall Match"
        elif fit_score >= 80:
            fit_badge = "Strong Alternative"

        # Tailored install command
        install_cmd = _extract_tailored_install(fn, readme, target_os, installed_pkg_ids)

        # Tradeoffs statement
        tradeoffs = (
            "Requires local/container setup and self-maintenance compared to the proprietary cloud service."
            if form_factor == "self_hosted_web"
            else "Community-driven project; specialized enterprise plugins or cloud sync may require extra configuration."
        )

        evaluated_candidates.append({
            "full_name": fn,
            "stars": dto.get("stars"),
            "forks": dto.get("forks"),
            "language": dto.get("language"),
            "license": dto.get("license"),
            "license_kind": dto.get("license_kind") or license_kind(dto.get("license")),
            "description": dto.get("description"),
            "homepage": dto.get("homepage"),
            "gain_1d": dto.get("gain_1d"),
            "gain_7d": dto.get("gain_7d"),
            "form_factor": form_factor,
            "os_compatible": os_compat,
            "os_evidence": os_evidence,
            "fit_score": fit_score,
            "fit_badge": fit_badge,
            "habit_reasons": habit_reasons,
            "workflow_synergies": workflow_synergies,
            "tailored_install_command": install_cmd,
            "tradeoffs": tradeoffs,
        })

    # Sort candidates by fit_score descending
    evaluated_candidates.sort(key=lambda c: (-c["fit_score"], -(c.get("stars") or 0)))
    top_candidates = evaluated_candidates[:args.limit]

    # Articulation Guide for the LLM
    best_overall = top_candidates[0] if top_candidates else None
    cli_picks = [c for c in top_candidates if c["form_factor"] == "cli_tui"]
    gui_picks = [c for c in top_candidates if c["form_factor"] in ("native_gui", "desktop_cross_platform", "self_hosted_web")]

    articulation_guide = {
        "best_overall_pick": best_overall["full_name"] if best_overall else None,
        "best_cli_pick": cli_picks[0]["full_name"] if cli_picks else None,
        "best_gui_pick": gui_picks[0]["full_name"] if gui_picks else None,
        "summary": (
            f"For {args.paid_product} on {target_os.capitalize()} with {', '.join(user_habits[:3])} workflow: "
            f"Top recommendation is {best_overall['full_name']} ({best_overall['fit_score']}% fit)."
            if best_overall else f"No immediate direct match for {args.paid_product}."
        ),
    }

    as_of = db.as_of or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "paid_product": catalog_hit["name"] if catalog_hit else args.paid_product,
        "category": catalog_hit["category"] if catalog_hit else "Commercial Software",
        "target_os": target_os,
        "user_habits": user_habits,
        "installed_software": installed_software[:15],
        "alternatives_count": len(top_candidates),
        "alternatives": top_candidates,
        "articulation_guide": articulation_guide,
        "as_of": as_of,
        "data_coverage": "complete" if top_candidates else "partial",
        "sources": ["PAID_PRODUCT_CATALOG", "repos", "chunks", "local_environment"],
    }
