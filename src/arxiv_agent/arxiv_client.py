from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import requests

ATOM = "http://www.w3.org/2005/Atom"
ARXIV = "http://arxiv.org/schemas/atom"


def _text(parent: ET.Element, tag: str) -> str:
    node = parent.find(f"{{{ATOM}}}{tag}")
    return (node.text or "").strip() if node is not None else ""


def _parse_arxiv_id(entry_id: str) -> tuple[str, str]:
    parsed = urlparse(entry_id)
    raw = parsed.path.rstrip("/").split("/abs/")[-1]
    match = re.fullmatch(r"(?P<id>\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7})(?P<version>v\d+)?", raw)
    if not match:
        raise ValueError(f"Could not parse arXiv ID from {entry_id}")
    return match.group("id"), match.group("version") or "v1"


class ArxivClient:
    def __init__(self, cfg: dict[str, Any]):
        self.api_url = cfg["api_url"]
        self.interval = float(cfg.get("request_interval_seconds", 3.2))
        self.max_results = int(cfg.get("max_results_per_topic", 100))
        self.lookback_days = int(cfg.get("lookback_days", 14))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": cfg.get("user_agent", "arxiv-research-agent/0.1")})
        self._last_request = 0.0

    @staticmethod
    def _escape_phrase(value: str) -> str:
        return 'all:"' + value.replace('"', '') + '"'

    def build_query(self, topic: dict[str, Any]) -> str:
        categories = topic.get("categories") or []
        keywords = topic.get("keywords") or []
        cat_expr = " OR ".join(f"cat:{c}" for c in categories)
        keyword_expr = " OR ".join(self._escape_phrase(k) for k in keywords)
        if cat_expr and keyword_expr:
            return f"({cat_expr}) AND ({keyword_expr})"
        return cat_expr or keyword_expr

    def search_topic(self, topic: dict[str, Any]) -> list[dict[str, Any]]:
        query = self.build_query(topic)
        if not query:
            return []
        wait = self.interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        params = {
            "search_query": query,
            "start": 0,
            "max_results": self.max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        response = None
        for attempt, delay in enumerate((5, 15, 30, None)):
            try:
                response = self.session.get(self.api_url, params=params, timeout=60)
                self._last_request = time.monotonic()
                response.raise_for_status()
                break
            except requests.Timeout:
                if delay is None:
                    raise
                time.sleep(delay)
            except requests.ConnectionError:
                if delay is None:
                    raise
                time.sleep(delay)
            except requests.HTTPError:
                if delay is None or response is None or response.status_code < 500 and response.status_code != 429:
                    raise
                time.sleep(delay)
        assert response is not None
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise ValueError("Invalid Atom XML returned by arXiv") from exc
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        papers: list[dict[str, Any]] = []
        for entry in root.findall(f"{{{ATOM}}}entry"):
            entry_id = _text(entry, "id")
            try:
                arxiv_id, version = _parse_arxiv_id(entry_id)
            except ValueError:
                continue
            published = _text(entry, "published")
            updated = _text(entry, "updated")
            try:
                published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if published_dt.tzinfo is None:
                    published_dt = published_dt.replace(tzinfo=timezone.utc)
                else:
                    published_dt = published_dt.astimezone(timezone.utc)
            except ValueError:
                continue
            # arXiv's published date is the first submission date. Use it to avoid
            # treating an old paper's new version as a newly submitted paper.
            if published_dt < cutoff:
                continue
            links = entry.findall(f"{{{ATOM}}}link")
            abs_url = f"https://arxiv.org/abs/{arxiv_id}"
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
            for link in links:
                href = link.attrib.get("href", "")
                rel = link.attrib.get("rel", "")
                typ = link.attrib.get("type", "")
                if rel == "alternate" and href:
                    abs_url = href
                if typ == "application/pdf" and href:
                    pdf_url = href
            authors = [
                (a.find(f"{{{ATOM}}}name").text or "").strip()
                for a in entry.findall(f"{{{ATOM}}}author")
                if a.find(f"{{{ATOM}}}name") is not None
            ]
            categories = [
                c.attrib.get("term", "")
                for c in entry.findall(f"{{{ATOM}}}category")
                if c.attrib.get("term")
            ]
            title = re.sub(r"\s+", " ", _text(entry, "title"))
            abstract = re.sub(r"\s+", " ", _text(entry, "summary"))
            papers.append({
                "arxiv_id": arxiv_id,
                "version": version,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "categories": categories,
                "topic_groups": [topic["name"]],
                "published": published,
                "updated": updated,
                "abs_url": abs_url,
                "pdf_url": pdf_url,
            })
        return papers
