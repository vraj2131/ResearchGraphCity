from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from app.openalex_client import OpenAlexCancelled, OpenAlexClient, OpenAlexError, RequestRateLimiter, ThreadLocalSession


@dataclass
class FakeResponse:
    payload: dict
    status_code: int = 200
    headers: dict | None = None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        if not self.responses:
            raise AssertionError("Unexpected OpenAlex request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, fingerprint):
        return self.values.get(fingerprint)

    def put(self, fingerprint, response, status):
        self.values[fingerprint] = response


def work(work_id: str, title: str = "Paper") -> dict:
    return {"id": f"https://openalex.org/{work_id}", "title": title, "doi": None}


def test_request_reuses_fingerprint_cache():
    session = FakeSession([FakeResponse({"results": [work("W1")], "meta": {}})])
    cache = MemoryCache()
    client = OpenAlexClient(api_key="key", session=session, cache=cache)

    first = client.request("/works", {"search": "graph", "per_page": 100})
    second = client.request("/works", {"per_page": 100, "search": "graph"})

    assert first == second
    assert len(session.calls) == 1
    assert session.calls[0][1]["api_key"] == "key"


def test_iter_pages_follows_cursor_and_stops_at_limit():
    session = FakeSession(
        [
            FakeResponse({"results": [work("W1"), work("W2")], "meta": {"next_cursor": "next"}}),
            FakeResponse({"results": [work("W3"), work("W4")], "meta": {"next_cursor": "last"}}),
        ]
    )
    client = OpenAlexClient(api_key=None, session=session)

    results = list(client.iter_works({"search": "graph"}, limit=3, per_page=2))

    assert [item["id"].rsplit("/", 1)[-1] for item in results] == ["W1", "W2", "W3"]
    assert session.calls[1][1]["cursor"] == "next"


def test_retry_after_is_respected_for_retryable_status():
    sleeps = []
    session = FakeSession(
        [
            FakeResponse({"error": "limited"}, status_code=429, headers={"Retry-After": "2"}),
            FakeResponse({"results": [], "meta": {}}),
        ]
    )
    client = OpenAlexClient(api_key=None, session=session, sleep=sleeps.append, max_retries=2)

    client.request("/works", {"search": "graph"})

    assert sleeps == [2.0]
    assert len(session.calls) == 2


def test_non_retryable_status_raises_clear_error():
    client = OpenAlexClient(api_key=None, session=FakeSession([FakeResponse({}, status_code=400)]))

    with pytest.raises(OpenAlexError, match="status 400"):
        client.request("/works", {"search": "bad"})


def test_resolve_reports_id_doi_and_title_provenance():
    session = FakeSession(
        [
            FakeResponse(work("W123", "ID paper")),
            FakeResponse({"results": [work("W456", "DOI paper")], "meta": {}}),
            FakeResponse({"results": [work("W789", "Title paper")], "meta": {}}),
        ]
    )
    client = OpenAlexClient(api_key=None, session=session)

    assert client.resolve_seed("https://openalex.org/W123").match_type == "openalex_id"
    assert client.resolve_seed("https://doi.org/10.1000/test").match_type == "doi"
    assert client.resolve_seed("A useful paper title").match_type == "title"


def test_cancellation_is_checked_between_requests():
    client = OpenAlexClient(
        api_key=None,
        session=FakeSession([FakeResponse({"results": [], "meta": {}})]),
        cancel_check=lambda: True,
    )

    with pytest.raises(OpenAlexCancelled):
        client.request("/works", {"search": "graph"})


def test_fetch_by_ids_batches_and_deduplicates_ids():
    session = FakeSession([FakeResponse({"results": [work("W1"), work("W2")], "meta": {"next_cursor": None}})])
    client = OpenAlexClient(api_key=None, session=session)

    results = list(client.fetch_works_by_ids(["W1", "https://openalex.org/W2", "W1"]))

    assert len(results) == 2
    assert session.calls[0][1]["filter"] == "openalex_id:W1|W2"


def test_malformed_works_payload_is_rejected():
    client = OpenAlexClient(api_key=None, session=FakeSession([FakeResponse({"meta": {}})]))

    with pytest.raises(OpenAlexError, match="missing results"):
        list(client.iter_works({"search": "graph"}, limit=1))


def test_rate_limiter_spaces_request_starts():
    current = [10.0]
    sleeps = []

    def sleep(delay):
        sleeps.append(delay)
        current[0] += delay

    limiter = RequestRateLimiter(0.5, clock=lambda: current[0], sleep=sleep)
    limiter.acquire()
    limiter.acquire()

    assert sleeps == [0.5]


def test_thread_local_session_creates_one_http_session_per_worker():
    created = []
    lock = Lock()

    class Session:
        def __init__(self, identifier):
            self.identifier = identifier

    def factory():
        with lock:
            session = Session(len(created))
            created.append(session)
            return session

    sessions = ThreadLocalSession(factory)
    barrier = Barrier(2)

    def session_identifier(_):
        identifier = sessions.current().identifier
        barrier.wait()
        return identifier

    with ThreadPoolExecutor(max_workers=2) as executor:
        identifiers = list(executor.map(session_identifier, range(2)))

    assert sorted(identifiers) == [0, 1]
