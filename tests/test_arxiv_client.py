from datetime import datetime, timedelta, timezone

import pytest
import requests

from arxiv_agent.arxiv_client import ArxivClient, _parse_arxiv_id


def test_parse_arxiv_ids_and_versions():
    assert _parse_arxiv_id("https://arxiv.org/abs/2301.12345v2") == ("2301.12345", "v2")
    assert _parse_arxiv_id("https://arxiv.org/abs/hep-th/9901001v3") == ("hep-th/9901001", "v3")
    assert _parse_arxiv_id("http://arxiv.org/abs/2301.1234") == ("2301.1234", "v1")
    with pytest.raises(ValueError):
        _parse_arxiv_id("https://arxiv.org/abs/2301.12345junk")


def test_search_parses_atom_and_accepts_naive_timestamp(monkeypatch):
    published = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><id>https://arxiv.org/abs/2301.12345v2</id>
      <published>{published}</published><updated>{published}</updated>
      <title>  A   paper </title><summary> An\n abstract </summary>
      <author><name>A. Author</name></author><category term="cs.CV"/>
      <link rel="alternate" href="https://arxiv.org/abs/2301.12345v2"/>
      </entry><entry><id>https://arxiv.org/abs/bad</id></entry></feed>'''

    class Response:
        text = xml

        def raise_for_status(self):
            pass

    client = ArxivClient({"api_url": "https://example.test", "lookback_days": 2, "request_interval_seconds": 0})
    monkeypatch.setattr(client.session, "get", lambda *a, **k: Response())
    papers = client.search_topic({"name": "vision", "categories": ["cs.CV"], "keywords": ["localization"]})
    assert len(papers) == 1
    assert papers[0]["version"] == "v2"
    assert papers[0]["title"] == "A paper"
    assert papers[0]["abstract"] == "An abstract"


def test_search_retries_transient_request_failure(monkeypatch):
    class Response:
        text = '<feed xmlns="http://www.w3.org/2005/Atom" />'

        def raise_for_status(self):
            pass

    client = ArxivClient({"api_url": "https://example.test", "request_interval_seconds": 0})
    attempts = 0

    def get(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.ConnectionError("temporary")
        return Response()

    monkeypatch.setattr(client.session, "get", get)
    monkeypatch.setattr("arxiv_agent.arxiv_client.time.sleep", lambda _: None)
    assert client.search_topic({"name": "x", "keywords": ["test"]}) == []
    assert attempts == 2
