"""Tool registry for the MCP server (and shared by the API).

Tool docstrings (the `description` fields) are what the LLM reads, so they say when to use each
tool. Results are compact JSON with `as_of` and are capped to roughly 4k tokens.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from ossdex_core.config import Settings
from ossdex_core.licenses import KIND_NOTES
from pydantic import BaseModel, Field, ValidationError

from . import repo_query as rq
from .alternatives import FindAlternativesArgs, find_oss_alternatives
from .brief_tools import (
    AnalyzeForksArgs,
    ClassifyArtifactArgs,
    ClassifyGrowthArgs,
    ClassifyIssuesArgs,
    CommercialLandscapeArgs,
    CompanyEventsArgs,
    EvaluateBriefArgs,
    LicenseAuditArgs,
    MaintainerHealthArgs,
    NameCollisionArgs,
    PackageAdoptionArgs,
    PlatformCompatArgs,
    RuntimeDepsArgs,
    SaasBaseToolArgs,
    analyze_forks,
    check_name_collision,
    classify_artifact,
    classify_growth,
    classify_issues,
    evaluate_brief,
    get_commercial_landscape,
    get_company_events,
    get_maintainer_health,
    get_package_adoption,
    get_runtime_dependencies,
    license_audit,
    platform_compat,
    saas_base_eval,
)
from .db import VISIBLE, DbError, ReadDb
from .search import readme_sections, search, similar

log = logging.getLogger("ossdex.tools")

MAX_CHARS = 14_000  # about 4k tokens
README_INTRO_CHARS = 1500

SortName = Literal["stars", "forks", "gain_1d", "gain_7d", "gain_30d", "pushed", "created", "oldest"]
_Filters = rq.RepoFilters


class SearchReposArgs(_Filters):
    query: str = Field(max_length=200, description="Natural-language or keyword query, e.g. 'AI agents built on langchain'.")
    limit: int = Field(10, ge=1, le=30)
    offset: int = Field(0, ge=0, le=200, description="Skip this many results (paging).")


class ListReposArgs(_Filters):
    sort: SortName = "stars"
    limit: int = Field(20, ge=1, le=50)
    offset: int = Field(0, ge=0, description="Skip this many results (paging).")


class SimilarArgs(_Filters):
    full_name: str = Field(max_length=100, description="owner/repo to find alternatives to, e.g. 'n8n-io/n8n'.")
    limit: int = Field(10, ge=1, le=30)


class CompareArgs(BaseModel):
    full_names: list[str] = Field(min_length=2, max_length=6, description="2-6 repos as owner/repo.")


class CountArgs(_Filters):
    group_by: Literal["language", "license_kind", "topic", "created_year", "pushed_year"] = Field(
        description="What to group the matching repos by.")
    limit: int = Field(30, ge=1, le=50)


class GetRepoArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'langchain-ai/langchain'.")


class ReadmeArgs(BaseModel):
    full_name: str = Field(max_length=100)
    query: str = Field(max_length=200, description="What to look for inside this repo's README.")


class RisingArgs(BaseModel):
    days: Literal[1, 7] = Field(1, description="Window the star gain is measured over (1 for daily, 7 for weekly).")
    language: str | None = Field(None, description="Only this programming language.")
    limit: int = Field(20, ge=1, le=50)


class NichesArgs(_Filters):
    days: Literal[1, 7, 30] = Field(7, description="Window the star gain is measured over.")
    min_repos: int = Field(5, ge=1, le=100, description="Ignore topics with fewer repos than this.")
    sort: Literal["growth", "momentum", "size"] = Field(
        "growth", description="growth: most stars gained in total; momentum: most gained per repo "
        "(small, fast topics); size: most total stars.")
    limit: int = Field(15, ge=1, le=40)


class DemandArgs(BaseModel):
    full_name: str = Field(max_length=100, description="owner/repo, e.g. 'n8n-io/n8n'.")


class OpportunityArgs(BaseModel):
    language: str | None = Field(None, description="Only this programming language, e.g. 'python'.")
    topic: str | None = Field(None, description="Only repos with this GitHub topic.")
    days: Literal[1, 7, 30] = Field(7, description="Window the star gain is measured over.")
    min_repos: int = Field(5, ge=1, le=100, description="Ignore topics with fewer repos than this.")
    limit: int = Field(5, ge=1, le=10, description="How many niches to report.")


class NoArgs(BaseModel):
    pass


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    handler: Callable[[Any], dict]

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": self.args.model_json_schema()}


def llm_repo(dto: dict) -> dict:
    """Compact, sourced form of a repo for an LLM."""
    out = {
        "repo": dto["full_name"], "language": dto["language"], "stars": dto["stars"],
        "forks": dto["forks"], "description": dto["description"], "topics": dto["topics"] or None,
        "license": dto["license"] or "none (all rights reserved)",
        "license_kind": dto.get("license_kind"), "homepage": dto.get("homepage"),
        "created_at": dto.get("created_at"), "pushed_at": dto["pushed_at"],
        "stars_gained_1d": dto.get("gain_1d"), "stars_gained_7d": dto.get("gain_7d"),
        "stars_gained_30d": dto.get("gain_30d"),
        "similarity": dto.get("similarity"),
        "snippet": dto.get("snippet"), "matched_by": dto.get("why"),
    }
    return {k: v for k, v in out.items() if v not in (None, [], "")}


class Toolbox:
    def __init__(self, db: ReadDb, settings: Settings):
        self.db = db
        self.settings = settings
        self.cache = None  # a ResponseCache, set by the web server (a lone stdio user needs none)
        self.tools: dict[str, Tool] = {t.name: t for t in self._build()}

    # ---- plumbing ----
    def meta(self) -> dict:
        return {"as_of": self.db.as_of}

    def stats(self) -> dict:
        row = self.db.one(
            f"SELECT COUNT(*) AS repos, COALESCE(SUM(readme IS NOT NULL), 0) AS enriched "
            f"FROM repos WHERE {VISIBLE}")
        return {"repos": row["repos"], "enriched": row["enriched"],
                "history_days": self.db.history_days(),
                "require_license": self.db.meta("require_license") != "0"}

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools.values()]

    def call(self, name: str, arguments: dict | None) -> dict:
        if self.cache is None:
            return self._call(name, arguments)
        version = self.cache.snapshot()
        hit = self.cache.get_tool(name, arguments)
        if hit is not None:
            return hit
        result = self._call(name, arguments)
        self.cache.put_tool(name, arguments, result, version)
        return result

    def _call(self, name: str, arguments: dict | None) -> dict:
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"unknown tool {name!r}", "tools": sorted(self.tools)}
        try:
            args = tool.args.model_validate(arguments or {})
        except ValidationError as e:
            return {"error": "invalid arguments", "details": json.loads(e.json())[:5]}
        try:
            with self.db.budget():  # one time limit for everything this call queries
                meta = self.meta()
                res = tool.handler(args)
            if "as_of" not in res:
                res["as_of"] = meta.get("as_of") or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            if "data_coverage" not in res:
                res["data_coverage"] = "missing" if "error" in res else "complete"
            if "sources" not in res:
                res["sources"] = ["ossdex.db"]
            return cap(res | meta)
        except DbError as e:
            return {
                "error": str(e),
                "data_coverage": "missing",
                "as_of": self.db.as_of or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sources": ["ossdex.db"],
            }

    # ---- tools ----
    def _build(self) -> list[Tool]:
        return [
            Tool("search_repos",
                 "Search the open-source repo knowledge base (popular GitHub repos) by "
                 "keywords (README text, names, topics, descriptions). Use for questions like 'AI projects based on langchain' or "
                 "'tools for running llms locally'. Results are ranked repos with description, "
                 "stars, forks, recent star gains and a README snippet. Add language/topics "
                 "filters to narrow (license_kinds, min_forks...). Follow up with get_repo for details.",
                 SearchReposArgs, self._search_repos),
            Tool("list_repos",
                 "List repos by structured filters and sort, with no text query: 'top Go repos by "
                 "stars', 'most forked Rust repos', 'oldest Python repos', 'repos pushed this "
                 "month'. Use search_repos instead when the question is about a topic or concept, "
                 "and get_rising for fast-growing repos.",
                 ListReposArgs, self._list_repos),
            Tool("get_repo",
                 "Full record of one repo: description, topics, license, stars, forks, open "
                 "issues, star history and a README intro.", GetRepoArgs, self._get_repo),
            Tool("find_similar",
                 "Alternatives to a repo: projects whose description and topics match it by keywords. "
                 "Use it for 'alternatives to X' and 'more like this', optionally with "
                 "filters (e.g. license_kinds=['permissive'], pushed_after).",
                 SimilarArgs, self._similar),
            Tool("compare_repos",
                 "Side-by-side comparison of 2-6 repos: stars, forks, recent star gains, license "
                 "and what it allows, age, last push, open issues, homepage and README intro. Use "
                 "it to choose between candidates.", CompareArgs, self._compare),
            Tool("count_repos",
                 "How many repos match the filters, grouped by language, license kind, topic or "
                 "year, with total and median stars. Use it to size a niche or see what is common "
                 "(e.g. 'which topics are big among permissive Go projects?').",
                 CountArgs, self._count),
            Tool("get_readme_section",
                 "Best-matching README sections of one repo for a question, for drilling into how "
                 "a project works or what it depends on.", ReadmeArgs, self._readme),
            Tool("get_rising",
                 "Repos gaining the most stars over the last 1 day (daily) or 7 days (weekly), from the collector's "
                 "daily snapshots. The history is as long as the collector has been running, so "
                 "it can be empty at first.", RisingArgs, self._rising),
            Tool("find_niches",
                 "Topics ranked by how fast their repos are gaining stars: repos, total stars, "
                 "stars gained, gain per repo, share still maintained, and the top risers. Use it "
                 "to pick an ecosystem to specialise in or build for: a topic with fast growth and "
                 "few repos is room. Narrow with language/topic/license filters.",
                 NichesArgs, self._niches),
            Tool("get_demand",
                 "What users of one project ask for: its most-upvoted open issues and how many "
                 "open issues are labelled help wanted or bounty. Only for repos whose demand was collected; "
                 "says so when there is nothing stored. Use it for feature ideas, "
                 "plugin ideas and paid-work leads.", DemandArgs, self._demand),
            Tool("opportunity_report",
                 "For someone who wants to earn money from open source (freelancing, plugins, "
                 "hosting): the fastest-growing niches, and in each the top rising repos with "
                 "business-model hints (hosted cloud, enterprise, pricing, paid support, sponsors) "
                 "and, when fetched, bounties and most-wanted issues. Use it for 'where can I "
                 "freelance', 'what should I build'.", OpportunityArgs, self._opportunity),
            Tool("facets",
                 "The languages, topics and licenses present in the database with repo counts. "
                 "Call this to find valid filter values before filtering.", NoArgs, self._facets),
            # ---- Brief Diagnostic & Evaluation Tools (P1-P5) ----
            Tool("classify_artifact",
                 "Determine what the repository artifact actually is (app, library, sdk, framework, "
                 "template, cli, plugin, dataset, model, course, awesome_list) and which SaaS shapes "
                 "are feasible. Prevents category errors (F1, F10).",
                 ClassifyArtifactArgs, self._classify_artifact),
            Tool("get_runtime_dependencies",
                 "List external services, API credentials, and backends required or optional at runtime. "
                 "Assesses vendor lock-in risk (F2).",
                 RuntimeDepsArgs, self._get_runtime_dependencies),
            Tool("classify_growth",
                 "Classify the star curve (launch_spike, sustained_growth, flat, declining, revived), "
                 "calculate peak/median daily gains, half-life, and project 30d stars. Prevents velocity misreads (F3).",
                 ClassifyGrowthArgs, self._classify_growth),
            Tool("get_package_adoption",
                 "Registry-based adoption for packages (npm, pypi, crates, go, packagist, docker_hub). "
                 "Extracts package coordinates from README (F3, F4).",
                 PackageAdoptionArgs, self._get_package_adoption),
            Tool("analyze_forks",
                 "Distinguish genuine production customization from template copies and abandoned forks. "
                 "Prevents fork ratio misreads (F4).",
                 AnalyzeForksArgs, self._analyze_forks),
            Tool("get_maintainer_health",
                 "Maintainer health, cadence, bus-factor, push recency, and corporate/org backing. "
                 "Evaluates supply chain risk and supports SLA/services angles.",
                 MaintainerHealthArgs, self._get_maintainer_health),
            Tool("classify_issues",
                 "Cluster open issues into 10 pain categories (compliance, hosting_deployment, "
                 "performance_scaling, security, integration, etc.) and identify monetizable pain. "
                 "Prevents empty demand misinterpretation (F9).",
                 ClassifyIssuesArgs, self._classify_issues),
            Tool("get_commercial_landscape",
                 "Paid products, managed offerings, and competitor vendors in the same category with "
                 "pricing models and sources. Prevents missed commercial precedent (F5).",
                 CommercialLandscapeArgs, self._get_commercial_landscape),
            Tool("get_company_events",
                 "Funding, acquisitions, sponsorships, shutdowns, and relicensing tied to the repo org "
                 "or core maintainers (F5).",
                 CompanyEventsArgs, self._get_company_events),
            Tool("check_name_collision",
                 "Similar names across existing repos, products, and trademarks. Prevents name collisions (F6).",
                 NameCollisionArgs, self._check_name_collision),
            Tool("license_audit",
                 "License compliance posture across own code, dependencies, system binaries (e.g. ffmpeg), "
                 "model weights, and vendor terms. Outputs hosted SaaS and closed distribution verdicts (F7).",
                 LicenseAuditArgs, self._license_audit),
            Tool("platform_compat",
                 "Audit hosting platform compatibility across serverless, PaaS, and container hosts. "
                 "Evaluates GPU, background daemon, and disk requirements (F8).",
                 PlatformCompatArgs, self._platform_compat),
            Tool("saas_base",
                 "Commercial packaging assessment for a repo or idea. Evaluates recommended shape, "
                 "blockers, moat, COGS drivers, price anchors, and kill tests.",
                 SaasBaseToolArgs, self._saas_base),
            Tool("evaluate_brief",
                 "End-to-end evidence-based evaluation of a Product Idea Brief. Fact-checks claims "
                 "(velocity, forks, demand, license), scores angles, and outputs reject/narrow/pursue verdict.",
                 EvaluateBriefArgs, self._evaluate_brief),
            Tool("find_oss_alternatives",
                 "Find, rank, and articulate personalized open-source alternatives for a paid product "
                 "(e.g. Notion, Postman, TablePlus, Raycast, Docker Desktop, Zapier, 1Password) based on the "
                 "user's OS, habits (cli-first, keyboard-driven, native-gui, local-first, self-hosted-docker), "
                 "and local workflow. Provides fit scores, tailored install commands, and trade-offs.",
                 FindAlternativesArgs, self._find_oss_alternatives),
        ]

    def _search_repos(self, a: SearchReposArgs) -> dict:
        hits = search(self.db, a.query, a.to_filters(), a.limit + a.offset)[a.offset:]
        return {"query": a.query, "count": len(hits), "repos": [llm_repo(h) for h in hits]}

    def _list_repos(self, a: ListReposArgs) -> dict:
        f = a.to_filters()
        res = rq.list_repos(self.db, f, a.sort, 1, a.limit, offset=a.offset)
        out = {"total_matching": res["total"], "repos": [llm_repo(d) for d in res["items"]]}
        if a.sort.startswith("gain_") or f.min_gain is not None:
            out["history_days"] = self.db.history_days()
        return out

    def _get_repo(self, a: GetRepoArgs) -> dict:
        d = rq.repo_detail(self.db, a.full_name)
        if d is None:
            return {"error": f"{a.full_name} is not in the database"}
        out = llm_repo(d) | {
            "homepage": d["homepage"], "github_url": d["github_url"],
            "open_issues": d["open_issues"],
            "readme_intro": (d["readme"] or "")[:README_INTRO_CHARS] or None,
            "star_history": d["history"][-30:] or None,
        }
        if d.get("lists"):
            out["lists"] = d["lists"]
        if d.get("papers"):
            out["papers"] = d["papers"]
        if d.get("money"):
            out["business_hints"] = d["money"]["signals"]
            out["funding_links"] = [x["url"] for x in d["money"]["funding"] if x.get("url")]
        if d.get("demand"):
            out["demand"] = d["demand"]
        out["license_note"] = KIND_NOTES[d["license_kind"]]
        if not d["has_readme"]:
            out["note"] = "no README stored for this repo yet"
        return out

    def _similar(self, a: SimilarArgs) -> dict:
        res = similar(self.db, a.full_name, a.to_filters(), a.limit)
        if res is None:
            return {"error": f"{a.full_name} is not in the database"}
        out = {"to": a.full_name, "count": len(res["repos"]),
               "repos": [llm_repo(d) for d in res["repos"]]}
        if res.get("note"):
            out["note"] = res["note"]
        return out

    def _compare(self, a: CompareArgs) -> dict:
        rows, missing = [], []
        now = datetime.now(UTC)
        for name in dict.fromkeys(a.full_names):
            d = rq.repo_detail(self.db, name)
            if d is None:
                missing.append(name)
                continue
            pushed = d["pushed_at"]
            days = None
            if pushed:
                try:
                    when = datetime.fromisoformat(pushed)
                    days = (now - (when if when.tzinfo else when.replace(tzinfo=UTC))).days
                except ValueError:
                    days = None
            row = llm_repo(d) | {
                "forks_per_100_stars": round(100 * (d["forks"] or 0) / d["stars"], 1) if d["stars"] else None,
                "days_since_push": days, "open_issues": d["open_issues"],
                "license_note": KIND_NOTES[d["license_kind"]],
                "readme_intro": (d["readme"] or "")[:600] or None}
            if d.get("lists"):
                row["lists"] = d["lists"]
            if d.get("papers"):
                row["papers"] = d["papers"]
            rows.append(row)
        out: dict = {"repos": rows}
        if missing:
            out["missing"] = missing
        return out

    def _count(self, a: CountArgs) -> dict:
        res = rq.grouped_counts(self.db, a.to_filters(), a.group_by, a.limit)
        out = {"group_by": a.group_by} | res
        if a.group_by == "license_kind":
            out["notes"] = {g["value"]: KIND_NOTES[g["value"]] for g in res["groups"]}
        return out

    def _readme(self, a: ReadmeArgs) -> dict:
        row = self.db.one("SELECT ghr_id FROM repos WHERE lower(full_name) = lower(?)", (a.full_name,))
        if row is None:
            return {"error": f"{a.full_name} is not in the database"}
        secs = readme_sections(self.db, row["ghr_id"], a.query)
        return {"repo": a.full_name, "sections": secs or [], "note": None if secs else "no README"}

    def _rising(self, a: RisingArgs) -> dict:
        f = rq.RepoFilters(languages=[a.language] if a.language else [], min_gain=1, gain_days=a.days)
        res = rq.list_repos(self.db, f, f"gain_{a.days}d", 1, a.limit)
        out = {"window_days": a.days, "history_days": self.db.history_days(),
               "repos": [llm_repo(d) for d in res["items"]]}
        if not res["items"]:
            out["note"] = (f"no {a.days}-day star gains yet: the collector has "
                           f"{out['history_days']} days of history")
        return out

    def _niches(self, a: NichesArgs) -> dict:
        return rq.niches(self.db, a.to_filters(), a.days, a.min_repos, a.sort, a.limit)

    def _demand(self, a: DemandArgs) -> dict:
        row = self.db.one("SELECT ghr_id, full_name FROM repos WHERE lower(full_name) = lower(?)", (a.full_name,))
        if row is None:
            return {
                "error": f"{a.full_name} is not in the database",
                "repo": a.full_name,
                "fetched": False,
                "top_upvoted_issues": [],
                "help_wanted_count": None,
                "bounty_count": None,
                "data_coverage": "missing",
            }
        d = rq.demand_for(self.db, [row["ghr_id"]], issues=10).get(row["ghr_id"])
        if d is None:
            return {
                "repo": a.full_name,
                "fetched": False,
                "top_issues": [],
                "top_upvoted_issues": [],
                "help_wanted": None,
                "help_wanted_count": None,
                "bounties": None,
                "bounty_count": None,
                "note": "no demand data is stored for this repo",
                "data_coverage": "missing",
                "sources": ["repos"],
            }
        return {
            "repo": a.full_name,
            "fetched": True,
            "top_upvoted_issues": d.get("top_issues") or [],
            "help_wanted_count": d.get("help_wanted"),
            "bounty_count": d.get("bounties"),
            "data_coverage": "complete",
            "sources": ["repo_demand", "repo_issues"],
        } | d

    def _opportunity(self, a: OpportunityArgs) -> dict:
        base = rq.RepoFilters(languages=[a.language] if a.language else [],
                              topics=[a.topic] if a.topic else [], licensed_only=True)
        found = rq.niches(self.db, base, a.days, a.min_repos, "growth", a.limit)
        out_niches, unfetched = [], []
        for n in found["niches"]:
            f = base.model_copy(update={"topics": [*base.topics, n["topic"]]})
            top = rq.list_repos(self.db, f, f"gain_{a.days}d", 1, 3)["items"]
            ids = [r["ghr_id"] for r in top]
            money, demand = rq.money_for(self.db, ids), rq.demand_for(self.db, ids)
            rising = []
            for r in top:
                item = {"repo": r["full_name"], "stars": r["stars"],
                        "gain": r[f"gain_{a.days}d"], "description": r["description"]}
                if r["ghr_id"] in money:
                    item["business_hints"] = money[r["ghr_id"]]["signals"]
                if r["ghr_id"] in demand:
                    item["demand"] = demand[r["ghr_id"]]
                else:
                    unfetched.append(r["full_name"])
                rising.append(item)
            out_niches.append({k: n[k] for k in ("topic", "repos", "total_stars", "gain",
                                                  "gain_per_repo", "median_gain", "top_share",
                                                  "active_pct")} | {"rising": rising})
        out = {"window_days": found["window_days"], "history_days": found["history_days"],
               "niches": out_niches,
               "how_to_read": "Fast growth with few repos is room to specialise. Business hints "
                              "(hosted_cloud, enterprise, pricing, support_consulting, sponsors) mean "
                              "companies already pay for services around the project: those are your "
                              "freelance clients. Demand lists what users ask for."}
        if found.get("note"):
            out["note"] = found["note"]
        if unfetched:
            out["no_demand_data"] = list(dict.fromkeys(unfetched))[:6]
        return out

    def _facets(self, _: NoArgs) -> dict:
        f = rq.facets(self.db, rq.RepoFilters(), topic_limit=40)
        return {
            "languages": f["languages"][:40],
            "topics": f["topics"],
            "licenses": f["licenses"][:15],
            "lists": f.get("lists", [])[:30],
        }

    def _classify_artifact(self, a: ClassifyArtifactArgs) -> dict:
        return classify_artifact(self.db, a.full_name)

    def _get_runtime_dependencies(self, a: RuntimeDepsArgs) -> dict:
        return get_runtime_dependencies(self.db, a.full_name)

    def _classify_growth(self, a: ClassifyGrowthArgs) -> dict:
        return classify_growth(self.db, a.full_name, a.days)

    def _get_package_adoption(self, a: PackageAdoptionArgs) -> dict:
        return get_package_adoption(self.db, a.full_name)

    def _analyze_forks(self, a: AnalyzeForksArgs) -> dict:
        return analyze_forks(self.db, a.full_name, a.sample_size)

    def _get_maintainer_health(self, a: MaintainerHealthArgs) -> dict:
        return get_maintainer_health(self.db, a.full_name, a.months)

    def _classify_issues(self, a: ClassifyIssuesArgs) -> dict:
        return classify_issues(self.db, a.full_name, a.top_n)

    def _get_commercial_landscape(self, a: CommercialLandscapeArgs) -> dict:
        return get_commercial_landscape(self.db, a.full_name, a.category, a.limit)

    def _get_company_events(self, a: CompanyEventsArgs) -> dict:
        return get_company_events(self.db, a.full_name)

    def _check_name_collision(self, a: NameCollisionArgs) -> dict:
        return check_name_collision(self.db, a.name, a.category)

    def _license_audit(self, a: LicenseAuditArgs) -> dict:
        return license_audit(self.db, a.full_name)

    def _platform_compat(self, a: PlatformCompatArgs) -> dict:
        return platform_compat(self.db, a.full_name, a.platforms)

    def _saas_base(self, a: SaasBaseToolArgs) -> dict:
        return saas_base_eval(self.db, a.idea, a.language)

    def _evaluate_brief(self, a: EvaluateBriefArgs) -> dict:
        return evaluate_brief(self.db, a.full_name, a.angles, a.brief_claims)

    def _find_oss_alternatives(self, a: FindAlternativesArgs) -> dict:
        return find_oss_alternatives(self.db, a)


def cap(result: dict, max_chars: int = MAX_CHARS) -> dict:
    """Drop trailing list items until the JSON fits (keeps ranking order)."""
    for key in ("repos", "sections"):
        items = result.get(key)
        if not isinstance(items, list):
            continue
        total = len(items)
        while len(json.dumps(result, default=str)) > max_chars and len(items) > 1:
            items.pop()
        if len(items) < total:
            result["truncated"] = f"showing {len(items)} of {total} results (size cap)"
    return result
