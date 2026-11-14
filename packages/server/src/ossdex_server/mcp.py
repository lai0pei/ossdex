"""MCP server exposing the shared tool registry (stdio; also mountable over HTTP)."""

from __future__ import annotations

import logging
import os
import sys
from typing import Annotated, Literal

import anyio.to_thread
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from ossdex_core.config import Settings, load_settings
from ossdex_core.licenses import LicenseKind
from pydantic import Field

from . import repo_query as rq
from .db import open_db
from .tools import (
    CompareArgs,
    CountArgs,
    DemandArgs,
    ListReposArgs,
    NichesArgs,
    OpportunityArgs,
    SearchReposArgs,
    SimilarArgs,
    SortName,
    Toolbox,
    _Filters,
)


def build_toolbox(settings: Settings) -> Toolbox:
    db = open_db(settings.db_path)
    return Toolbox(db, settings)


def _doc(model, field: str) -> Field:
    """The description of a tool-argument field from the tool schema."""
    return Field(description=model.model_fields[field].description)


Languages = Annotated[list[str] | None, _doc(_Filters, "languages")]
Topics = Annotated[list[str] | None, _doc(_Filters, "topics")]
Licenses = Annotated[list[str] | None, _doc(_Filters, "licenses")]
Kinds = Annotated[list[LicenseKind] | None, _doc(_Filters, "license_kinds")]
MinStars = Annotated[int | None, _doc(_Filters, "min_stars")]
MaxStars = Annotated[int | None, _doc(_Filters, "max_stars")]
MinForks = Annotated[int | None, _doc(_Filters, "min_forks")]
MaxForks = Annotated[int | None, _doc(_Filters, "max_forks")]
PushedAfter = Annotated[str | None, _doc(_Filters, "pushed_after")]
PushedBefore = Annotated[str | None, _doc(_Filters, "pushed_before")]
MinGain = Annotated[int | None, _doc(_Filters, "min_gain")]
GainDays = Annotated[Literal[1, 7, 30] | None, _doc(_Filters, "gain_days")]
InLists = Annotated[list[str] | None, _doc(_Filters, "in_lists")]
Money = Annotated[list[str] | None, _doc(_Filters, "money")]
HasBounties = Annotated[bool | None, _doc(_Filters, "has_bounties")]
MentionsPaper = Annotated[bool | None, _doc(_Filters, "mentions_paper")]
LicensedOnly = Annotated[bool | None, _doc(_Filters, "licensed_only")]
GroupBy = Literal["language", "license_kind", "topic", "created_year", "pushed_year"]


LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
LOCAL_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def public_host() -> str | None:
    """The domain the public server answers on (`OSSDEX_PUBLIC_HOST`, e.g. ossdex.example.com)."""
    return os.environ.get("OSSDEX_PUBLIC_HOST", "").strip() or None


def transport_security(host: str | None = None) -> TransportSecuritySettings:
    """DNS-rebinding protection that allows localhost plus the public domain. Left to its default,
    FastMCP allows localhost only and rejects every request that arrives under the real domain."""
    hosts, origins = list(LOCAL_HOSTS), list(LOCAL_ORIGINS)
    if host:
        hosts += [host, f"{host}:*"]
        origins += [f"https://{host}", f"http://{host}"]
    return TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                     allowed_hosts=hosts, allowed_origins=origins)


