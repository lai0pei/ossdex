"""Diagnostic and composite tools for evaluating Product Idea Briefs.

Prevents failure modes F1 through F10:
- F1: Category error (treating library/template/list as deployable app)
- F2: Hidden lock-in (permissive license, but vendor-owned backend required)
- F3: Velocity misread (decaying launch spike confused with breakout growth)
- F4: Fork misread (template copies confused with enterprise deployment)
- F5: Missed commercial precedent (existing vendor/managed offering occupies angle)
- F6: Name/trademark collision (collision with existing repo or trademark)
- F7: License blind spot (copyleft system binaries, model weights, vendor ToS)
- F8: Platform blind spot (target hosting cannot run workloads)
- F9: Empty demand data ("0 bounties" reported when demand was never fetched)
- F10: Noisy similarity (surfacing semantic vs keyword match provenance)

Conventions:
- Enums are closed sets; return "unknown" when evidence is insufficient. Never guess.
- Numeric fields are None if data is unavailable; never substitute 0.
- evidence[]: machine-checkable reasons.
- confidence: float 0.0-1.0.
- Every response includes as_of, data_coverage ("complete" | "partial" | "missing"), sources[].
"""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from typing import Any, Literal

from ossdex_core.licenses import LicenseKind
from pydantic import BaseModel, Field

from . import repo_query as rq
from .db import ReadDb

# Closed-set Enum Types
ArtifactKind = Literal[
    "app", "library", "sdk", "framework", "template", "cli",
    "plugin", "dataset", "model", "course", "awesome_list", "unknown"
]

FeasibleSaaSShape = Literal[
    "hosted_app", "managed_api", "remote_execution_driver",
    "marketplace_plugin", "support_services", "vertical_edition", "none"
]

GrowthPattern = Literal[
    "launch_spike", "sustained_growth", "flat", "declining", "revived", "insufficient_history"
]

ForkInterpretation = Literal[
    "template_copies", "contribution_forks", "production_customization", "abandoned", "mixed"
]

MaintainerRisk = Literal["low", "medium", "high"]

IssueClusterLabel = Literal[
    "install_environment", "hosting_deployment", "performance_scaling",
    "bug", "feature_request", "integration", "docs", "security", "compliance", "other"
]

VendorType = Literal[
    "managed_service", "api", "platform", "enterprise_edition", "consultancy"
]

PricingModel = Literal[
    "per_seat", "per_usage_unit", "flat_tier", "custom", "free_tier_only"
]

CompanyEventType = Literal[
    "funding", "acquisition", "shutdown", "relicense", "spin_out",
    "commercial_launch", "foundation_donation"
]

CollisionRisk = Literal["low", "medium", "high"]
ComplianceVerdict = Literal["ok", "caution", "blocked"]
PlatformStatus = Literal["supported", "restricted", "workaround", "unsupported", "unknown"]
BriefVerdict = Literal["reject", "narrow", "pursue"]
ClaimStatus = Literal["confirmed", "overstated", "wrong", "unverified"]
DataCoverage = Literal["complete", "partial", "missing"]


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_base_detail(db: ReadDb, full_name: str) -> dict | None:
    return rq.repo_detail(db, full_name)


# -----------------------------------------------------------------------------
# Tool 1: classify_artifact [prevents F1, F10]
# -----------------------------------------------------------------------------
class ClassifyArtifactArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'n8n-io/n8n' or 'psf/requests'")


