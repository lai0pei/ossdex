import json

import httpx
import pytest
import respx
from ossdex_collector.github import BudgetExhausted, GitHub, GithubError, RateLimited, ServerError

from testsupport.fake_github import BASE, FakeGitHub, make_repo


class Clock:
    """A fake clock: `sleep` advances it, so waits are visible and instant."""

    def __init__(self):
        self.t = 1_000_000.0
        self.slept: list[float] = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def client(fake, clock, **kw):
    mock = respx.mock(base_url=BASE, assert_all_called=False)
    mock.route().mock(side_effect=fake.handler)
    mock.start()
    gh = GitHub("secret-token-value", base_url=BASE, sleep=clock.sleep, now=clock.now,
                min_interval=0, **kw)
    return gh, mock


def test_search_count_and_page():
    fake = FakeGitHub([make_repo(i, stars=1000 + i) for i in range(5)])
    gh, mock = client(fake, Clock())
    try:
        assert gh.search_count("stars:>=1000") == 5
        nodes, page, total = gh.search_page("stars:>=1000")
        assert total == 5 and not page["hasNextPage"]
        assert [n["stargazerCount"] for n in nodes] == [1004, 1003, 1002, 1001, 1000]
        assert gh.top_stars("stars:>=1000") == 1004
    finally:
        mock.stop()


def test_a_token_is_required():
    with pytest.raises(GithubError, match="token"):
        GitHub("")


def test_a_bad_token_error_does_not_leak_it():
    fake = FakeGitHub([])
    fake.statuses = [401]
    gh, mock = client(fake, Clock())
    try:
        with pytest.raises(GithubError) as e:
            gh.search_count("x")
        assert "secret-token-value" not in str(e.value) and "401" in str(e.value)
    finally:
        mock.stop()


def test_server_errors_are_retried_with_backoff():
    fake = FakeGitHub([make_repo(1, stars=5)])
    fake.statuses = [502, 502, 200]
    clock = Clock()
    gh, mock = client(fake, clock)
    try:
        assert gh.search_count("stars:>=1") == 1
        assert clock.slept == [2.0, 4.0]
    finally:
        mock.stop()


def test_persistent_server_errors_give_up():
    fake = FakeGitHub([])
    fake.statuses = [502] * 10
    gh, mock = client(fake, Clock())
    try:
        with pytest.raises(GithubError, match="502"):
            gh.search_count("x")
    finally:
        mock.stop()


def test_retry_after_is_honored():
    fake = FakeGitHub([make_repo(1, stars=5)])
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(403, text="secondary rate limit", headers={"retry-after": "30"})
        return fake.handler(request)

    clock = Clock()
    mock = respx.mock(base_url=BASE)
    mock.route().mock(side_effect=handler)
    mock.start()
    try:
        gh = GitHub("t", base_url=BASE, sleep=clock.sleep, now=clock.now, min_interval=0)
        assert gh.search_count("stars:>=1") == 1
        assert 30 <= clock.slept[0] <= 32
    finally:
        mock.stop()


def test_a_far_primary_reset_raises_so_the_run_can_resume():
    fake = FakeGitHub([make_repo(1, stars=5)])
    fake.fail_after_pages = 0
    gh, mock = client(fake, Clock())
    try:
        with pytest.raises(RateLimited, match="Run the command again"):
            gh.search_page("stars:>=1")
    finally:
        mock.stop()


def test_low_remaining_with_a_near_reset_waits_then_continues():
    fake = FakeGitHub([make_repo(1, stars=5)])
    clock = Clock()
    gh, mock = client(fake, clock)
    try:
        gh.search_count("stars:>=1")
        gh.remaining, gh.reset_at = 10, clock.t + 40  # nearly out of points, reset in 40s
        gh.search_count("stars:>=1")
        assert 40 <= clock.slept[0] <= 42
    finally:
        mock.stop()


def test_low_remaining_with_a_far_reset_raises():
    fake = FakeGitHub([make_repo(1, stars=5)])
    clock = Clock()
    gh, mock = client(fake, clock)
    try:
        gh.search_count("stars:>=1")
        gh.remaining, gh.reset_at = 10, clock.t + 3000
        with pytest.raises(RateLimited):
            gh.search_count("stars:>=1")
    finally:
        mock.stop()


def test_the_point_budget_stops_the_run():
    fake = FakeGitHub([make_repo(1, stars=5)])
    gh, mock = client(fake, Clock(), budget=2)
    try:
        gh.search_count("a")
        gh.search_count("a")
        with pytest.raises(BudgetExhausted, match="2-point budget"):
            gh.search_count("a")
        assert gh.spent == 2
    finally:
        mock.stop()


def test_errors_inside_a_200_are_retried_then_raised_not_used():
    fake = FakeGitHub([make_repo(1, stars=5)])
    fake.poison = {1}
    clock = Clock()
    gh, mock = client(fake, clock)
    try:
        with pytest.raises(GithubError, match="Something went wrong"):
            gh.search_page("stars:>=1")  # data={"search": null} + errors: must not be unpacked
        assert clock.slept == [2.0, 4.0, 8.0] and fake.search_pages == 4
    finally:
        mock.stop()