def create_mcp(tb: Toolbox, **kwargs) -> FastMCP:
    mcp = FastMCP("ossdex", **kwargs)

    def reg(name: str):
        return mcp.tool(name=name, description=tb.tools[name].description)

    async def call(name: str, **args) -> dict:
        # tb.call blocks on SQLite; FastMCP runs async tools on the event loop, so hand it to a
        # worker thread or one slow query stalls every other request on this process.
        arguments = {k: v for k, v in args.items() if v is not None}
        return await anyio.to_thread.run_sync(tb.call, name, arguments)

    @reg("search_repos")
    async def search_repos(query: Annotated[str, _doc(SearchReposArgs, "query")],
                     languages: Languages = None, topics: Topics = None, licenses: Licenses = None,
                     license_kinds: Kinds = None, min_stars: MinStars = None,
                     max_stars: MaxStars = None, min_forks: MinForks = None, max_forks: MaxForks = None,
                     pushed_after: PushedAfter = None, pushed_before: PushedBefore = None, min_gain: MinGain = None,
                     gain_days: GainDays = None, licensed_only: LicensedOnly = None,
                     in_lists: InLists = None, mentions_paper: MentionsPaper = None,
                     money: Money = None, has_bounties: HasBounties = None,
                     limit: int = 10, offset: Annotated[int, _doc(SearchReposArgs, "offset")] = 0
                     ) -> dict:
        return await call("search_repos", query=query, languages=languages, topics=topics,
                    licenses=licenses, license_kinds=license_kinds, min_stars=min_stars,
                    max_stars=max_stars, min_forks=min_forks, max_forks=max_forks, pushed_after=pushed_after, pushed_before=pushed_before,
                    min_gain=min_gain, gain_days=gain_days, licensed_only=licensed_only,
                    in_lists=in_lists, mentions_paper=mentions_paper, money=money,
                    has_bounties=has_bounties, limit=limit, offset=offset)

    @reg("list_repos")
    async def list_repos(languages: Languages = None, topics: Topics = None, licenses: Licenses = None,
                   license_kinds: Kinds = None, min_stars: MinStars = None,
                   max_stars: MaxStars = None, min_forks: MinForks = None, max_forks: MaxForks = None,
                   pushed_after: PushedAfter = None, pushed_before: PushedBefore = None, min_gain: MinGain = None,
                   gain_days: GainDays = None, licensed_only: LicensedOnly = None,
                   in_lists: InLists = None, mentions_paper: MentionsPaper = None,
                   money: Money = None, has_bounties: HasBounties = None,
                   sort: SortName = "stars", limit: int = 20,
                   offset: Annotated[int, _doc(ListReposArgs, "offset")] = 0) -> dict:
        return await call("list_repos", languages=languages, topics=topics, licenses=licenses,
                    license_kinds=license_kinds, min_stars=min_stars, max_stars=max_stars,
                    min_forks=min_forks, max_forks=max_forks, pushed_after=pushed_after, pushed_before=pushed_before, min_gain=min_gain,
                    gain_days=gain_days, licensed_only=licensed_only, in_lists=in_lists,
                    mentions_paper=mentions_paper, money=money, has_bounties=has_bounties,
                    sort=sort, limit=limit,
                    offset=offset)

    @reg("find_similar")
    async def find_similar(full_name: Annotated[str, _doc(SimilarArgs, "full_name")],
                     license_kinds: Kinds = None, languages: Languages = None,
                     min_stars: MinStars = None, min_forks: MinForks = None, max_forks: MaxForks = None,
                     pushed_after: PushedAfter = None, pushed_before: PushedBefore = None, limit: int = 10) -> dict:
        return await call("find_similar", full_name=full_name, license_kinds=license_kinds,
                    languages=languages, min_stars=min_stars, min_forks=min_forks, max_forks=max_forks,
                    pushed_after=pushed_after, pushed_before=pushed_before, limit=limit)

    @reg("compare_repos")
    async def compare_repos(full_names: Annotated[list[str], _doc(CompareArgs, "full_names")]) -> dict:
        return await call("compare_repos", full_names=full_names)

    @reg("count_repos")
    async def count_repos(group_by: Annotated[GroupBy, _doc(CountArgs, "group_by")],
                    languages: Languages = None, topics: Topics = None,
                    license_kinds: Kinds = None, min_stars: MinStars = None,
                    max_stars: MaxStars = None, min_forks: MinForks = None, max_forks: MaxForks = None,
                    pushed_after: PushedAfter = None, pushed_before: PushedBefore = None, limit: int = 30) -> dict:
        return await call("count_repos", group_by=group_by, languages=languages, topics=topics,
                    license_kinds=license_kinds, min_stars=min_stars, max_stars=max_stars,
                    min_forks=min_forks, max_forks=max_forks, pushed_after=pushed_after, pushed_before=pushed_before, limit=limit)

    @reg("find_niches")
    async def find_niches(languages: Languages = None, topics: Topics = None, license_kinds: Kinds = None,
                    days: Annotated[Literal[1, 7, 30], _doc(NichesArgs, "days")] = 7,
                    min_repos: Annotated[int, _doc(NichesArgs, "min_repos")] = 5,
                    sort: Annotated[Literal["growth", "momentum", "size"], _doc(NichesArgs, "sort")] = "growth",
                    limit: int = 15) -> dict:
        return await call("find_niches", languages=languages, topics=topics, license_kinds=license_kinds,
                    days=days, min_repos=min_repos, sort=sort, limit=limit)

    @reg("get_demand")
    async def get_demand(full_name: Annotated[str, _doc(DemandArgs, "full_name")]) -> dict:
        return await call("get_demand", full_name=full_name)

    @reg("opportunity_report")
    async def opportunity_report(language: Annotated[str | None, _doc(OpportunityArgs, "language")] = None,
                           topic: Annotated[str | None, _doc(OpportunityArgs, "topic")] = None,
                           days: Annotated[Literal[1, 7, 30], _doc(OpportunityArgs, "days")] = 7,
                           min_repos: Annotated[int, _doc(OpportunityArgs, "min_repos")] = 5,
                           limit: int = 5) -> dict:
        return await call("opportunity_report", language=language, topic=topic, days=days,
                    min_repos=min_repos, limit=limit)

    @reg("get_repo")
    async def get_repo(full_name: str) -> dict:
        return await call("get_repo", full_name=full_name)

    @reg("get_readme_section")
    async def get_readme_section(full_name: str, query: str) -> dict:
        return await call("get_readme_section", full_name=full_name, query=query)

    @reg("get_rising")
    async def get_rising(days: int = 1, language: str | None = None, limit: int = 20) -> dict:
        return await call("get_rising", days=days, language=language, limit=limit)

    @reg("facets")
    async def facets() -> dict:
        return await call("facets")

    @reg("classify_artifact")
    async def classify_artifact(full_name: str) -> dict:
        return await call("classify_artifact", full_name=full_name)

    @reg("get_runtime_dependencies")
    async def get_runtime_dependencies(full_name: str) -> dict:
        return await call("get_runtime_dependencies", full_name=full_name)

    @reg("classify_growth")
    async def classify_growth(full_name: str, days: int = 60) -> dict:
        return await call("classify_growth", full_name=full_name, days=days)

    @reg("get_package_adoption")
    async def get_package_adoption(full_name: str) -> dict:
        return await call("get_package_adoption", full_name=full_name)

    @reg("analyze_forks")
    async def analyze_forks(full_name: str, sample_size: int = 500) -> dict:
        return await call("analyze_forks", full_name=full_name, sample_size=sample_size)

    @reg("get_maintainer_health")
    async def get_maintainer_health(full_name: str, months: int = 6) -> dict:
        return await call("get_maintainer_health", full_name=full_name, months=months)

    @reg("classify_issues")
    async def classify_issues(full_name: str, top_n: int = 100) -> dict:
        return await call("classify_issues", full_name=full_name, top_n=top_n)

    @reg("get_commercial_landscape")
    async def get_commercial_landscape(full_name: str | None = None, category: str | None = None, limit: int = 10) -> dict:
        return await call("get_commercial_landscape", full_name=full_name, category=category, limit=limit)

    @reg("get_company_events")
    async def get_company_events(full_name: str) -> dict:
        return await call("get_company_events", full_name=full_name)

    @reg("check_name_collision")
    async def check_name_collision(name: str, category: str | None = None) -> dict:
        return await call("check_name_collision", name=name, category=category)

    @reg("license_audit")
    async def license_audit(full_name: str) -> dict:
        return await call("license_audit", full_name=full_name)

    @reg("platform_compat")
    async def platform_compat(full_name: str, platforms: list[str] | None = None) -> dict:
        return await call("platform_compat", full_name=full_name, platforms=platforms)

    @reg("saas_base")
    async def saas_base_tool(idea: str, language: str | None = None) -> dict:
        return await call("saas_base", idea=idea, language=language)

    @reg("evaluate_brief")
    async def evaluate_brief(full_name: str, angles: list[str] | None = None, brief_claims: dict | None = None) -> dict:
        return await call("evaluate_brief", full_name=full_name, angles=angles, brief_claims=brief_claims)

    @reg("find_oss_alternatives")
    async def find_oss_alternatives(
        paid_product: str,
        os: Literal["macos", "linux", "windows"] = "linux",
        habits: list[str] | None = None,
        installed_software: list[str] | None = None,
        license_kinds: Kinds = None,
        min_stars: MinStars = None,
        limit: int = 8,
    ) -> dict:
        return await call(
            "find_oss_alternatives",
            paid_product=paid_product,
            os=os,
            habits=habits,
            installed_software=installed_software,
            license_kinds=license_kinds,
            min_stars=min_stars,
            limit=limit,
        )

    @mcp.resource("ossdex://repo/{owner}/{name}")
    async def repo_readme(owner: str, name: str) -> str:
        d = await anyio.to_thread.run_sync(rq.repo_detail, tb.db, f"{owner}/{name}")
        if d is None:
            return f"{owner}/{name} is not in the database"
        d = rq.public_detail(d)
        return (f"# {d['full_name']}\n\n{d['github_url']}\n\n"
                f"{d['readme_excerpt'] or '(no README stored)'}"
                + (f"\n\n(excerpt; full README: {d['readme_url']})" if d["readme_truncated"] else ""))

    @mcp.prompt(name="saas_base", description="Find an open-source project to build a product or "
                                              "SaaS on, with licenses that allow it.")
    def saas_base(idea: str, language: str = "") -> str:
        lang = f" in {language}" if language else ""
        return (
            f"Find open-source projects{lang} I could use as the base of a product or SaaS: {idea}.\n"
            "Use the ossdex tools:\n"
            "1. search_repos with several angles ('self-hosted <idea>', 'open source <idea> "
            "alternative', '<idea> starter / boilerplate'), license_kinds=['permissive'] and "
            "pushed_after within the last 6 months. Repeat with 'weak_copyleft' and flag the caveat.\n"
            "2. compare_repos on the best 4-5, and find_similar on the best one to catch alternatives.\n"
            "3. For each finalist report: what it is, license and what the license allows for a hosted "
            "or closed product, maturity (stars, age), momentum (star gains), open issues, whether a "
            "paid cloud version exists (homepage), and the effort to rebrand or extend it.\n"
            "Mention AGPL or unclassified licenses only as warnings. Recommend one, say what would "
            "change that choice, and end with: license summary, not legal advice; read each LICENSE.")

    @mcp.prompt(name="freelance_niches", description="Find platforms businesses run that you could "
                                                     "get paid to set up, customize or extend.")
    def freelance_niches(skill_or_stack: str) -> str:
        return (
            f"I do freelance work with: {skill_or_stack}. Find open-source platforms that "
            "businesses deploy and pay people to set up, customize and extend.\n"
            "Use the ossdex tools:\n"
            "1. count_repos(group_by='topic') for that stack, then list_repos sorted by forks "
            "(many forks = many deployments) and search_repos for CMS, e-commerce, ERP, CRM, "
            "automation, analytics, booking, learning platforms and similar.\n"
            "2. get_rising for new niches that are growing.\n"
            "3. For each of the best 5-8: users (stars, forks), how alive it is (last push, issues), "
            "what clients would pay for (setup, plugins/themes, migrations, integrations, hosting, "
            "support) and the skills needed.\n"
            "License matters less for client work, but note AGPL or source-available terms.\n"
            "Rank them and suggest which one to start with.")

    @mcp.prompt(name="oss_solution", description="Find the best open-source tool for a problem "
                                                 "and its alternatives.")
    def oss_solution(problem: str, constraints: str = "") -> str:
        extra = f" Constraints: {constraints}." if constraints else ""
        return (
            f"Find the best open-source solution for: {problem}.{extra}\n"
            "Use the ossdex tools: search_repos for candidates, find_similar on the top hit to "
            "catch alternatives, then compare_repos on 3-5 finalists. Recommend one with its "
            "tradeoffs (license, maturity, activity, language, how it is run) and name the runner-up.")

    @mcp.prompt(name="vertical_saas_idea", description="Formulate a vertical SaaS product idea "
                                                       "tailoring an open-source project to a "
                                                       "specific industry.")
    def vertical_saas_idea(repo_or_niche: str, target_industry: str) -> str:
        return (
            f"Design a vertical SaaS product based on {repo_or_niche} tailored specifically for "
            f"the {target_industry} industry.\n"
            "Use the ossdex tools:\n"
            "1. If a specific repo is named, run get_repo and get_demand on it. If a concept is "
            "named, search_repos with license_kinds=['permissive'] to find permissive candidates.\n"
            "2. Run find_similar to check if competitors or alternatives already serve this space.\n"
            "3. Inspect get_demand for enterprise requests: compliance, audit trails, security, SSO, "
            "and domain-specific integrations.\n"
            "4. Deliver: (a) Value proposition for the target vertical; (b) Required compliance & "
            "custom connectors (e.g. HIPAA, SOC2, FINRA, GDPR); (c) Packaging & pricing tiers; "
            "(d) Sales & distribution strategy for reaching buyers in this industry.")

    @mcp.prompt(name="compose_product_stack", description="Compose 2 to 5 open-source repositories "
                                                          "into a unified product architecture with "
                                                          "assigned roles and license audit.")
    def compose_product_stack(idea: str, core_repos: str = "", language: str = "") -> str:
        repos_note = f" Starting components: {core_repos}." if core_repos else ""
        lang_note = f" Preferred language: {language}." if language else ""
        return (
            f"Architect a complete software product for: {idea}.{repos_note}{lang_note}\n"
            "Use the ossdex tools:\n"
            "1. If core_repos are specified, run compare_repos to audit their licenses, velocity, "
            "and maintenance. If not, use search_repos across architectural layers (engine, api, "
            "ui, storage, auth) with license_kinds=['permissive', 'weak_copyleft'].\n"
            "2. For each component, use get_readme_section to inspect API contracts, Docker compose "
            "specs, and integration hooks.\n"
            "3. Check license compatibility: ensure no copyleft/AGPL obligations contaminate "
            "proprietary code, or isolate them behind microservice/RPC boundaries.\n"
            "4. Deliver: (a) Architectural topology with assigned roles; (b) Data flow & inter-service "
            "communication protocols; (c) License gate audit and isolation strategy; (d) MVP roadmap.")

    @mcp.prompt(name="monetize_demand_gaps", description="Analyze unmet community demand, bounties, "
                                                         "and upvoted issues to build paid extensions "
                                                         "or services.")
    def monetize_demand_gaps(full_name: str) -> str:
        return (
            f"Analyze unmet community demand and monetization opportunities around: {full_name}.\n"
            "Use the ossdex tools:\n"
            "1. Run get_demand(full_name=full_name) to inspect top upvoted open issues, reactions, "
            "comments, and bounty counts.\n"
            "2. Run get_repo(full_name=full_name) to review funding links, sponsors, and existing "
            "commercial signals.\n"
            "3. Identify the #1 highest-ROI paid extension, plugin, or enterprise integration to build.\n"
            "4. Deliver: (a) Validated problem breakdown from issue comments; (b) Technical extension "
            "architecture; (c) Monetization model (one-time license vs. SaaS connector); (d) Outreach "
            "plan to convert the issue upvoters into beta customers.")

    @mcp.prompt(name="fork_and_rebrand_audit", description="Technical and legal checklist for safely "
                                                           "forking, rebranding, and white-labeling "
                                                           "an open-source project.")
    def fork_and_rebrand_audit(full_name: str, product_goal: str = "") -> str:
        goal_note = f" Target product goal: {product_goal}." if product_goal else ""
        return (
            f"Create a technical and legal plan to fork, rebrand, and white-label: {full_name}.{goal_note}\n"
            "Use the ossdex tools:\n"
            "1. Run get_repo(full_name=full_name) to inspect license terms, maintainer velocity, and "
            "days since last push.\n"
            "2. Run get_readme_section(full_name=full_name, query='trademark license build contributing') "
            "to check for trademark guidelines and build requirements.\n"
            "3. Run find_similar(full_name=full_name) to verify whether other active forks or commercial "
            "spinoffs already exist.\n"
            "4. Deliver: (a) Legal notice preservation requirements; (b) Assets & branding checklist "
            "(logos, telemetry stripping, domain references); (c) Upstream tracking git strategy.")

    @mcp.prompt(name="competitive_moat_analysis", description="Benchmark an open-source project against "
                                                             "its top alternatives to find underserved "
                                                             "positioning moats.")
    def competitive_moat_analysis(full_name: str) -> str:
        return (
            f"Conduct a competitive moat and positioning analysis for: {full_name}.\n"
            "Use the ossdex tools:\n"
            "1. Run find_similar(full_name=full_name, limit=6) to discover the closest open-source "
            "competitors.\n"
            "2. Run compare_repos across {full_name} and the top 3-4 alternatives to analyze star velocity, "
            "fork ratios, license restrictions, and open issue backlogs.\n"
            "3. For the top competitors, inspect get_demand to see where users are unhappy or requesting "
            "missing capabilities.\n"
            "4. Deliver: (a) Competitive feature & licensing matrix; (b) Underserved positioning wedge; "
            "(c) Defensibility strategy against upstream or competing alternatives.")

    @mcp.prompt(name="breakout_opportunity_scan", description="Scan fast-growing topics and rising repos "
                                                              "to spot emerging open-source product "
                                                              "opportunities.")
    def breakout_opportunity_scan(language: str = "", topic: str = "", days: int = 7) -> str:
        lang_note = f" for language '{language}'" if language else ""
        topic_note = f" in topic '{topic}'" if topic else ""
        return (
            f"Scan for breakout open-source opportunities{lang_note}{topic_note} over the last {days} days.\n"
            "Use the ossdex tools:\n"
            "1. Run opportunity_report(language=language, topic=topic, days=days) to find fast-growing "
            "niches with business-model signals and unmet demand.\n"
            "2. Run find_niches and get_rising to verify star acceleration and maintained share.\n"
            "3. For the standout rising project, run get_demand and compare_repos to validate traction.\n"
            "4. Deliver: (a) Top 3 breakout themes; (b) Market gaps with few repos but high momentum; "
            "(c) 2 actionable product concepts to build in these niches.")

    @mcp.prompt(name="evaluate_product_brief", description="Evaluate a Product Idea Brief against 10 commercialization failure modes (F1-F10).")
    def evaluate_product_brief(full_name: str, angles: str = "", claims: str = "") -> str:
        angles_note = f" Proposed commercial angles: {angles}." if angles else ""
        claims_note = f" Claims to verify: {claims}." if claims else ""
        return (
            f"Evaluate the Product Idea Brief for repository: {full_name}.{angles_note}{claims_note}\n"
            "Use the ossdex tools to verify all assumptions and prevent the 10 failure modes (F1-F10):\n"
            "1. Run classify_artifact(full_name=full_name) to prevent category errors (F1) and confirm deployability.\n"
            "2. Run get_runtime_dependencies(full_name=full_name) to audit vendor lock-in risk (F2).\n"
            "3. Run classify_growth(full_name=full_name) to distinguish launch spikes from sustained growth (F3).\n"
            "4. Run analyze_forks(full_name=full_name) and get_package_adoption(full_name=full_name) to verify production adoption (F4).\n"
            "5. Run get_commercial_landscape(full_name=full_name) and get_company_events(full_name=full_name) to map competitors (F5).\n"
            "6. Run check_name_collision(name=full_name.split('/')[1]) to check trademark/name collisions (F6).\n"
            "7. Run license_audit(full_name=full_name) to audit system binaries and copyleft risks (F7).\n"
            "8. Run platform_compat(full_name=full_name) to evaluate serverless, GPU, and daemon constraints (F8).\n"
            "9. Run classify_issues(full_name=full_name) and get_demand(full_name=full_name) to cluster monetizable pain (F9).\n"
            "10. Finally, run evaluate_brief(full_name=full_name) to synthesize the evidence-based verdict (pursue/narrow/reject), "
            "recommend the commercial wedge, and specify concrete kill tests.")

    @mcp.prompt(name="articulate_repo_ideas", description="Brainstorm and articulate 5 concrete product/startup ideas based on an open-source repository.")
    def articulate_repo_ideas(full_name: str, target_audience: str = "") -> str:
        aud_note = f" Target audience hint: {target_audience}." if target_audience else ""
        return (
            f"Brainstorm and articulate 5 concrete, evidence-based commercial product ideas based on repository: {full_name}.{aud_note}\n"
            "Use the ossdex tools to discover what the repository provides, where real demand exists, and which business shapes are viable:\n"
            "1. Run classify_artifact(full_name=full_name) to confirm the artifact kind (app vs library vs template) and viable SaaS shapes.\n"
            "2. Run get_repo(full_name=full_name) and get_readme_section to inspect core capabilities, architectural boundaries, and dependencies.\n"
            "3. Run classify_issues(full_name=full_name) and get_demand(full_name=full_name) to extract the most painful user problems and requested features.\n"
            "4. Run get_commercial_landscape(full_name=full_name) and find_similar(full_name=full_name) to identify existing competitors and market voids.\n"
            "5. Run license_audit(full_name=full_name) to ensure the proposed commercial ideas comply with license obligations.\n"
            "Deliver 5 distinct product ideas across viable formats (e.g., Managed Cloud / Hosted API / Vertical Edition / Developer DX Plugin / Workflow Automation). For each idea deliver:\n"
            "(a) One-Sentence Pitch: An [X] for [Persona Y] that solves [Pain Z] without [Friction W];\n"
            "(b) Commercial Shape & Packaging (seat-based, usage-based, or enterprise tier);\n"
            "(c) 80/20 Value Split: What the open-source repo supplies vs. what proprietary value you build on top;\n"
            "(d) Grounding Evidence: Specific issues, missing features, or demand signals from the tools;\n"
            "(e) Fastest 14-day MVP wedge and kill criteria.")

    @mcp.prompt(name="articulate_stack_ideas", description="Brainstorm 4 concrete '1+1=3' mashup product ideas combining 2 to 6 open-source repositories.")
    def articulate_stack_ideas(repos: str, domain_hint: str = "") -> str:
        dom_note = f" Domain or theme hint: {domain_hint}." if domain_hint else ""
        return (
            f"Brainstorm 4 concrete, high-synergy '1+1=3' commercial product ideas created by combining these repositories: {repos}.{dom_note}\n"
            "Use the ossdex tools to analyze component synergies, license boundaries, and integration seams:\n"
            "1. Run compare_repos across all specified repositories to evaluate side-by-side maturity, maintenance, and license kinds.\n"
            "2. For each repo, run classify_artifact to assign complementary architectural roles (e.g., core compute engine, API gateway, UI frontend, vector storage, agent orchestration).\n"
            "3. Run get_demand on each repository to pinpoint integration gaps and requested connectors between these ecosystems.\n"
            "4. Deliver 4 distinct mashup product concepts that can only exist by uniting these specific repositories:\n"
            "(a) Unified Product Narrative & Pitch: What the composed product does and who pays for it;\n"
            "(b) Architectural Topology: How each repo functions as a modular subsystem and where the proprietary glue sits;\n"
            "(c) Synergy Moat: Why this specific combination creates an unfair advantage over standalone single-repo wrappers;\n"
            "(d) Pricing & Delivery Model (Managed Multi-Tenant Cloud vs. Private VPC Appliance vs. Developer CLI/SDK);\n"
            "(e) Lean 14-Day MVP Scope: The minimum viable glue layer needed to demo the integrated solution to design partners.")

    @mcp.prompt(name="learn_repo_80_20", description="Pareto 80/20 learning guide: prerequisites, the 20% high-value core, 80% noise to skip, 60-min fast-track lab, and common pitfalls.")
    def learn_repo_80_20(full_name: str, background: str = "", goal: str = "") -> str:
        bg_note = f" User background: {background}." if background else ""
        goal_note = f" Target goal: {goal}." if goal else ""
        return (
            f"Create a Pareto 80/20 learning and usage guide for repository: {full_name}.{bg_note}{goal_note}\n"
            "Apply the 80/20 rule: focus on the 20% core knowledge that yields 80% of practical capability, "
            "and filter out the 80% edge-case noise.\n"
            "Use the ossdex tools to inspect the repository structure, capabilities, dependencies, and real user friction:\n"
            "1. Run classify_artifact(full_name=full_name) to understand what kind of artifact this is (library, CLI, app, framework) and how it runs.\n"
            "2. Run get_repo(full_name=full_name) and get_readme_section(full_name=full_name, query='quickstart installation usage architecture api') to extract the official entry points.\n"
            "3. Run get_runtime_dependencies(full_name=full_name) to identify required credentials, backend services, or system binaries.\n"
            "4. Run classify_issues(full_name=full_name) to identify real user stumbling blocks, particularly around installation, environment, and docs.\n"
            "Deliver a structured Pareto 80/20 Mastery Guide with:\n"
            "(a) Prerequisite Knowledge Checklist: Essential languages, libraries, and concepts split into 'Must-Know Now (20%)' vs. 'Look Up Later (80%)';\n"
            "(b) The 20% Core to Learn First: The 3-5 primary abstractions, APIs, or commands that deliver 80% of real-world value;\n"
            "(c) The 80% You Can Safely Ignore Initially: Advanced internals, niche adapters, or legacy flags to skip on Day 1;\n"
            "(d) 60-Minute Hands-On Fast-Track Lab: 0-15m environment setup, 15-35m Hello World run, 35-60m first practical modification;\n"
            "(e) Top Beginner Pitfalls & Traps: 3 common errors from GitHub issues and the exact fix for each.")

    @mcp.prompt(name="learn_stack_80_20", description="Pareto 80/20 multi-repo stack learning path: prerequisite matrix, 20% integration surface of each repo, and weekend mini-project.")
    def learn_stack_80_20(repos: str, background: str = "") -> str:
        bg_note = f" User background: {background}." if background else ""
        return (
            f"Create a Pareto 80/20 learning path to master and integrate this multi-repo stack: {repos}.{bg_note}\n"
            "Instead of learning 100% of every repo, apply the 80/20 rule to master only the integration surfaces and core contracts.\n"
            "Use the ossdex tools:\n"
            "1. Run compare_repos across all specified repositories to inspect languages, maturity, and dependencies.\n"
            "2. For each repo, run classify_artifact and get_readme_section to pinpoint how they communicate (REST, gRPC, CLI, SDK, database).\n"
            "3. Deliver a high-leverage multi-repo learning roadmap:\n"
            "(a) Cross-Stack Prerequisite Matrix: Common concepts across the stack;\n"
            "(b) The 20% Integration Surface: Exactly which APIs or data structures connect the repos;\n"
            "(c) Optimal Learning Sequence: Order in which to learn the components (e.g., Engine -> Interface -> Auth);\n"
            "(d) Weekend Stitch-Together Mini-Project: A step-by-step build lab to get a working integrated prototype in 48 hours.")

    @mcp.prompt(name="find_oss_alternative", description="Find, analyze, and articulate tailored open-source alternatives for a paid product based on user OS, habits, and installed software.")
    def find_oss_alternative(paid_product: str, habits: str = "", workflow_notes: str = "") -> str:
        habits_note = f" User habits preference: {habits}." if habits else ""
        wf_note = f" Workflow context: {workflow_notes}." if workflow_notes else ""
        return (
            f"Find, analyze, and articulate the best open-source alternatives for: {paid_product}.{habits_note}{wf_note}\n"
            "Use the ossdex tools to evaluate top open-source candidates:\n"
            "1. Ask the user for their operating system (macos, linux or windows), daily habits (cli-first, keyboard-driven, native-gui, local-first, self-hosted-docker) and installed tools (brew, docker, cargo...), unless they already said.\n"
            f"2. Run `find_oss_alternatives(paid_product='{paid_product}', os=..., habits=[...], installed_software=[...])` to retrieve ranked open-source candidates with fit scores, tailored install commands, and habit synergy analysis.\n"
            "3. If candidate details or README sections are needed, run `get_repo(full_name=candidate)` and `get_readme_section` on the top 2-3 finalists.\n"
            "4. Compare the top finalists using `compare_repos`.\n"
            "Deliver a tailored Open-Source Alternative & Migration Report:\n"
            "(a) Executive Recommendation: The #1 best overall match, #1 CLI/TUI pick, and #1 native/GUI pick for the user's specific OS;\n"
            "(b) Deep-Dive Candidate Matrix: For each top recommendation, detail why it fits their habits (e.g. Vim keybindings, offline SQLite, local Docker), workflow synergies with their installed software, and exact tailored install command;\n"
            "(c) Honest Trade-Offs & Feature Parity: Specific capabilities the proprietary product has that are missing, and how to bridge them;\n"
            "(d) 15-Minute Migration Plan: Step-by-step export, import, and configuration guide to switch smoothly.")

    @mcp.resource("ossdex://status")
    def status() -> str:
        import json

        return json.dumps(tb.stats() | tb.meta())

    return mcp


def serve_stdio() -> None:
    serve_mcp(transport="stdio")


def serve_mcp(
    transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
    host: str = "127.0.0.1",
    port: int = 8201,
) -> None:
    if transport == "stdio":
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)  # stdout is the MCP channel
    else:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    extra = {}
    if transport == "streamable-http":  # same HTTP settings as the web server's /mcp
        extra = {"stateless_http": True, "json_response": True,
                 "transport_security": transport_security(public_host())}
    mcp = create_mcp(build_toolbox(load_settings()), host=host, port=port, **extra)
    mcp.run(transport=transport)