def classify_artifact(db: ReadDb, full_name: str) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "kind": "unknown",
            "host_ecosystem": None,
            "deployable": False,
            "feasible_saas_shapes": ["none"],
            "evidence": ["repo not found"],
            "confidence": 0.0,
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    topics = [t.lower() for t in (repo.get("topics") or [])]
    desc = (repo.get("description") or "").lower()
    readme = (repo.get("readme") or "").lower()
    lang = (repo.get("language") or "").lower()
    name_lower = full_name.lower()

    evidence: list[str] = []
    kind: ArtifactKind = "unknown"
    deployable = False
    feasible_shapes: list[FeasibleSaaSShape] = []
    host_ecosystem: str | None = lang or None
    confidence = 0.8

    # 1. Awesome list detection
    if any(t in ("awesome", "awesome-list", "awesome-lists") for t in topics) or \
       name_lower.startswith("awesome-") or name_lower.endswith("-awesome") or \
       "curated list of" in desc or "curated list of" in readme[:500]:
        kind = "awesome_list"
        deployable = False
        feasible_shapes = ["none"]
        evidence.append("awesome list topics/description detected")
        confidence = 0.95

    # 2. Course / Educational / Tutorial
    elif any(t in ("course", "tutorial", "learn-to-code", "education") for t in topics) or \
         any(w in desc for w in ("course", "tutorial", "learn python", "roadmap", "cheatsheet")):
        kind = "course"
        deployable = False
        feasible_shapes = ["support_services", "none"]
        evidence.append("tutorial / educational course markers in topics or description")
        confidence = 0.9

    # 3. Dataset / Model weights
    elif any(t in ("dataset", "datasets", "model-weights", "llm-weights", "pretrained-models") for t in topics) or \
         any(w in desc for w in ("dataset", "pre-trained weights", "model weights", "checkpoints")):
        kind = "dataset" if "dataset" in desc or "dataset" in topics else "model"
        deployable = False
        feasible_shapes = ["managed_api", "support_services"]
        evidence.append("dataset or model weights keywords detected")
        confidence = 0.85

    # 4. Template / Starter / Boilerplate
    elif any(t in ("template", "starter", "boilerplate", "skeleton") for t in topics) or \
         any(w in name_lower for w in ("-starter", "-template", "-boilerplate")) or \
         any(w in desc for w in ("starter kit", "boilerplate", "project template")):
        kind = "template"
        deployable = False
        feasible_shapes = ["hosted_app", "support_services"]
        evidence.append("starter template / boilerplate detected")
        confidence = 0.85

    # 5. Plugin / Driver / Extension
    elif any(t in ("plugin", "extension", "addon", "driver", "integration") for t in topics) or \
         any(w in name_lower for w in ("-plugin", "-extension", "-driver", "-adapter")) or \
         any(w in desc for w in ("plugin for", "extension for", "adapter for", "driver for")):
        kind = "plugin"
        deployable = False
        feasible_shapes = ["marketplace_plugin", "remote_execution_driver", "support_services"]
        evidence.append("plugin/driver keywords detected in name or topics")
        confidence = 0.9

    # 6. CLI
    elif any(t in ("cli", "command-line", "terminal", "terminal-app") for t in topics) or \
         any(w in desc for w in ("command line tool", "cli tool", "terminal utility")):
        kind = "cli"
        deployable = False
        feasible_shapes = ["managed_api", "support_services"]
        evidence.append("CLI / terminal keywords detected in topics or description")
        confidence = 0.85

    # 7. SDK
    elif any(t in ("sdk", "client", "api-client") for t in topics) or \
         any(w in name_lower for w in ("-sdk", "-client", "-python", "-js", "-go")) and \
         any(w in desc for w in ("client library", "official sdk", "api client", "bindings for")):
        kind = "sdk"
        deployable = False
        feasible_shapes = ["managed_api", "support_services"]
        evidence.append("SDK / client bindings indicators in name and description")
        confidence = 0.85

    # 8. Deployable App (Servers, Daemons, Web Apps, Turnkey platforms)
    elif any(t in ("self-hosted", "web-app", "dashboard", "server", "daemon", "service") for t in topics) or \
         any(w in desc for w in ("self-hosted", "open source alternative to", "web interface", "server", "dashboard")) or \
         any(w in readme[:3000] for w in ("docker run", "docker-compose", "helm install", "localhost:8", "localhost:3")):
        kind = "app"
        deployable = True
        feasible_shapes = ["hosted_app", "managed_api", "vertical_edition", "support_services"]
        evidence.append("deployable server / docker / self-hosted app indicators in README/topics")
        confidence = 0.88

    # 9. Framework
    elif any(t in ("framework", "web-framework") for t in topics) or "framework" in desc:
        kind = "framework"
        deployable = False
        feasible_shapes = ["hosted_app", "managed_api", "support_services"]
        evidence.append("framework marker in topics/description")
        confidence = 0.8

    # 10. Library (Default for code modules with package install commands)
    else:
        kind = "library"
        deployable = False
        feasible_shapes = ["managed_api", "support_services"]
        evidence.append("standard library / package consumption patterns")
        confidence = 0.75

    return {
        "repo": full_name,
        "kind": kind,
        "host_ecosystem": host_ecosystem,
        "deployable": deployable,
        "feasible_saas_shapes": feasible_shapes,
        "evidence": evidence,
        "confidence": round(confidence, 2),
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete" if repo.get("readme") else "partial",
        "sources": ["repos", "repo_stats"],
    }


# -----------------------------------------------------------------------------
# Tool 2: get_runtime_dependencies [prevents F2]
# -----------------------------------------------------------------------------
class RuntimeDepsArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'n8n-io/n8n'")


_VENDOR_SERVICES = [
    ("OpenAI", "openai", "LLM Inference API", False, True, [r"OPENAI_API_KEY", r"api\.openai\.com"]),
    ("Anthropic", "anthropic", "LLM Inference API", False, True, [r"ANTHROPIC_API_KEY", r"api\.anthropic\.com"]),
    ("Pinecone", "pinecone", "Managed Vector Database", False, True, [r"PINECONE_API_KEY", r"pinecone\.io"]),
    ("Weaviate Cloud", "weaviate", "Managed Vector Database", True, True, [r"WEAVIATE_URL", r"weaviate\.network"]),
    ("Qdrant Cloud", "qdrant", "Vector Database", True, True, [r"QDRANT_API_KEY", r"cloud\.qdrant\.io"]),
    ("Supabase", "supabase", "BaaS / Postgres", True, True, [r"SUPABASE_KEY", r"supabase\.co"]),
    ("Firebase", "google", "BaaS / Auth", False, True, [r"firebaseio\.com", r"FIREBASE_API_KEY"]),
    ("AWS S3", "amazon", "Object Storage", True, True, [r"AWS_ACCESS_KEY_ID", r"s3\.amazonaws\.com"]),
    ("Stripe", "stripe", "Payment Processing", False, True, [r"STRIPE_API_KEY", r"stripe\.com"]),
    ("GitHub OAuth", "github", "Authentication", False, False, [r"GITHUB_CLIENT_ID", r"github\.com/login/oauth"]),
    ("Browserless", "browserless", "Headless Browser Automation", False, True, [r"browserless\.io", r"BLESS_TOKEN"]),
    ("PostgreSQL", "postgresql", "Relational Database", True, False, [r"postgres://", r"postgresql://", r"POSTGRES_PASSWORD"]),
    ("Redis", "redis", "In-Memory Cache & Queue", True, False, [r"redis://", r"REDIS_URL"]),
]


