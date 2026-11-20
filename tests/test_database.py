from arxiv_agent.database import PaperDB


def paper(version="v1", title="Paper", topics=None):
    return {
        "arxiv_id": "2301.12345", "version": version, "title": title, "abstract": "Abstract",
        "authors": ["Author"], "categories": ["cs.CV"], "topic_groups": topics or ["vision"],
        "published": "2026-11-20T00:00:00Z", "updated": "2026-11-20T00:00:00Z",
        "abs_url": "https://arxiv.org/abs/2301.12345", "pdf_url": "https://arxiv.org/pdf/2301.12345",
    }


def test_duplicate_merges_topic_without_duplicate_or_state_loss(tmp_path):
    db = PaperDB(tmp_path / "papers.db")
    try:
        assert db.insert_paper(paper())
        db.update_screening("2301.12345", {"relevance_score": 8, "relevance_level": "high"})
        assert not db.insert_paper(paper(topics=["geometry"]))
        row = db.get("2301.12345")
        assert row["topic_groups"] == ["geometry", "vision"]
        assert row["status"] == "screened"
        assert row["score"] == 8
        assert db.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
    finally:
        db.close()


def test_new_version_refreshes_metadata_and_resets_screening(tmp_path):
    db = PaperDB(tmp_path / "papers.db")
    try:
        db.insert_paper(paper())
        db.update_screening("2301.12345", {"relevance_score": 8, "relevance_level": "high"})
        db.insert_paper(paper(version="v2", title="Updated title"))
        row = db.get("2301.12345")
        assert row["version"] == "v2"
        assert row["title"] == "Updated title"
        assert row["status"] == "discovered"
        assert row["score"] is None
        assert row["screening"] == {}
    finally:
        db.close()
