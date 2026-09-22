from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import threading
import time
from typing import Callable, Iterator, Protocol

import requests
from sqlalchemy.orm import Session, sessionmaker

from .models import IngestionCacheRecord


OPENALEX_API_URL = "https://api.openalex.org"
WORK_SELECT = ",".join(
    (
        "id",
        "doi",
        "title",
        "abstract_inverted_index",
        "publication_year",
        "authorships",
        "primary_location",
        "topics",
        "keywords",
        "referenced_works",
        "cited_by_count",
        "open_access",
    )
)


class OpenAlexError(RuntimeError):
    pass


class OpenAlexCancelled(OpenAlexError):
    pass


class ThreadLocalSession:
    def __init__(self, factory: Callable[[], object] = requests.Session):
        self.factory = factory
        self.local = threading.local()

    def current(self):
        session = getattr(self.local, "session", None)
        if session is None:
            session = self.factory()
            self.local.session = session
        return session

    def get(self, *args, **kwargs):
        return self.current().get(*args, **kwargs)


class RequestRateLimiter:
    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.clock = clock
        self.sleep = sleep
        self.lock = threading.Lock()
        self.last_started: float | None = None

    def acquire(self) -> None:
        with self.lock:
            now = self.clock()
            if self.last_started is not None:
                delay = self.min_interval_seconds - (now - self.last_started)
                if delay > 0:
                    self.sleep(delay)
                    now = self.clock()
            self.last_started = now


class ResponseCache(Protocol):
    def get(self, fingerprint: str) -> dict | None: ...

    def put(self, fingerprint: str, response: dict, status: int) -> None: ...


class PostgresOpenAlexCache:
    def __init__(self, session_factory: sessionmaker[Session], ttl_seconds: int = 86_400):
        self.session_factory = session_factory
        self.ttl_seconds = ttl_seconds

    def get(self, fingerprint: str) -> dict | None:
        with self.session_factory() as session:
            cached = session.get(IngestionCacheRecord, fingerprint)
            if cached is None:
                return None
            now = datetime.now(timezone.utc)
            expires_at = cached.expires_at
            if expires_at is not None and expires_at.replace(tzinfo=expires_at.tzinfo or timezone.utc) <= now:
                return None
            return cached.response

    def put(self, fingerprint: str, response: dict, status: int) -> None:
        with self.session_factory.begin() as session:
            cached = session.get(IngestionCacheRecord, fingerprint)
            if cached is None:
                cached = IngestionCacheRecord(request_fingerprint=fingerprint, response=response, source_status=status)
                session.add(cached)
            cached.response = response
            cached.source_status = status
            cached.retrieved_at = datetime.now(timezone.utc)
            cached.expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)


@dataclass(frozen=True)
class ResolvedSeed:
    raw_input: str
    match_type: str
    work: dict | None


class OpenAlexClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        session=None,
        cache: ResponseCache | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
        cancel_check: Callable[[], bool] | None = None,
        rate_limiter: RequestRateLimiter | None = None,
    ):
        self.api_key = api_key
        self.session = session or ThreadLocalSession()
        self.cache = cache
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep = sleep
        self.cancel_check = cancel_check or (lambda: False)
        self.rate_limiter = rate_limiter

    def request(self, path: str, params: dict | None = None) -> dict:
        clean_params = {key: value for key, value in (params or {}).items() if value is not None}
        fingerprint = self._fingerprint(path, clean_params)
        if self.cache:
            cached = self.cache.get(fingerprint)
            if cached is not None:
                return cached
        request_params = dict(clean_params)
        if self.api_key:
            request_params["api_key"] = self.api_key

        for attempt in range(self.max_retries + 1):
            if self.cancel_check():
                raise OpenAlexCancelled("OpenAlex collection cancelled")
            try:
                if self.rate_limiter:
                    self.rate_limiter.acquire()
                response = self.session.get(
                    f"{OPENALEX_API_URL}{path}",
                    params=request_params,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise OpenAlexError("OpenAlex request failed after retries") from exc
                self.sleep(min(30.0, 2.0**attempt))
                continue
            status = int(response.status_code)
            if status == 429 or 500 <= status < 600:
                if attempt >= self.max_retries:
                    raise OpenAlexError(f"OpenAlex request failed with status {status} after retries")
                retry_after = (response.headers or {}).get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else min(30.0, 2.0**attempt)
                self.sleep(delay)
                continue
            if status < 200 or status >= 300:
                raise OpenAlexError(f"OpenAlex request failed with status {status}")
            try:
                payload = response.json()
            except (TypeError, ValueError) as exc:
                raise OpenAlexError("OpenAlex returned malformed JSON") from exc
            if not isinstance(payload, dict):
                raise OpenAlexError("OpenAlex returned an unexpected response shape")
            if self.cache:
                self.cache.put(fingerprint, payload, status)
            return payload
        raise OpenAlexError("OpenAlex request failed")

    def iter_works(self, filters: dict, *, limit: int, per_page: int = 100) -> Iterator[dict]:
        cursor: str | None = "*"
        yielded = 0
        while cursor and yielded < limit:
            payload = self.request(
                "/works",
                {
                    **filters,
                    "cursor": cursor,
                    "per_page": min(100, per_page, limit - yielded),
                    "select": WORK_SELECT,
                },
            )
            results = payload.get("results")
            if not isinstance(results, list):
                raise OpenAlexError("OpenAlex works response is missing results")
            for item in results:
                if not isinstance(item, dict):
                    continue
                yield item
                yielded += 1
                if yielded >= limit:
                    return
            if not results:
                return
            meta = payload.get("meta") or {}
            cursor = meta.get("next_cursor")

    def resolve_seed(self, raw_input: str) -> ResolvedSeed:
        value = raw_input.strip()
        openalex_id = self.extract_openalex_id(value)
        if openalex_id:
            payload = self.request(f"/works/{openalex_id}", {"select": WORK_SELECT})
            return ResolvedSeed(raw_input=value, match_type="openalex_id", work=payload)
        doi = self.extract_doi(value)
        if doi:
            works = list(self.iter_works({"filter": f"doi:{doi}"}, limit=1, per_page=1))
            return ResolvedSeed(raw_input=value, match_type="doi", work=works[0] if works else None)
        works = list(self.iter_works({"search": value, "sort": "relevance_score:desc"}, limit=1, per_page=1))
        return ResolvedSeed(raw_input=value, match_type="title", work=works[0] if works else None)

    def fetch_works_by_ids(self, openalex_ids: list[str]) -> Iterator[dict]:
        normalized = [self.extract_openalex_id(value) for value in openalex_ids]
        ids = list(dict.fromkeys(item for item in normalized if item))
        for start in range(0, len(ids), 50):
            batch = ids[start : start + 50]
            yield from self.iter_works({"filter": f"openalex_id:{'|'.join(batch)}"}, limit=len(batch))

    def iter_citing_works(self, openalex_id: str, *, limit: int) -> Iterator[dict]:
        normalized = self.extract_openalex_id(openalex_id)
        if not normalized:
            return
        yield from self.iter_works({"filter": f"cites:{normalized}", "sort": "cited_by_count:desc"}, limit=limit)

    @staticmethod
    def extract_openalex_id(value: str) -> str | None:
        match = re.search(r"(?:openalex\.org/)?(W\d+)$", value.strip(), flags=re.IGNORECASE)
        return match.group(1).upper() if match else None

    @staticmethod
    def extract_doi(value: str) -> str | None:
        cleaned = re.sub(r"^(?:https?://doi\.org/|doi:)", "", value.strip(), flags=re.IGNORECASE)
        match = re.search(r"10\.\d{4,9}/\S+", cleaned, flags=re.IGNORECASE)
        return match.group(0).rstrip(".,;").lower() if match else None

    @staticmethod
    def _fingerprint(path: str, params: dict) -> str:
        canonical = json.dumps({"path": path, "params": params}, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