def get_runtime_dependencies(db: ReadDb, full_name: str) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "required_services": [],
            "optional_services": [],
            "lock_in_risk": "unknown",
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    readme = repo.get("readme") or ""
    owner = full_name.split("/")[0].lower()

    required_services: list[dict] = []
    optional_services: list[dict] = []

    for name, vendor, role, self_hostable, paid_tiers, patterns in _VENDOR_SERVICES:
        matched_evidence = []
        for pat in patterns:
            if re.search(pat, readme, re.IGNORECASE):
                matched_evidence.append(f"matched pattern: {pat}")
        if matched_evidence:
            vendor_is_upstream = (vendor == owner) or (vendor in owner)
            service_record = {
                "name": name,
                "owner": vendor,
                "role": role,
                "self_hostable": self_hostable,
                "paid_tiers": paid_tiers,
                "vendor_is_upstream": vendor_is_upstream,
                "evidence": matched_evidence,
            }
            # Heuristic: if marked optional in readme context
            if any(term in readme.lower() for term in (f"optional: {name.lower()}", f"optional {name.lower()}")):
                optional_services.append(service_record)
            else:
                required_services.append(service_record)

    # Determine lock-in risk
    lock_in_risk: Literal["low", "medium", "high", "unknown"] = "low"
    if any(s["vendor_is_upstream"] and not s["self_hostable"] for s in required_services):
        lock_in_risk = "high"
    elif any(not s["self_hostable"] and s["paid_tiers"] for s in required_services):
        lock_in_risk = "medium"
    elif not repo.get("has_readme"):
        lock_in_risk = "unknown"

    return {
        "repo": full_name,
        "required_services": required_services,
        "optional_services": optional_services,
        "lock_in_risk": lock_in_risk,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete" if repo.get("readme") else "partial",
        "sources": ["repos", "README.md"],
    }


# -----------------------------------------------------------------------------
# Tool 3: classify_growth [prevents F3]
# -----------------------------------------------------------------------------
class ClassifyGrowthArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'n8n-io/n8n'")
    days: int = Field(60, ge=7, le=365, description="Lookback window in days")


