from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PaperDB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS papers (
                arxiv_id TEXT PRIMARY KEY,
                version TEXT,
                title TEXT NOT NULL,
                abstract TEXT NOT NULL,
                authors_json TEXT NOT NULL,
                categories_json TEXT NOT NULL,
                topic_groups_json TEXT NOT NULL,
                published TEXT,
                updated TEXT,
                abs_url TEXT NOT NULL,
                pdf_url TEXT NOT NULL,
                score REAL,
                relevance_level TEXT,
                screening_json TEXT,
                full_analysis_json TEXT,
                pdf_path TEXT,
                status TEXT NOT NULL DEFAULT 'discovered',
                discovered_at TEXT NOT NULL,
                analyzed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_papers_discovered ON papers(discovered_at);
            CREATE INDEX IF NOT EXISTS idx_papers_published ON papers(published);
            CREATE INDEX IF NOT EXISTS idx_papers_score ON papers(score);
            """
        )
        self.conn.commit()

    def exists(self, arxiv_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM papers WHERE arxiv_id=?", (arxiv_id,)).fetchone()
        return row is not None

    def insert_paper(self, p: dict[str, Any]) -> bool:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT topic_groups_json, version FROM papers WHERE arxiv_id=?", (p["arxiv_id"],)
            ).fetchone()
            if row:
                existing = json.loads(row["topic_groups_json"] or "[]")
                merged = sorted(set(existing) | set(p.get("topic_groups", [])))
                new_version = p.get("version", "")
                changed_version = bool(new_version and new_version != row["version"])
                self.conn.execute(
                    """UPDATE papers SET topic_groups_json=?,
                       version=CASE WHEN ? THEN ? ELSE version END,
                       title=CASE WHEN ? THEN ? ELSE title END,
                       abstract=CASE WHEN ? THEN ? ELSE abstract END,
                       authors_json=CASE WHEN ? THEN ? ELSE authors_json END,
                       categories_json=CASE WHEN ? THEN ? ELSE categories_json END,
                       updated=CASE WHEN ? THEN ? ELSE updated END,
                       abs_url=CASE WHEN ? THEN ? ELSE abs_url END,
                       pdf_url=CASE WHEN ? THEN ? ELSE pdf_url END,
                       score=CASE WHEN ? THEN NULL ELSE score END,
                       relevance_level=CASE WHEN ? THEN NULL ELSE relevance_level END,
                       screening_json=CASE WHEN ? THEN NULL ELSE screening_json END,
                       full_analysis_json=CASE WHEN ? THEN NULL ELSE full_analysis_json END,
                       status=CASE WHEN ? THEN 'discovered' ELSE status END,
                       analyzed_at=CASE WHEN ? THEN NULL ELSE analyzed_at END
                       WHERE arxiv_id=?""",
                    (json.dumps(merged, ensure_ascii=False), changed_version, new_version,
                     changed_version, p["title"], changed_version, p["abstract"],
                     changed_version, json.dumps(p.get("authors", []), ensure_ascii=False),
                     changed_version, json.dumps(p.get("categories", []), ensure_ascii=False),
                     changed_version, p.get("updated", ""), changed_version, p["abs_url"],
                     changed_version, p["pdf_url"], changed_version, changed_version,
                     changed_version, changed_version, changed_version, changed_version, p["arxiv_id"]),
                )
                self.conn.commit()
                return False

            self.conn.execute(
                """INSERT INTO papers (
                arxiv_id, version, title, abstract, authors_json, categories_json,
                topic_groups_json, published, updated, abs_url, pdf_url,
                status, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'discovered', ?)""",
            (
                p["arxiv_id"], p.get("version", ""), p["title"], p["abstract"],
                json.dumps(p.get("authors", []), ensure_ascii=False),
                json.dumps(p.get("categories", []), ensure_ascii=False),
                json.dumps(p.get("topic_groups", []), ensure_ascii=False),
                p.get("published", ""), p.get("updated", ""), p["abs_url"],
                p["pdf_url"], utc_now(),
            ),
            )
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    def update_screening(self, arxiv_id: str, screening: dict[str, Any]) -> None:
        score = float(screening.get("relevance_score", 0) or 0)
        level = str(screening.get("relevance_level", "low"))
        self.conn.execute(
            "UPDATE papers SET score=?, relevance_level=?, screening_json=?, status='screened', analyzed_at=? WHERE arxiv_id=?",
            (score, level, json.dumps(screening, ensure_ascii=False), utc_now(), arxiv_id),
        )
        self.conn.commit()

    def update_full_analysis(self, arxiv_id: str, analysis: dict[str, Any], pdf_path: str) -> None:
        self.conn.execute(
            "UPDATE papers SET full_analysis_json=?, pdf_path=?, status='analyzed', analyzed_at=? WHERE arxiv_id=?",
            (json.dumps(analysis, ensure_ascii=False), pdf_path, utc_now(), arxiv_id),
        )
        self.conn.commit()

    def update_status(self, arxiv_id: str, status: str) -> None:
        self.conn.execute("UPDATE papers SET status=? WHERE arxiv_id=?", (status, arxiv_id))
        self.conn.commit()

    def reset_for_reanalysis(self, arxiv_id: str) -> None:
        self.conn.execute(
            "UPDATE papers SET score=NULL, relevance_level=NULL, screening_json=NULL, full_analysis_json=NULL, status='discovered', analyzed_at=NULL WHERE arxiv_id=?",
            (arxiv_id,),
        )
        self.conn.commit()

    def list_pending_screening(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM papers WHERE status='discovered' ORDER BY published DESC"
        ).fetchall()
        return [self._decode(r) for r in rows]

    def list_pending_full_analysis(self, min_score: float) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM papers WHERE status='screened' AND score>=? AND full_analysis_json IS NULL ORDER BY score DESC, published DESC",
            (float(min_score),),
        ).fetchall()
        return [self._decode(r) for r in rows]

    def get(self, arxiv_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM papers WHERE arxiv_id=?", (arxiv_id,)).fetchone()
        return self._decode(row) if row else None

    def list_discovered_since(self, iso_timestamp: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM papers WHERE discovered_at>=? ORDER BY score DESC, published DESC",
            (iso_timestamp,),
        ).fetchall()
        return [self._decode(r) for r in rows]

    def list_recent_days(self, days: int) -> list[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat(timespec="seconds")
        rows = self.conn.execute(
            "SELECT * FROM papers WHERE discovered_at >= ? ORDER BY score DESC, published DESC",
            (cutoff,),
        ).fetchall()
        return [self._decode(r) for r in rows]

    def close(self) -> None:
        self.conn.close()

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for src, dst in [
            ("authors_json", "authors"),
            ("categories_json", "categories"),
            ("topic_groups_json", "topic_groups"),
            ("screening_json", "screening"),
            ("full_analysis_json", "full_analysis"),
        ]:
            raw = d.pop(src, None)
            try:
                d[dst] = json.loads(raw) if raw else ({} if dst in {"screening", "full_analysis"} else [])
            except json.JSONDecodeError:
                d[dst] = {} if dst in {"screening", "full_analysis"} else []
        return d
