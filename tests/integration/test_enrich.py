import httpx
from ossdex_collector.enrich import (
    MAX_PAPERS_PER_REPO,
    arxiv_ids,
    enrich_all,
    extract_papers,
    fetch_paper_titles,
    github_links,
    link_awesome,
    parse_atom,
)
from ossdex_core.chunks import index_chunks
from ossdex_core.store import connect, now_iso, prune


def add_repo(conn, i, name, *, readme=None, topics="[]", status="ok", sha=None):
    conn.execute("INSERT INTO repos (ghr_id, full_name, topics, readme, readme_sha, stars, "
                 "enrich_status) VALUES (?,?,?,?,?,?,?)",
                 (i, name, topics, readme, sha or (f"sha{i}" if readme else None), 100, status))


def make_list(conn, n_targets=25, extra=""):
    for i in range(n_targets):
        add_repo(conn, 100 + i, f"org/proj{i}")
    body = "# Awesome Foo\n[![Awesome](https://awesome.re/badge.svg)](https://github.com/sindresorhus/awesome)\n"
    body += "## Web\n" + "\n".join(f"- [p{i}](https://github.com/org/proj{i}/tree/main)" for i in range(15))
    body += "\n## CLI\n" + "\n".join(f"- [p{i}](https://github.com/Org/Proj{i}.git#readme)"
                                      for i in range(15, n_targets)) + extra
    add_repo(conn, 1, "foo/awesome-foo", readme=body, topics='["awesome-list"]')


def test_github_links_normalize_and_track_sections():
    text = "# Top\n## [Web](#web) tools\n- https://github.com/a/b.git?x=1\n- github.com/c/d/blob/m/x.md#L1\n"
    assert github_links(text) == [("Web tools", "a/b"), ("Web tools", "c/d")]


def test_arxiv_ids():
    text = ("arxiv.org/abs/2301.00001v2 and https://arxiv.org/pdf/2301.00001 "
            "huggingface.co/papers/2402.12345 old arxiv.org/abs/cs/0601001")
    assert arxiv_ids(text) == ["2301.00001", "2402.12345"]


def test_link_awesome(tmp_path):
    conn = connect(tmp_path / "t.db")
    make_list(conn)
    add_repo(conn, 2, "tiny/awesome-tiny", readme="# t\n- https://github.com/org/proj1",
             topics='["awesome-list"]')
    add_repo(conn, 3, "wm/awesome", readme="# wm\n" + "https://github.com/org/proj1 " * 30)  # no topic
    assert link_awesome(conn) == {"lists": 1, "links": 25}
    rows = {r[0]: r[1] for r in conn.execute("SELECT ghr_id, section FROM repo_lists")}
    assert rows[100] == "Web" and rows[120] == "CLI"
    assert 1 not in rows  # not the list itself
    conn.execute("UPDATE repos SET enrich_status = 'below' WHERE ghr_id = 100")
    assert link_awesome(conn)["links"] == 24  # hidden repos are not tagged
    conn.close()


def test_extract_papers_incremental_and_reading_lists(tmp_path):
    conn = connect(tmp_path / "t.db")
    add_repo(conn, 1, "a/model", readme="see arxiv.org/abs/2301.00001v1")
    many = " ".join(f"arxiv.org/abs/2301.{i:05d}" for i in range(MAX_PAPERS_PER_REPO + 1))
    add_repo(conn, 2, "a/papers", readme=many)
    assert extract_papers(conn) == {"scanned": 2, "repos_with_papers": 1, "reading_lists_skipped": 1}
    assert conn.execute("SELECT arxiv_id FROM repo_papers").fetchall()[0][0] == "2301.00001"
    assert extract_papers(conn)["scanned"] == 0  # same sha: untouched
    conn.execute("UPDATE repos SET readme = 'none', readme_sha = 'new' WHERE ghr_id = 1")
    assert extract_papers(conn)["scanned"] == 1
    assert conn.execute("SELECT COUNT(*) FROM repo_papers").fetchone()[0] == 0
    conn.close()


ATOM = """<feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/2301.00001v1</id><title>A  Great
 Paper</title><published>2023-01-01T00:00:00Z</published></entry></feed>"""


def test_parse_atom():
    assert parse_atom(ATOM) == {"2301.00001": ("A Great Paper", "2023-01-01T00:00:00Z")}


def test_fetch_titles_uses_injected_client_and_skips_known(tmp_path):
    conn = connect(tmp_path / "t.db")
    conn.executemany("INSERT INTO repo_papers VALUES (?,?)", [(1, "2301.00001"), (1, "2301.00002")])
    conn.execute("INSERT INTO papers VALUES ('2301.00002', 'Known', NULL, ?)", (now_iso(),))
    seen = []

    def handler(request):
        seen.append(request.url.params["id_list"])
        return httpx.Response(200, text=ATOM)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_paper_titles(conn, client=client, delay=0) == {"titles": 1, "unknown": 0, "pending": 0}
    assert seen == ["2301.00001"]
    assert conn.execute("SELECT title FROM papers WHERE arxiv_id = '2301.00001'").fetchone()[0] == "A Great Paper"
    assert fetch_paper_titles(conn, client=client, delay=0)["titles"] == 0 and len(seen) == 1
    conn.close()


def test_fetch_titles_http_error_leaves_pending(tmp_path):
    conn = connect(tmp_path / "t.db")
    conn.execute("INSERT INTO repo_papers VALUES (1, '2301.00001')")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    assert fetch_paper_titles(conn, client=client, delay=0)["pending"] == 1
    conn.close()


def test_card_and_prune(tmp_path):
    conn = connect(tmp_path / "t.db")
    make_list(conn)
    add_repo(conn, 2, "a/model", readme="arxiv.org/abs/2301.00001")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=ATOM)))
    enrich_all(conn, client=client, delay=0)
    index_chunks(conn)
    card = conn.execute("SELECT text FROM chunks WHERE ghr_id = 100 AND kind = 'card'").fetchone()[0]
    assert "Listed in: awesome-foo (Web)" in card
    card = conn.execute("SELECT text FROM chunks WHERE ghr_id = 2 AND kind = 'card'").fetchone()[0]
    assert "README mentions papers: A Great Paper" in card
    conn.execute("UPDATE repos SET enrich_status = 'gone' WHERE ghr_id IN (1, 2)")
    prune(conn)
    assert conn.execute("SELECT COUNT(*) FROM repo_lists").fetchone()[0] == 0  # its list is gone
    assert conn.execute("SELECT COUNT(*) FROM repo_papers").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM paper_src WHERE ghr_id = 2").fetchone()[0] == 0
    conn.close()