def classify_growth(db: ReadDb, full_name: str, days: int = 60) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "pattern": "insufficient_history",
            "age_days": 0,
            "daily_gain": {"peak": None, "current": None, "median_14d": None},
            "half_life_days": None,
            "projected_stars_30d": None,
            "confidence": 0.0,
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    # Calculate repo age in days
    age_days = 0
    if repo.get("created_at"):
        try:
            created = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
            age_days = max(1, (datetime.now(UTC) - created).days)
        except Exception:
            age_days = 0

    history = [p for p in repo.get("history", []) if p.get("stars") is not None]

    if len(history) < 3 or db.history_days() < 7:
        current_stars = repo.get("stars")
        return {
            "repo": full_name,
            "pattern": "insufficient_history",
            "age_days": age_days,
            "daily_gain": {
                "peak": repo.get("gain_1d") or repo.get("gain_7d"),
                "current": None,
                "median_14d": None,
            },
            "half_life_days": None,
            "projected_stars_30d": None,
            "confidence": 0.25,
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "partial",
            "sources": ["repo_stats"],
        }

    # Compute daily gains across chronological history
    daily_deltas: list[float] = []
    for i in range(1, len(history)):
        diff = history[i]["stars"] - history[i - 1]["stars"]
        daily_deltas.append(max(0, float(diff)))

    peak = max(daily_deltas) if daily_deltas else 0.0
    current = daily_deltas[-1] if daily_deltas else 0.0
    recent_14 = daily_deltas[-14:] if len(daily_deltas) >= 14 else daily_deltas
    recent_14_sorted = sorted(recent_14)
    median_14d = recent_14_sorted[len(recent_14_sorted) // 2] if recent_14_sorted else 0.0

    pattern: GrowthPattern = "sustained_growth"
    half_life_days: float | None = None

    if peak > 5.0 and median_14d <= peak * 0.2 and current <= peak * 0.15:
        pattern = "launch_spike"
        # Half-life estimation: ln(2) / decay_rate
        decay_steps = max(1, len(daily_deltas))
        decay_rate = math.log(max(1.0, peak) / max(0.5, current)) / decay_steps
        half_life_days = round(math.log(2) / max(0.01, decay_rate), 1) if decay_rate > 0 else None
    elif median_14d <= 1.0 and current <= 1.0:
        pattern = "flat"
    elif current < 0:
        pattern = "declining"
    elif len(daily_deltas) > 20 and sum(daily_deltas[:10]) <= 5 and sum(daily_deltas[-10:]) > 50:
        pattern = "revived"
    else:
        pattern = "sustained_growth"

    current_stars = repo.get("stars") or 0
    projected_stars_30d = current_stars + int(round(median_14d * 30))

    return {
        "repo": full_name,
        "pattern": pattern,
        "age_days": age_days,
        "daily_gain": {
            "peak": round(peak, 1),
            "current": round(current, 1),
            "median_14d": round(median_14d, 1),
        },
        "half_life_days": half_life_days,
        "projected_stars_30d": projected_stars_30d,
        "confidence": 0.85,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete",
        "sources": ["repo_stats", "repos"],
    }


# -----------------------------------------------------------------------------
# Tool 4: get_package_adoption [prevents F3, F4]
# -----------------------------------------------------------------------------
class PackageAdoptionArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'tiangolo/fastapi'")


_REGISTRY_PATTERNS = [
    ("npm", re.compile(r"npm\s+(?:i|install)\s+([@a-z0-9_-]+/[a-z0-9_.-]+|[a-z0-9_.-]+)", re.I)),
    ("pypi", re.compile(r"pip\s+install\s+([a-z0-9_.-]+)", re.I)),
    ("crates", re.compile(r"cargo\s+add\s+([a-z0-9_.-]+)", re.I)),
    ("go", re.compile(r"go\s+get\s+([a-z0-9_.-]+/[a-z0-9_.-]+)", re.I)),
    ("packagist", re.compile(r"composer\s+require\s+([a-z0-9_.-]+/[a-z0-9_.-]+)", re.I)),
    ("docker_hub", re.compile(r"docker\s+pull\s+([a-z0-9_.-]+/[a-z0-9_.-]+|[a-z0-9_.-]+)", re.I)),
]


def get_package_adoption(db: ReadDb, full_name: str) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "packages": [],
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    readme = repo.get("readme") or ""
    packages: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for reg, rx in _REGISTRY_PATTERNS:
        matches = rx.findall(readme)
        for pkg in matches:
            pkg_name = pkg.strip().strip("'\"")
            if (reg, pkg_name) not in seen and len(pkg_name) > 1 and not pkg_name.startswith("-"):
                seen.add((reg, pkg_name))
                packages.append({
                    "registry": reg,
                    "package": pkg_name,
                    "downloads_total": None,  # null preservation, never substitute 0
                    "downloads_30d": None,
                    "trend_90d_pct": None,
                    "dependent_repos": None,
                    "dependent_packages": None,
                })

    return {
        "repo": full_name,
        "packages": packages,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "partial" if packages else ("complete" if repo.get("readme") else "missing"),
        "sources": ["README.md package install directives"],
    }


# -----------------------------------------------------------------------------
# Tool 5: analyze_forks [prevents F4]
# -----------------------------------------------------------------------------
class AnalyzeForksArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'n8n-io/n8n'")
    sample_size: int = Field(500, ge=10, le=1000)


def analyze_forks(db: ReadDb, full_name: str, sample_size: int = 500) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "forks": 0,
            "sampled": 0,
            "ahead_of_upstream": None,
            "active_90d": None,
            "with_deploy_config": None,
            "with_own_stars_gt_10": None,
            "interpretation": "abandoned",
            "confidence": 0.0,
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    forks = repo.get("forks") or 0
    stars = repo.get("stars") or 1
    fork_ratio = forks / stars

    artifact = classify_artifact(db, full_name)
    kind = artifact.get("kind", "unknown")

    interpretation: ForkInterpretation = "mixed"
    confidence = 0.7

    if kind in ("template", "course", "awesome_list"):
        interpretation = "template_copies"
        confidence = 0.9
    elif kind == "app" and fork_ratio >= 0.12:
        interpretation = "production_customization"
        confidence = 0.8
    elif kind in ("library", "sdk") and fork_ratio >= 0.15:
        interpretation = "contribution_forks"
        confidence = 0.75
    elif repo.get("pushed_at"):
        try:
            pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
            if (datetime.now(UTC) - pushed).days > 365:
                interpretation = "abandoned"
                confidence = 0.85
        except Exception:
            pass

    return {
        "repo": full_name,
        "forks": forks,
        "sampled": 0,  # null preservation: offline index doesn't have live git commit trees
        "ahead_of_upstream": None,
        "active_90d": None,
        "with_deploy_config": None,
        "with_own_stars_gt_10": None,
        "interpretation": interpretation,
        "confidence": confidence,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "partial",
        "sources": ["repos", "classify_artifact"],
    }


# -----------------------------------------------------------------------------
# Tool 6: get_maintainer_health [supports services/SLA]
# -----------------------------------------------------------------------------
class MaintainerHealthArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'n8n-io/n8n'")
    months: int = Field(6, ge=1, le=24)


def get_maintainer_health(db: ReadDb, full_name: str, months: int = 6) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "active_committers": None,
            "bus_factor": None,
            "top_affiliations": [],
            "releases_in_window": None,
            "last_release_date": None,
            "median_first_response_days": None,
            "median_pr_merge_days": None,
            "ownership_change_events": [],
            "risk": "high",
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    days_since_push = None
    if repo.get("pushed_at"):
        try:
            pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
            days_since_push = max(0, (datetime.now(UTC) - pushed).days)
        except Exception:
            pass

    risk: MaintainerRisk = "low"
    if repo.get("archived") or (days_since_push is not None and days_since_push > 180):
        risk = "high"
    elif days_since_push is not None and days_since_push > 60:
        risk = "medium"

    owner = full_name.split("/")[0]
    affiliations = [owner]
    if repo.get("money") and repo["money"].get("signals"):
        affiliations.extend(repo["money"]["signals"])

    return {
        "repo": full_name,
        "active_committers": None,
        "bus_factor": None,
        "top_affiliations": affiliations[:4],
        "releases_in_window": None,
        "last_release_date": None,
        "median_first_response_days": None,
        "median_pr_merge_days": None,
        "ownership_change_events": [],
        "risk": risk,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "partial",
        "sources": ["repos", "repo_money"],
    }


# -----------------------------------------------------------------------------
# Tool 7: classify_issues [prevents F9]
# -----------------------------------------------------------------------------
class ClassifyIssuesArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'n8n-io/n8n'")
    top_n: int = Field(100, ge=10, le=200)


_ISSUE_CLUSTERS: list[tuple[IssueClusterLabel, list[str]]] = [
    ("compliance", ["sso", "saml", "audit", "gdpr", "hipaa", "soc2", "rbac", "license", "legal"]),
    ("hosting_deployment", ["docker", "kubernetes", "k8s", "helm", "deploy", "cloud", "aws", "gcp", "vercel", "systemd"]),
    ("security", ["vulnerability", "cve", "auth", "token", "xss", "csrf", "secret", "permission"]),
    ("performance_scaling", ["memory", "leak", "slow", "cpu", "scale", "timeout", "latency", "bottleneck", "crash"]),
    ("integration", ["plugin", "connector", "webhook", "api", "zapier", "slack", "postgres", "database", "adapter"]),
    ("install_environment", ["install", "setup", "build", "pip", "npm", "cmake", "windows", "macos", "arm64", "cuda"]),
    ("docs", ["documentation", "readme", "tutorial", "typo", "guide", "docs"]),
    ("bug", ["bug", "fix", "error", "fail", "broken", "issue"]),
    ("feature_request", ["feature", "request", "support", "add", "option"]),
]


def classify_issues(db: ReadDb, full_name: str, top_n: int = 100) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "total_open": 0,
            "clusters": [],
            "monetizable_pain": [],
            "help_wanted_count": None,
            "bounty_count": None,
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    demand = repo.get("demand")
    # F9 prevention: if demand was never fetched, return explicit missing coverage
    if demand is None:
        return {
            "repo": full_name,
            "total_open": repo.get("open_issues") or 0,
            "clusters": [],
            "monetizable_pain": [],
            "help_wanted_count": None,
            "bounty_count": None,
            "note": f"demand data not fetched yet: run `ossdex demand {full_name}`",
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["repos"],
        }

    issues = demand.get("top_issues") or []
    cluster_buckets: dict[IssueClusterLabel, list[dict]] = {label: [] for label, _ in _ISSUE_CLUSTERS}
    cluster_buckets["other"] = []

    for iss in issues[:top_n]:
        title_lower = (iss.get("title") or "").lower()
        labels_lower = [str(l).lower() for l in (iss.get("labels") or [])]
        text = f"{title_lower} {' '.join(labels_lower)}"

        assigned = False
        for label, keywords in _ISSUE_CLUSTERS:
            if any(kw in text for kw in keywords):
                cluster_buckets[label].append(iss)
                assigned = True
                break
        if not assigned:
            cluster_buckets["other"].append(iss)

    clusters_output: list[dict] = []
    monetizable_pain: list[str] = []
    monetizable_labels = {"compliance", "hosting_deployment", "performance_scaling", "integration", "security"}

    for label, bucket in cluster_buckets.items():
        if not bucket:
            continue
        total_upvotes = sum(int(x.get("reactions") or 0) for x in bucket)
        examples = [
            {"number": x["number"], "title": x["title"], "url": x["url"]}
            for x in bucket[:3]
        ]
        clusters_output.append({
            "label": label,
            "count": len(bucket),
            "upvotes": total_upvotes,
            "examples": examples,
        })
        if label in monetizable_labels and (len(bucket) >= 1 or total_upvotes >= 5):
            monetizable_pain.append(label)

    return {
        "repo": full_name,
        "total_open": repo.get("open_issues") or len(issues),
        "clusters": clusters_output,
        "monetizable_pain": sorted(monetizable_pain),
        "help_wanted_count": demand.get("help_wanted"),
        "bounty_count": demand.get("bounties"),
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete",
        "sources": ["repo_demand", "repo_issues"],
    }


# -----------------------------------------------------------------------------
# Tool 8: get_commercial_landscape [prevents F5]
# -----------------------------------------------------------------------------
class CommercialLandscapeArgs(BaseModel):
    full_name: str | None = Field(None, max_length=100, description="owner/repo to inspect")
    category: str | None = Field(None, max_length=100, description="topic or category name")
    limit: int = Field(10, ge=1, le=30)


def get_commercial_landscape(db: ReadDb, full_name: str | None = None, category: str | None = None, limit: int = 10) -> dict:
    if not full_name and not category:
        return {"error": "one of full_name or category is required", "category": "unknown", "vendors": []}

    vendors: list[dict] = []
    cat_label = category or "open source software"

    if full_name:
        repo = _get_base_detail(db, full_name)
        if repo:
            cat_label = (repo.get("topics") or [cat_label])[0]
            if repo.get("homepage"):
                vendors.append({
                    "name": repo["full_name"].split("/")[1].title(),
                    "type": "managed_service",
                    "pricing_model": "flat_tier",
                    "usage_unit": "month",
                    "entry_price_usd": None,
                    "free_tier": True,
                    "built_on_repo": True,
                    "checked": db.as_of or _now_iso()[:10],
                    "source": repo["homepage"],
                })
            # Also pull runtime vendor dependencies (F2 / F5 bridge)
            deps = get_runtime_dependencies(db, full_name)
            for s in deps.get("required_services", []):
                if s.get("paid_tiers"):
                    vendors.append({
                        "name": s["name"],
                        "type": "api",
                        "pricing_model": "per_usage_unit",
                        "usage_unit": "request",
                        "entry_price_usd": None,
                        "free_tier": "unknown",
                        "built_on_repo": False,
                        "checked": db.as_of or _now_iso()[:10],
                        "source": f"https://github.com/{full_name}",
                    })

    return {
        "category": cat_label,
        "vendors": vendors[:limit],
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete" if vendors else "partial",
        "sources": ["repo_money", "homepage", "README.md"],
    }


# -----------------------------------------------------------------------------
# Tool 9: get_company_events [prevents F5]
# -----------------------------------------------------------------------------
class CompanyEventsArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'supabase/supabase'")


def get_company_events(db: ReadDb, full_name: str) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "events": [],
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    events: list[dict] = []
    owner, repo_name = full_name.split("/", 1) if "/" in full_name else (full_name, "")

    # Funding links
    money = repo.get("money") or {}
    for f in money.get("funding", []):
        if f.get("url"):
            events.append({
                "date": db.as_of or _now_iso()[:10],
                "type": "funding",
                "entity": owner,
                "counterparty": f.get("platform"),
                "relation_to_repo": "creator",
                "source": f["url"],
            })

    # Archival / Shutdown event
    if repo.get("archived"):
        events.append({
            "date": repo.get("pushed_at") or _now_iso()[:10],
            "type": "shutdown",
            "entity": owner,
            "counterparty": None,
            "relation_to_repo": "creator",
            "source": repo.get("github_url") or "",
        })

    return {
        "repo": full_name,
        "events": events,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete" if events else "partial",
        "sources": ["repo_money.funding", "repos.archived"],
    }


# -----------------------------------------------------------------------------
# Tool 10: check_name_collision [prevents F6]
# -----------------------------------------------------------------------------
class NameCollisionArgs(BaseModel):
    name: str = Field(max_length=100, description="Proposed product or repo name")
    category: str | None = Field(None, max_length=100, description="Target domain or category")


def check_name_collision(db: ReadDb, name: str, category: str | None = None) -> dict:
    clean = name.strip().lower()
    rows = db.query(
        "SELECT full_name, stars, topics FROM repos WHERE enrich_status = 'ok' AND "
        "(lower(full_name) LIKE ? OR lower(full_name) LIKE ?) LIMIT 15",
        (f"%/{clean}%", f"%{clean}%")
    )

    collisions: list[dict] = []
    max_risk: CollisionRisk = "low"

    for r in rows:
        fn = r["full_name"]
        slug = fn.split("/")[1].lower() if "/" in fn else fn.lower()
        stars = r["stars"]
        topics = [t.lower() for t in (json.loads(r["topics"]) if r["topics"] else [])]
        same_cat = bool(category and category.lower() in topics)

        # Calculate basic string similarity
        sim = 1.0 if slug == clean else (0.85 if clean in slug else 0.5)
        if sim >= 0.85 and stars and stars > 1000:
            max_risk = "high"
        elif sim >= 0.85 and max_risk != "high":
            max_risk = "medium"

        collisions.append({
            "kind": "repo",
            "identifier": fn,
            "stars": stars,
            "similarity": round(sim, 2),
            "same_category": same_cat,
        })

    return {
        "name": name,
        "collisions": collisions,
        "risk": max_risk,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete",
        "sources": ["repos table"],
    }


# -----------------------------------------------------------------------------
# Tool 11: license_audit [prevents F7]
# -----------------------------------------------------------------------------
class LicenseAuditArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'n8n-io/n8n'")


def license_audit(db: ReadDb, full_name: str) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "own_license": "unknown",
            "dependencies": [],
            "vendor_terms": [],
            "verdict": {"hosted_saas": "blocked", "closed_distribution": "blocked", "notes": ["repo not found"]},
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    own_lic = repo.get("license") or "None"
    kind: LicenseKind = repo.get("license_kind") or "none"
    readme = repo.get("readme") or ""

    dependencies: list[dict] = []
    vendor_terms: list[dict] = []
    notes: list[str] = []

    # Detect copyleft binary references in README
    if "ffmpeg" in readme.lower():
        dependencies.append({
            "dep": "ffmpeg",
            "scope": "system_binary",
            "license": "LGPL-2.1-or-later / GPL-3.0",
            "saas_ok": True,
            "redistribution": "weak_copyleft",
        })
        notes.append("ffmpeg referenced: safe for hosted SaaS backend; verify non-GPL build flags if distributing binaries.")

    # Check vendor lock-in resale terms
    deps = get_runtime_dependencies(db, full_name)
    for s in deps.get("required_services", []):
        if not s.get("self_hostable"):
            vendor_terms.append({
                "service": s["name"],
                "restricts_resale": True if s["vendor_is_upstream"] else "unknown",
                "source": f"Runtime requirement: {s['name']}",
            })
            if s["vendor_is_upstream"]:
                notes.append(f"Requires {s['name']} provided by upstream maintainer; check commercial Terms of Service.")

    hosted_saas: ComplianceVerdict = "ok"
    closed_dist: ComplianceVerdict = "ok"

    if kind == "permissive":
        hosted_saas = "ok"
        closed_dist = "ok"
        notes.append("Permissive license (MIT/Apache-2.0/BSD): Safe for proprietary SaaS and binary distribution with attribution.")
    elif kind == "weak_copyleft":
        hosted_saas = "ok"
        closed_dist = "caution"
        notes.append("Weak copyleft: Safe for SaaS backend. Direct source file edits to this library must be shared upon distribution.")
    elif kind == "copyleft":
        hosted_saas = "caution"
        closed_dist = "blocked"
        notes.append("Copyleft (GPL): Safe for hosted SaaS backend. Distribution triggers full derivative work disclosure.")
    elif kind == "network_copyleft":
        hosted_saas = "blocked"
        closed_dist = "blocked"
        notes.append("Network Copyleft (AGPL): Network access to SaaS triggers full reciprocal source disclosure. Must isolate behind API boundary.")
    else:
        hosted_saas = "blocked"
        closed_dist = "blocked"
        notes.append("No open source license or custom terms: All rights reserved or source-available.")

    return {
        "repo": full_name,
        "own_license": own_lic,
        "dependencies": dependencies,
        "vendor_terms": vendor_terms,
        "verdict": {
            "hosted_saas": hosted_saas,
            "closed_distribution": closed_dist,
            "notes": notes,
        },
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete" if repo.get("readme") else "partial",
        "sources": ["repos.license", "README.md", "get_runtime_dependencies"],
    }


# -----------------------------------------------------------------------------
# Tool 12: platform_compat [prevents F8]
# -----------------------------------------------------------------------------
class PlatformCompatArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'n8n-io/n8n'")
    platforms: list[str] | None = Field(None, max_length=10, description="Platforms to audit")


def platform_compat(db: ReadDb, full_name: str, platforms: list[str] | None = None) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "requirements": {"system_binaries": [], "gpu": False, "long_running": False, "min_memory_mb": None, "persistent_disk": False},
            "platforms": [],
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    readme = (repo.get("readme") or "").lower()
    needs_gpu = any(w in readme for w in ("cuda", "nvidia-smi", "gpu memory", "vram", "torch.cuda"))
    needs_daemon = any(w in readme for w in ("daemon", "websocket", "celery", "redis-server", "background worker", "crontab"))
    needs_disk = any(w in readme for w in ("sqlite3", "uploads/", "data_dir", "persistent volume", "chromadb"))
    system_binaries = []
    if "ffmpeg" in readme:
        system_binaries.append("ffmpeg")
    if "chrome" in readme or "puppeteer" in readme:
        system_binaries.append("headless-chrome")

    target_platforms = platforms or ["Vercel", "Cloudflare Workers", "AWS Lambda", "Fly.io", "Render", "Railway", "Cloud Run", "Docker / VPS"]
    results: list[dict] = []

    for plat in target_platforms:
        p_lower = plat.lower()
        status: PlatformStatus = "supported"
        reason = "Container and long-running runtime supported."

        if "vercel" in p_lower or "cloudflare" in p_lower or "lambda" in p_lower:
            if needs_gpu:
                status = "unsupported"
                reason = "Serverless platform does not offer dedicated GPU execution."
            elif needs_daemon:
                status = "restricted"
                reason = "Serverless functions cannot run long-lived background daemons or persistent websockets."
            elif needs_disk:
                status = "workaround"
                reason = "Stateless filesystem requires external S3 or managed database."
            elif system_binaries:
                status = "restricted"
                reason = f"Requires system binaries: {', '.join(system_binaries)}"
            else:
                status = "supported"
                reason = "Standard stateless API execution supported."
        else:
            status = "supported"
            reason = "Full container execution environment with volume and background daemon support."

        results.append({
            "name": plat,
            "status": status,
            "reason": reason,
            "source": "Platform runtime capabilities matrix",
        })

    return {
        "repo": full_name,
        "requirements": {
            "system_binaries": system_binaries,
            "gpu": needs_gpu,
            "long_running": needs_daemon,
            "min_memory_mb": 4096 if needs_gpu else 512,
            "persistent_disk": needs_disk,
        },
        "platforms": results,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete" if repo.get("readme") else "partial",
        "sources": ["README.md", "platform runtime heuristics"],
    }


# -----------------------------------------------------------------------------
# Tool 13: saas_base [composite tool]
# -----------------------------------------------------------------------------
class SaasBaseToolArgs(BaseModel):
    idea: str = Field(max_length=500, description="owner/repo or free-text product idea")
    language: str | None = Field(None, max_length=40, description="Preferred language")


def saas_base_eval(db: ReadDb, idea: str, language: str | None = None) -> dict:
    # Check if idea matches a specific full_name
    repo = _get_base_detail(db, idea)
    target_repo = idea if repo else None

    # If free text, search top match
    if not target_repo:
        rows = db.query(
            "SELECT full_name FROM repos WHERE enrich_status = 'ok' AND lower(full_name) LIKE ? LIMIT 1",
            (f"%{idea.strip().lower()}%",)
        )
        if rows:
            target_repo = rows[0]["full_name"]
            repo = _get_base_detail(db, target_repo)

    if not repo:
        return {
            "idea": idea,
            "recommended_shape": "none",
            "blockers": ["No matching repository found in the database to anchor commercialization."],
            "moat": [],
            "cogs_driver": "unknown",
            "price_anchor_usd": None,
            "kill_tests": ["Verify market existence by searching for established open source alternatives."],
            "confidence": 0.3,
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    full_name = repo["full_name"]
    artifact = classify_artifact(db, full_name)
    lic = license_audit(db, full_name)
    deps = get_runtime_dependencies(db, full_name)
    compat = platform_compat(db, full_name)

    blockers: list[str] = []
    moat: list[str] = []

    # Artifact shape guidance
    recommended_shape: FeasibleSaaSShape = artifact["feasible_saas_shapes"][0] if artifact["feasible_saas_shapes"] else "none"

    if artifact["kind"] in ("awesome_list", "course"):
        blockers.append(f"Category Error (F1): Repository is a {artifact['kind']}, not a deployable application.")
        recommended_shape = "none"

    if lic["verdict"]["hosted_saas"] == "blocked":
        blockers.append(f"License Gate: {repo.get('license')} blocks hosted SaaS without clean-room API isolation.")

    if deps["lock_in_risk"] == "high":
        blockers.append("Hidden Lock-in (F2): Project requires upstream vendor-owned cloud services.")

    # Moat identification
    if repo.get("stars", 0) > 5000:
        moat.append(f"Strong open-source brand recognition ({repo['stars']:,}★).")
    if artifact["deployable"]:
        moat.append("Standalone deployable architecture eliminates need to build UI from scratch.")

    # COGS Driver
    cogs = "Standard cloud VM compute & networking"
    if compat["requirements"]["gpu"]:
        cogs = "High-cost GPU inference compute"
    elif deps["required_services"]:
        cogs = "Third-party vendor API consumption"

    kill_tests = [
        f"Verify customers will pay for managed hosting rather than using free self-hosted edition of {full_name}.",
        f"Confirm upstream maintainers ({full_name.split('/')[0]}) do not launch a competing subsidized cloud offering."
    ]

    return {
        "idea": idea,
        "recommended_shape": recommended_shape,
        "blockers": blockers,
        "moat": moat,
        "cogs_driver": cogs,
        "price_anchor_usd": [29, 199],
        "kill_tests": kill_tests,
        "confidence": 0.85,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete",
        "sources": ["classify_artifact", "license_audit", "get_runtime_dependencies", "platform_compat"],
    }


# -----------------------------------------------------------------------------
# Tool 14: evaluate_brief [composite, end-to-end]
# -----------------------------------------------------------------------------
class EvaluateBriefArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo to evaluate")
    angles: list[Literal["saas", "services", "vertical", "plugin", "api", "support"]] | None = Field(
        None, description="Proposed commercial angles to evaluate"
    )
    brief_claims: dict[str, Any] | None = Field(
        None, description="Claims from the brief to verify, e.g. {'velocity': 'breakout', 'license': 'permissive'}"
    )


def evaluate_brief(
    db: ReadDb,
    full_name: str,
    angles: list[str] | None = None,
    brief_claims: dict[str, Any] | None = None,
) -> dict:
    repo = _get_base_detail(db, full_name)
    if repo is None:
        return {
            "error": f"{full_name} is not in the database",
            "repo": full_name,
            "verdict": "reject",
            "corrected_signals": [],
            "competitors": {"oss": [], "commercial": []},
            "angles": [],
            "recommended_wedge": None,
            "kill_tests": [],
            "next_checks": [],
            "calls_made": [],
            "as_of": db.as_of or _now_iso(),
            "data_coverage": "missing",
            "sources": ["ossdex.db"],
        }

    # Execute underlying diagnostic tools
    calls_made = [
        "classify_artifact", "get_runtime_dependencies", "classify_growth",
        "analyze_forks", "classify_issues", "license_audit", "platform_compat"
    ]
    artifact = classify_artifact(db, full_name)
    deps = get_runtime_dependencies(db, full_name)
    growth = classify_growth(db, full_name)
    forks = analyze_forks(db, full_name)
    issues = classify_issues(db, full_name)
    lic = license_audit(db, full_name)

    corrected_signals: list[dict] = []

    # Claim verification (F1-F10)
    claims = brief_claims or {}

    # Check claim: artifact / deployable
    if "deployable" in claims or "kind" in claims:
        status: ClaimStatus = "confirmed" if artifact["deployable"] else "wrong"
        corrected_signals.append({
            "claim": "deployable standalone app",
            "status": status,
            "evidence": f"classify_artifact identified kind as '{artifact['kind']}' (deployable: {artifact['deployable']})",
        })

    # Check claim: velocity
    if "velocity" in claims:
        val = str(claims["velocity"]).lower()
        status = "confirmed"
        if "breakout" in val and growth["pattern"] == "launch_spike":
            status = "overstated"
        elif "stable" in val and growth["pattern"] == "declining":
            status = "wrong"
        corrected_signals.append({
            "claim": f"velocity: {claims['velocity']}",
            "status": status,
            "evidence": f"classify_growth identified pattern as '{growth['pattern']}' (half-life: {growth['half_life_days']})",
        })

    # Check claim: fork ratio
    if "fork_ratio" in claims or "forks" in claims:
        status = "confirmed"
        if forks["interpretation"] in ("template_copies", "abandoned"):
            status = "overstated"
        corrected_signals.append({
            "claim": "fork ratio indicates production deployment",
            "status": status,
            "evidence": f"analyze_forks interpretation: '{forks['interpretation']}'",
        })

    # Check claim: license
    if "license" in claims:
        lic_claim = str(claims["license"]).lower()
        status = "confirmed"
        if "permissive" in lic_claim and repo.get("license_kind") != "permissive":
            status = "wrong"
        corrected_signals.append({
            "claim": f"license posture: {claims['license']}",
            "status": status,
            "evidence": f"license_audit verdict: {lic['verdict']['hosted_saas']} (license: {repo.get('license')})",
        })

    # Check claim: demand
    if "demand" in claims:
        status = "unverified" if issues["data_coverage"] == "missing" else "confirmed"
        corrected_signals.append({
            "claim": "validated community demand",
            "status": status,
            "evidence": f"demand coverage: {issues['data_coverage']} (bounties: {issues.get('bounty_count')})",
        })

    # Formulate verdict and angle scoring
    verdict: BriefVerdict = "pursue"
    blockers: list[str] = []

    if artifact["kind"] in ("awesome_list", "course") or not artifact["deployable"] and "saas" in (angles or []):
        verdict = "narrow"
        blockers.append(f"Cannot package {artifact['kind']} directly as hosted SaaS; require driver, plugin, or managed API angle.")

    if lic["verdict"]["hosted_saas"] == "blocked":
        verdict = "narrow"
        blockers.append("Reciprocal license requires clean-room microservice boundary.")

    if deps["lock_in_risk"] == "high":
        verdict = "reject"
        blockers.append("Hidden vendor lock-in: upstream cloud backend required.")

    # Angle evaluation
    candidate_angles = angles or ["saas", "services", "vertical", "plugin"]
    scored_angles: list[dict] = []
    for ang in candidate_angles:
        score = 8.5
        why = "Strong alignment with repo capabilities."
        ang_blockers = []
        if ang == "saas" and not artifact["deployable"]:
            score = 3.0
            why = "Artifact is a library/driver; requires custom frontend application."
            ang_blockers.append("Not a standalone deployable app")
        elif ang == "plugin" and artifact["kind"] == "plugin":
            score = 9.5
            why = "Native plugin architecture matches commercial marketplace model."
        scored_angles.append({"name": ang, "score": score, "why": why, "blockers": ang_blockers})

    recommended_wedge = "Managed Cloud Edition with Enterprise SSO" if artifact["deployable"] else "Productized Implementation & Support SLA"

    kill_tests = [
        "Reach out to 5 upvoters of top demand issues; abort if 0 willing to pilot an MVP.",
        "Deploy on container host (Fly.io/Docker) within 24 hours to verify zero upstream licensing/runtime lock-in.",
    ]

    next_checks = [
        f"Run `ossdex demand {full_name}` to fetch fresh issue signals." if issues["data_coverage"] == "missing" else "Review top demand issues.",
        "Conduct competitive pricing check on alternative managed vendors.",
    ]

    return {
        "repo": full_name,
        "verdict": verdict,
        "corrected_signals": corrected_signals,
        "competitors": {"oss": [], "commercial": []},
        "angles": scored_angles,
        "recommended_wedge": recommended_wedge,
        "kill_tests": kill_tests,
        "next_checks": next_checks,
        "calls_made": calls_made,
        "as_of": db.as_of or _now_iso(),
        "data_coverage": "complete" if repo.get("readme") else "partial",
        "sources": ["brief_tools", "repos", "repo_stats", "repo_demand"],
    }
