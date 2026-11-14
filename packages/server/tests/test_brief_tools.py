"""Tests for the 14 brief diagnostic and evaluation tools in brief_tools.py.

Prevents failure modes F1 through F10:
- F1: Category error (treating library/template/list as deployable app)
- F2: Hidden lock-in (vendor-owned backend required)
- F3: Velocity misread (decaying launch spike confused with breakout growth)
- F4: Fork misread (template copies confused with enterprise deployment)
- F5: Missed commercial precedent (existing vendor/managed offering occupies angle)
- F6: Name/trademark collision (collision with existing repo or trademark)
- F7: License blind spot (copyleft system binaries, model weights, vendor ToS)
- F8: Platform blind spot (target hosting cannot run workloads)
- F9: Empty demand data ("0 bounties" reported when demand was never fetched)
- F10: Noisy similarity (surfacing semantic vs keyword match provenance)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ossdex_core.store import connect
from ossdex_server import brief_tools as bt
from ossdex_server.db import ReadDb
from ossdex_server.tools import Toolbox

from testsupport.helpers import build_fixture_db


@pytest.fixture
def custom_db_path(tmp_path: Path) -> Path:
    p = build_fixture_db(tmp_path / "custom_test.db")
    conn = connect(p)
    # Add specialized repos for testing failure modes
    # Repos:
    # 101: Awesome list (F1)
    # 102: Python Library with pip install (F1, F4)
    # 103: Deployable App with Docker and OpenAI lock-in (F1, F2, F8)
    # 104: AGPL project with ffmpeg binary (F7, F8)
    # 105: Launch spike project (F3)
    conn.execute(
        "INSERT INTO repos (ghr_id, node_id, full_name, url, language, description, topics, "
        "license, stars, forks, open_issues, enrich_status, pushed_at, created_at, readme, "
        "first_seen, last_seen, enriched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            101, "node101", "curator/awesome-agents", "https://github.com/curator/awesome-agents",
            "Markdown", "A curated list of awesome agents and LLM tools", json.dumps(["awesome", "awesome-list", "llm"]),
            "CC0-1.0", 3500, 400, 5, "ok", "2026-10-20", "2024-01-01",
            "# Awesome Agents\nA curated list of awesome agents!\n## List\n- Agent 1\n- Agent 2\n",
            "2026-10-01T00:00:00Z", "2026-10-27T00:00:00Z", "2026-10-27T00:00:00Z"
        )
    )
    conn.execute(
        "INSERT INTO repos (ghr_id, node_id, full_name, url, language, description, topics, "
        "license, stars, forks, open_issues, enrich_status, pushed_at, created_at, readme, "
        "first_seen, last_seen, enriched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            102, "node102", "dev/py-client", "https://github.com/dev/py-client",
            "Python", "Python SDK and library for interacting with our cloud API", json.dumps(["sdk", "client", "python"]),
            "MIT", 4200, 310, 20, "ok", "2026-10-22", "2023-01-01",
            "# py-client\nOfficial Python SDK.\n```bash\npip install py-client\n```\nRequires OPENAI_API_KEY.\n",
            "2026-10-01T00:00:00Z", "2026-10-27T00:00:00Z", "2026-10-27T00:00:00Z"
        )
    )
    conn.execute(
        "INSERT INTO repos (ghr_id, node_id, full_name, url, language, description, topics, "
        "license, stars, forks, open_issues, enrich_status, pushed_at, created_at, readme, "
        "first_seen, last_seen, enriched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            103, "node103", "enterprise/flow-app", "https://github.com/enterprise/flow-app",
            "TypeScript", "Self-hosted workflow automation web app", json.dumps(["workflow", "app", "dashboard"]),
            "Apache-2.0", 12000, 2500, 80, "ok", "2026-10-25", "2022-01-01",
            "# Flow App\nDeployable web UI workflow engine.\n"
            "```bash\ndocker run -p 8080:8080 enterprise/flow-app\n```\n"
            "Configuration:\n- OPENAI_API_KEY required for AI steps\n- PINECONE_API_KEY required for vector memory\n"
            "Supports docker-compose.yml and systemd daemon workers.\n",
            "2026-10-01T00:00:00Z", "2026-10-27T00:00:00Z", "2026-10-27T00:00:00Z"
        )
    )
    conn.execute(
        "INSERT INTO repos (ghr_id, node_id, full_name, url, language, description, topics, "
        "license, stars, forks, open_issues, enrich_status, pushed_at, created_at, readme, "
        "first_seen, last_seen, enriched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            104, "node104", "media/transcode-srv", "https://github.com/media/transcode-srv",
            "Rust", "Video transcoding daemon using ffmpeg and cuda", json.dumps(["video", "transcoder", "ffmpeg"]),
            "AGPL-3.0", 5000, 450, 15, "ok", "2026-10-20", "2023-05-01",
            "# Transcode Service\nRequires ffmpeg and nvidia CUDA for hardware acceleration.\n"
            "Runs a background worker daemon and writes to sqlite3 persistent disk.\n",
            "2026-10-01T00:00:00Z", "2026-10-27T00:00:00Z", "2026-10-27T00:00:00Z"
        )
    )
    # Add star snapshots for launch spike repo (105)
    conn.execute(
        "INSERT INTO repos (ghr_id, node_id, full_name, url, language, description, topics, "
        "license, stars, forks, open_issues, enrich_status, pushed_at, created_at, readme, "
        "first_seen, last_seen, enriched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            105, "node105", "hype/quick-ai", "https://github.com/hype/quick-ai",
            "Python", "Viral AI helper", json.dumps(["ai"]),
            "MIT", 4000, 200, 10, "ok", "2026-10-25", "2026-10-01",
            "# Quick AI\nViral tool released recently.\n",
            "2026-10-01T00:00:00Z", "2026-10-27T00:00:00Z", "2026-10-27T00:00:00Z"
        )
    )
    # Snapshot series: massive spike in first 3 days, then flat for 15+ days
    conn.execute("INSERT INTO repo_stats (ghr_id, day, stars, forks) VALUES (105, '2026-10-01', 500, 20)")
    conn.execute("INSERT INTO repo_stats (ghr_id, day, stars, forks) VALUES (105, '2026-10-02', 2500, 100)")
    conn.execute("INSERT INTO repo_stats (ghr_id, day, stars, forks) VALUES (105, '2026-10-03', 3800, 180)")
    for d in range(4, 26):
        conn.execute(f"INSERT INTO repo_stats (ghr_id, day, stars, forks) VALUES (105, '2026-10-{d:02d}', 3990, 200)")

    # Add demand records for 103
    conn.execute(
        "INSERT INTO repo_demand (ghr_id, help_wanted, bounties, fetched_at) "
        "VALUES (103, 4, 2, '2026-10-26T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO repo_issues (ghr_id, number, title, url, reactions, comments, labels, created_at) "
        "VALUES (103, 42, 'Add SAML SSO and Audit Log for enterprise compliance', 'https://github.com/enterprise/flow-app/issues/42', 85, 12, '[\"feature\", \"bounty\"]', '2026-09-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO repo_issues (ghr_id, number, title, url, reactions, comments, labels, created_at) "
        "VALUES (103, 43, 'Docker deployment fails on ARM64 / Kubernetes', 'https://github.com/enterprise/flow-app/issues/43', 45, 8, '[\"bug\", \"help wanted\"]', '2026-09-02T00:00:00Z')"
    )

    conn.commit()
    conn.close()
    return p


@pytest.fixture
def custom_db(custom_db_path: Path):
    d = ReadDb(custom_db_path)
    yield d
    d.close()


# -----------------------------------------------------------------------------
# Tool 1: classify_artifact [F1, F10]
# -----------------------------------------------------------------------------
def test_classify_artifact_f1_prevention(custom_db):
    # Awesome list cannot be deployable app
    res_list = bt.classify_artifact(custom_db, "curator/awesome-agents")
    assert res_list["kind"] == "awesome_list"
    assert res_list["deployable"] is False
    assert "hosted_app" not in res_list["feasible_saas_shapes"]
    assert res_list["data_coverage"] in ("complete", "partial")

    # SDK / library
    res_sdk = bt.classify_artifact(custom_db, "dev/py-client")
    assert res_sdk["kind"] in ("sdk", "library")
    assert res_sdk["deployable"] is False
    assert "remote_execution_driver" in res_sdk["feasible_saas_shapes"] or "managed_api" in res_sdk["feasible_saas_shapes"]

    # Deployable App
    res_app = bt.classify_artifact(custom_db, "enterprise/flow-app")
    assert res_app["kind"] == "app"
    assert res_app["deployable"] is True
    assert "hosted_app" in res_app["feasible_saas_shapes"]

    # Unknown repo
    res_missing = bt.classify_artifact(custom_db, "nonexistent/repo")
    assert res_missing["kind"] == "unknown"
    assert res_missing["deployable"] is False
    assert res_missing["data_coverage"] == "missing"


# -----------------------------------------------------------------------------
# Tool 2: get_runtime_dependencies [F2]
# -----------------------------------------------------------------------------
def test_get_runtime_dependencies_f2_lockin(custom_db):
    res = bt.get_runtime_dependencies(custom_db, "enterprise/flow-app")
    assert res["repo"] == "enterprise/flow-app"
    req_names = [s["name"] for s in res["required_services"]]
    assert "OpenAI" in req_names
    assert "Pinecone" in req_names
    # Pinecone and OpenAI are proprietary paid backends -> lock_in_risk is high or medium
    assert res["lock_in_risk"] in ("medium", "high")
    assert len(res["required_services"][0]["evidence"]) > 0

    # Repo without proprietary lock-in
    res_clean = bt.get_runtime_dependencies(custom_db, "acme/golang-api")
    assert res_clean["lock_in_risk"] == "low"


# -----------------------------------------------------------------------------
# Tool 3: classify_growth [F3]
# -----------------------------------------------------------------------------
def test_classify_growth_f3_velocity_misread(custom_db):
    # Quick-ai had 500->2500->3800 in 3 days then flat -> launch spike
    res_spike = bt.classify_growth(custom_db, "hype/quick-ai", days=60)
    assert res_spike["pattern"] in ("launch_spike", "flat")
    assert res_spike["daily_gain"]["peak"] >= 1000
    assert res_spike["confidence"] >= 0.5

    # Repos with no snapshots
    res_no_snap = bt.classify_growth(custom_db, "curator/awesome-agents", days=30)
    assert res_no_snap["pattern"] == "insufficient_history"
    assert res_no_snap["projected_stars_30d"] is None


# -----------------------------------------------------------------------------
# Tool 4: get_package_adoption [F3, F4]
# -----------------------------------------------------------------------------
def test_get_package_adoption(custom_db):
    res = bt.get_package_adoption(custom_db, "dev/py-client")
    assert len(res["packages"]) >= 1
    pkg = res["packages"][0]
    assert pkg["registry"] == "pypi"
    assert pkg["package"] == "py-client"
    # Null preservation: downloads must be None, not 0
    assert pkg["downloads_total"] is None
    assert pkg["downloads_30d"] is None


# -----------------------------------------------------------------------------
# Tool 5: analyze_forks [F4]
# -----------------------------------------------------------------------------
def test_analyze_forks_f4_fork_misread(custom_db):
    # enterprise/flow-app has deployable config (docker, etc.)
    res = bt.analyze_forks(custom_db, "enterprise/flow-app", sample_size=100)
    assert res["interpretation"] in ("production_customization", "mixed")
    # Offline index preserves null for live git metrics
    assert res["with_deploy_config"] is None
    assert 0.0 <= res["confidence"] <= 1.0

    # awesome list forks are template copies or abandoned
    res_list = bt.analyze_forks(custom_db, "curator/awesome-agents", sample_size=100)
    assert res_list["interpretation"] in ("template_copies", "abandoned", "mixed")


# -----------------------------------------------------------------------------
# Tool 6: get_maintainer_health [SLA / services]
# -----------------------------------------------------------------------------
def test_get_maintainer_health(custom_db):
    res = bt.get_maintainer_health(custom_db, "enterprise/flow-app", months=6)
    assert res["risk"] in ("low", "medium", "high")
    assert "enterprise" in res["top_affiliations"]
    assert res["as_of"] is not None


# -----------------------------------------------------------------------------
# Tool 7: classify_issues [F9]
# -----------------------------------------------------------------------------
def test_classify_issues_f9_empty_demand_and_clustering(custom_db):
    # Repo with fetched demand
    res = bt.classify_issues(custom_db, "enterprise/flow-app", top_n=50)
    assert res["data_coverage"] == "complete"
    assert res["help_wanted_count"] == 4
    assert res["bounty_count"] == 2
    # Verify cluster detection (compliance for SAML SSO, hosting_deployment for Docker/K8s)
    labels = [c["label"] for c in res["clusters"]]
    assert "compliance" in labels
    assert "hosting_deployment" in labels
    assert "compliance" in res["monetizable_pain"]

    # Repo with UNFETCHED demand -> must never report "0 bounties" as validated no demand!
    res_unfetched = bt.classify_issues(custom_db, "curator/awesome-agents")
    assert res_unfetched["data_coverage"] == "missing"
    assert res_unfetched["bounty_count"] is None
    assert res_unfetched["help_wanted_count"] is None


# -----------------------------------------------------------------------------
# Tool 8: get_commercial_landscape [F5]
# -----------------------------------------------------------------------------
def test_get_commercial_landscape(custom_db):
    res = bt.get_commercial_landscape(custom_db, full_name="enterprise/flow-app")
    assert res["category"] is not None
    assert len(res["vendors"]) >= 1
    v = res["vendors"][0]
    assert v["type"] in ("managed_service", "api", "platform", "enterprise_edition", "consultancy")


# -----------------------------------------------------------------------------
# Tool 9: get_company_events [F5]
# -----------------------------------------------------------------------------
def test_get_company_events(custom_db):
    res = bt.get_company_events(custom_db, "enterprise/flow-app")
    assert res["repo"] == "enterprise/flow-app"
    assert isinstance(res["events"], list)
    assert res["data_coverage"] in ("complete", "partial")


# -----------------------------------------------------------------------------
# Tool 10: check_name_collision [F6]
# -----------------------------------------------------------------------------
def test_check_name_collision(custom_db):
    # Should detect collision with "flow-app"
    res = bt.check_name_collision(custom_db, "flow-app")
    assert res["risk"] in ("medium", "high")
    matched_repos = [c["identifier"] for c in res["collisions"]]
    assert "enterprise/flow-app" in matched_repos

    # Random novel name -> low risk
    res_novel = bt.check_name_collision(custom_db, "zyxwv-random-987654")
    assert res_novel["risk"] == "low"
    assert len(res_novel["collisions"]) == 0


# -----------------------------------------------------------------------------
# Tool 11: license_audit [F7]
# -----------------------------------------------------------------------------
def test_license_audit_f7_license_blindspot(custom_db):
    # AGPL project with ffmpeg binary
    res_agpl = bt.license_audit(custom_db, "media/transcode-srv")
    assert res_agpl["verdict"]["hosted_saas"] == "blocked"
    assert res_agpl["verdict"]["closed_distribution"] == "blocked"
    # System binary ffmpeg should be noted in dependencies
    dep_names = [d["dep"] for d in res_agpl["dependencies"]]
    assert "ffmpeg" in dep_names

    # Permissive MIT project
    res_mit = bt.license_audit(custom_db, "acme/golang-api")
    assert res_mit["verdict"]["hosted_saas"] == "ok"
    assert res_mit["verdict"]["closed_distribution"] == "ok"


# -----------------------------------------------------------------------------
# Tool 12: platform_compat [F8]
# -----------------------------------------------------------------------------
def test_platform_compat_f8_platform_blindspot(custom_db):
    # media/transcode-srv requires CUDA, background daemon, persistent disk
    res = bt.platform_compat(custom_db, "media/transcode-srv")
    reqs = res["requirements"]
    assert reqs["gpu"] is True
    assert reqs["long_running"] is True
    assert reqs["persistent_disk"] is True

    # Serverless platforms like Vercel or Cloudflare should be unsupported or restricted
    plat_map = {p["name"]: p["status"] for p in res["platforms"]}
    assert plat_map.get("Vercel") in ("unsupported", "restricted")
    # Container platforms should be supported
    assert plat_map.get("Docker / VPS") == "supported"


# -----------------------------------------------------------------------------
# Tool 13: saas_base [composite]
# -----------------------------------------------------------------------------
def test_saas_base_composite(custom_db):
    res = bt.saas_base_eval(custom_db, "enterprise/flow-app")
    assert res["recommended_shape"] == "hosted_app"
    assert len(res["moat"]) > 0
    assert len(res["kill_tests"]) > 0
    assert 0.0 <= res["confidence"] <= 1.0


# -----------------------------------------------------------------------------
# Tool 14: evaluate_brief [composite end-to-end]
# -----------------------------------------------------------------------------
def test_evaluate_brief_end_to_end(custom_db):
    claims = {
        "velocity": "breakout_growth",
        "license": "permissive",
        "demand": "validated_bounties",
    }
    res = bt.evaluate_brief(
        custom_db,
        "enterprise/flow-app",
        angles=["saas", "services", "plugin"],
        brief_claims=claims,
    )
    assert res["verdict"] in ("pursue", "narrow", "reject")
    assert len(res["corrected_signals"]) >= 2
    assert len(res["kill_tests"]) >= 1
    assert len(res["next_checks"]) >= 1
    # Check signal correction
    sig_map = {s["claim"]: s["status"] for s in res["corrected_signals"]}
    assert any("velocity" in k for k in sig_map)
    assert any("license" in k for k in sig_map)


# -----------------------------------------------------------------------------
# Envelope Invariants across Toolbox
# -----------------------------------------------------------------------------
def test_toolbox_envelope_invariants(custom_db, settings):
    tb = Toolbox(custom_db, settings)
    # Call multiple tools and assert standard envelope
    tools_to_test = [
        ("classify_artifact", {"full_name": "enterprise/flow-app"}),
        ("get_runtime_dependencies", {"full_name": "enterprise/flow-app"}),
        ("classify_growth", {"full_name": "enterprise/flow-app", "days": 30}),
        ("get_package_adoption", {"full_name": "enterprise/flow-app"}),
        ("analyze_forks", {"full_name": "enterprise/flow-app", "sample_size": 50}),
        ("get_maintainer_health", {"full_name": "enterprise/flow-app", "months": 6}),
        ("classify_issues", {"full_name": "enterprise/flow-app", "top_n": 50}),
        ("get_commercial_landscape", {"full_name": "enterprise/flow-app"}),
        ("get_company_events", {"full_name": "enterprise/flow-app"}),
        ("check_name_collision", {"name": "flow-app"}),
        ("license_audit", {"full_name": "enterprise/flow-app"}),
        ("platform_compat", {"full_name": "enterprise/flow-app"}),
        ("saas_base", {"idea": "enterprise/flow-app"}),
        ("evaluate_brief", {"full_name": "enterprise/flow-app"}),
    ]

    for name, args in tools_to_test:
        out = tb.call(name, args)
        assert "as_of" in out, f"{name} missing as_of"
        assert "data_coverage" in out, f"{name} missing data_coverage"
        assert out["data_coverage"] in ("complete", "partial", "missing"), f"{name} invalid data_coverage: {out['data_coverage']}"
        assert "sources" in out, f"{name} missing sources"
        assert isinstance(out["sources"], list), f"{name} sources must be a list"
