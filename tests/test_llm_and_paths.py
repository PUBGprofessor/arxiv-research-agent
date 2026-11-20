import pytest
import sys
import types

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_: None))
from arxiv_agent.config import resolve_path
from arxiv_agent.llm import LLMClient
from arxiv_agent.reporter import generate_report


@pytest.mark.parametrize("text", [
    '{"relevance_score": 8}',
    '```json\n{"relevance_score": 8}\n```',
    'Here is the result:\n{"relevance_score": 8}\nDone.',
])
def test_parse_json_accepts_common_wrappers(text):
    assert LLMClient.parse_json(text) == {"relevance_score": 8}


@pytest.mark.parametrize("text", ["not json", "```json\n{oops}\n```", "[1, 2]"])
def test_parse_json_rejects_invalid_or_non_object(text):
    with pytest.raises(ValueError):
        LLMClient.parse_json(text)


def test_resolve_path_is_root_relative_and_preserves_absolute_paths(tmp_path):
    cfg = {"_root": tmp_path}
    assert resolve_path(cfg, "data/papers.db") == tmp_path / "data" / "papers.db"
    absolute = tmp_path / "absolute.db"
    assert resolve_path(cfg, str(absolute)) == absolute


def test_report_translates_paper_text_but_preserves_metadata(tmp_path):
    class Translator:
        def chat(self, _system, text, max_tokens):
            return f"译文:{text}"

    paper = {
        "title": "A Paper Title", "arxiv_id": "2301.12345", "abs_url": "https://arxiv.org/abs/2301.12345",
        "authors": ["A. Author"], "published": "2026-11-20", "categories": ["cs.CV"],
        "topic_groups": ["vision"], "abstract": "English abstract", "score": 8, "relevance_level": "high",
        "screening": {"core_problem": "Problem", "relevance_reason": "Reason"},
    }
    path = generate_report([paper], tmp_path, "Digest", "date", llm=Translator())
    report = path.read_text(encoding="utf-8")
    assert "A Paper Title" in report and "A. Author" in report
    assert "译文:English abstract" in report
    assert "译文:Reason" in report
