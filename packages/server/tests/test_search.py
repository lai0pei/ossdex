
import pytest
from ossdex_server import repo_query as rq
from ossdex_server.search import fts_query, query_terms, readme_sections, search, similar


def names(hits):
    return [h["full_name"] for h in hits]


def test_query_terms_drop_stopwords():
    assert query_terms("what would be the AI project which are based on langchain") == [
        "ai", "based", "langchain"]
    assert query_terms("the and of") == ["the", "and", "of"]  # never empty


def test_langchain_ranks_the_langchain_repo_first(db):
    hits = search(db, "AI projects based on langchain")
    assert names(hits)[0] == "acme/langchain-agent"
    assert "acme/rag-kit" in names(hits)  # README mentions langchain, no topic
    top = hits[0]
    assert {"topic", "keyword"} & set(top["why"])



def test_filters_apply(db):
    hits = search(db, "langchain", rq.RepoFilters(languages=["rust"]))
    assert all(h["language"] == "Rust" for h in hits)
    hits = search(db, "database", rq.RepoFilters(min_stars=2500))
    assert "acme/rust-db" in names(hits)
    assert search(db, "go", rq.RepoFilters(languages=["cobol"])) == []


def test_growth_filter_in_search(db):
    hits = search(db, "database vector langchain", rq.RepoFilters(min_gain=130))
    assert names(hits) and set(names(hits)) <= {"acme/langchain-agent", "foo/vector-search"}
    assert "acme/rust-db" not in names(hits)  # no measurable gain


def test_bare_repos_are_found_by_name_and_language(db):
    hits = search(db, "unenriched")
    assert "bare/unenriched" in names(hits)
    go = search(db, "go projects", rq.RepoFilters(languages=["go"]))
    assert {"bare/unenriched", "acme/golang-api"} <= set(names(go))


def test_gone_repos_never_returned(db):
    assert "gone/deleted" not in names(search(db, "deleted removed"))



def test_snippet_comes_from_readme_chunk(db):
    hit = next(h for h in search(db, "agents with langchain and any llm")
               if h["full_name"] == "acme/langchain-agent")
    assert hit["snippet"] and "langchain" in hit["snippet"].lower()
    assert len(hit["snippet"]) <= 400


def test_readme_sections(db):
    secs = readme_sections(db, 2, "agents")
    assert secs and "langchain" in secs[0]["text"].lower()
    assert readme_sections(db, 6, "anything") == []  # no README



def test_similar_matches_by_description_and_topics_without_the_repo_itself(db):
    res = similar(db, "acme/langchain-agent", limit=3)
    got = names(res["repos"])
    assert got and "acme/langchain-agent" not in got and "acme/rag-kit" in got


def test_similar_honours_filters_and_unknown_repos(db):
    res = similar(db, "acme/langchain-agent", rq.RepoFilters(languages=["rust"]), limit=5)
    assert all(h["language"] == "Rust" for h in res["repos"])
    assert similar(db, "nobody/nothing") is None


@pytest.mark.parametrize("q", ['"unbalanced', "a* OR -b", "NEAR(x y)", "x AND", "col:val", "'; --"])
def test_hostile_query_text_never_breaks_fts(db, q):
    search(db, q)  # must not raise a malformed MATCH error
    match = fts_query(q)
    assert match is None or all(t.startswith('"') for t in match.split(" OR "))