def test_a_transient_error_in_a_200_recovers():
    fake = FakeGitHub([make_repo(1, stars=5)])
    fake.poison = {1}
    clock = Clock()
    gh, mock = client(fake, clock)
    real = fake.handler
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 2:
            fake.poison = set()  # GitHub recovered
        return real(request)

    mock.routes[0].mock(side_effect=flaky)
    try:
        nodes, _, total = gh.search_page("stars:>=1")
        assert total == 1 and len(nodes) == 1 and clock.slept == [2.0]
    finally:
        mock.stop()


def test_not_found_errors_just_leave_nulls():
    def handler(request):
        return httpx.Response(200, json={"data": {"nodes": [None]}, "errors": [
            {"type": "NOT_FOUND", "message": "Could not resolve to a node with the global id of 'R_9'"}]})

    mock = respx.mock(base_url=BASE)
    mock.route().mock(side_effect=handler)
    mock.start()
    try:
        gh = GitHub("t", base_url=BASE, sleep=lambda s: None, min_interval=0)
        assert gh.nodes_by_ids(["R_9"]) == [None]
    finally:
        mock.stop()


def test_rate_limited_error_in_a_200_raises():
    def handler(request):
        return httpx.Response(200, json={"errors": [{"type": "RATE_LIMITED", "message": "API rate limit"}]})

    mock = respx.mock(base_url=BASE)
    mock.route().mock(side_effect=handler)
    mock.start()
    try:
        gh = GitHub("t", base_url=BASE, sleep=lambda s: None, min_interval=0)
        with pytest.raises(RateLimited):
            gh.search_count("x")
    finally:
        mock.stop()


def test_readmes_graphql_variants_and_rest_fallback():
    repos = [make_repo(1, stars=5), make_repo(2, stars=5, readme={"readme.md": "lower"}),
             make_repo(3, stars=5, readme={}), make_repo(4, stars=5, readme={})]
    fake = FakeGitHub(repos)
    fake.rest_readmes[repos[2]["name"].lower()] = "# from rest (README.markdown)"
    gh, mock = client(fake, Clock())
    try:
        got = gh.readmes([(r["id"], r["name"]) for r in repos] + [(99, "no/where")])
        assert got[1][0].startswith("# repo1") and got[2][0] == "lower"
        assert got[3][0] == "# from rest (README.markdown)" and len(got[3][1]) == 40  # sha1 hex
        assert got[4] is None  # no README at all
        assert got[99] is None  # repo does not exist
    finally:
        mock.stop()


def test_readme_for_a_replaced_repo_is_ignored():
    repos = [make_repo(1, stars=5)]
    fake = FakeGitHub(repos)
    gh, mock = client(fake, Clock())
    try:
        # the name now belongs to repo 1, but we asked about id 777 (the old owner of that name)
        assert gh.readmes([(777, repos[0]["name"])]) == {777: None}
    finally:
        mock.stop()


def test_a_non_json_200_is_retried_then_recovers():
    fake = FakeGitHub([make_repo(1, stars=5)])
    fake.statuses = ["html", "html", 200]
    gh, mock = client(fake, Clock())
    try:
        assert gh.search_count("stars:>=1") == 1
    finally:
        mock.stop()


def test_a_persistent_non_json_200_raises_a_github_error():
    fake = FakeGitHub([])
    fake.statuses = ["html"] * 10
    gh, mock = client(fake, Clock())
    try:
        with pytest.raises(ServerError, match="not JSON") as e:
            gh.search_count("x")
        assert isinstance(e.value, GithubError) and not isinstance(e.value, ValueError)
        assert "unicorn" not in str(e.value)
    finally:
        mock.stop()


def test_search_pages_shrink_when_github_keeps_failing():
    fake = FakeGitHub([make_repo(i, stars=1000 + i) for i in range(120)])
    fake.statuses = [502] * 4  # all attempts at the first size fail, the smaller size works
    gh, mock = client(fake, Clock())
    try:
        nodes, _, _ = gh.search_page("stars:>=1000", "10")
        assert len(nodes) == 50 and gh.search_first == 50
        sent = [json.loads(r.content)["variables"] for r in fake.seen]
        assert [v["first"] for v in sent] == [100] * 4 + [50]
        assert {v["after"] for v in sent} == {"10"}
    finally:
        mock.stop()


def test_search_pages_give_up_below_the_minimum():
    fake = FakeGitHub([make_repo(1, stars=1000)])
    fake.statuses = [502] * 50
    gh, mock = client(fake, Clock())
    try:
        with pytest.raises(ServerError):
            gh.search_page("stars:>=1000")
        assert gh.search_first == 25
    finally:
        mock.stop()
