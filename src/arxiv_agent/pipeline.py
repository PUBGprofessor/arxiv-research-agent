from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .analyzer import analyze_paper
from .arxiv_client import ArxivClient
from .config import resolve_path
from .database import PaperDB
from .llm import LLMClient
from .paper_filter import screen_paper
from .pdf_parser import download_pdf, extract_research_text
from .reporter import generate_report


log = logging.getLogger("arxiv_agent")


def run_pipeline(cfg: dict[str, Any], force: bool = False) -> Path:
    """执行检索到报告的完整流程，并返回本次日报路径。"""
    arxiv_cfg = cfg["arxiv"]
    db = PaperDB(resolve_path(cfg, cfg["storage"]["database_path"]))
    # 先汇总所有主题的检索结果，再统一写入数据库，避免跨主题重复筛选。
    client = ArxivClient(arxiv_cfg)
    topics = cfg.get("topic_groups", [])
    discovered: dict[str, dict[str, Any]] = {}

    try:
        log.info("Fetching papers from %d topic groups", len(topics))
        # 单个主题失败时记录异常并继续其余主题；失败主题会在后续运行再次检索。
        for topic in topics:
            log.info("Searching topic: %s", topic["name"])
            try:
                results = client.search_topic(topic)
            except Exception:
                log.exception("arXiv query failed for topic %s", topic["name"])
                continue
            for paper in results:
                if paper["arxiv_id"] in discovered:
                    discovered[paper["arxiv_id"]]["topic_groups"] = sorted(
                        set(discovered[paper["arxiv_id"]]["topic_groups"]) | set(paper["topic_groups"])
                    )
                else:
                    discovered[paper["arxiv_id"]] = paper

        for paper in discovered.values():
            db.insert_paper(paper)
            if force:
                db.reset_for_reanalysis(paper["arxiv_id"])

        log.info("Fetched %d unique papers", len(discovered))
        disable_pdf = cfg["_env"]["disable_pdf_analysis"]
        profile = cfg.get("research_profile", "")
        screening_cfg = cfg.get("screening", {})
        high_threshold = float(screening_cfg.get("high_relevance_threshold", 7.0))
        pdf_dir = resolve_path(cfg, cfg["storage"]["pdf_dir"])

        # 数据库中仍处于 discovered 的记录会在本次或后续运行继续初筛。
        pending_screening = db.list_pending_screening()
        max_screening = int(screening_cfg.get("max_screening_per_run", 60))
        pending_screening = pending_screening[:max_screening]
        pending_full = db.list_pending_full_analysis(high_threshold)
        if pending_screening or (pending_full and not disable_pdf):
            llm = LLMClient(cfg["_env"])
        else:
            llm = None

        # 每篇论文独立处理；失败时不改变 discovered 状态，以便下次运行重试。
        for idx, paper in enumerate(pending_screening, 1):
            log.info("[%d/%d] Screening %s", idx, len(pending_screening), paper["arxiv_id"])
            try:
                screening = screen_paper(llm, profile, paper, paper.get("topic_groups", []))
                db.update_screening(paper["arxiv_id"], screening)
            except Exception as exc:
                log.exception("Screening failed for %s: %s", paper["arxiv_id"], exc)

        if not disable_pdf and screening_cfg.get("analyze_full_text_for_high_relevance", True):
            pending_full = db.list_pending_full_analysis(high_threshold)
            max_fulltext = int(screening_cfg.get("max_fulltext_per_run", 5))
            pending_full = pending_full[:max_fulltext]
            for idx, paper in enumerate(pending_full, 1):
                screening = paper.get("screening") or {}
                if not screening.get("read_full_paper", True):
                    db.update_status(paper["arxiv_id"], "screened_only")
                    continue
                log.info("[%d/%d] Full-text analysis %s", idx, len(pending_full), paper["arxiv_id"])
                try:
                    pdf_path = pdf_dir / f"{paper['arxiv_id'].replace('/', '_')}.pdf"
                    downloaded = download_pdf(
                        paper["pdf_url"],
                        downloaded_path(pdf_path),
                        timeout=int(screening_cfg.get("download_timeout_seconds", 90)),
                    )
                    extracted = extract_research_text(
                        downloaded,
                        max_chars=int(screening_cfg.get("max_fulltext_chars", 50000)),
                        max_pages=int(screening_cfg.get("max_pdf_pages", 40)),
                    )
                    analysis = analyze_paper(llm, paper, screening, extracted)
                    db.update_full_analysis(paper["arxiv_id"], analysis, str(downloaded))
                except Exception as exc:
                    # 保留 screened 状态，后续运行仍可重试该论文的全文分析。
                    log.exception("Full-text analysis failed for %s: %s", paper["arxiv_id"], exc)

        window_days = int(cfg.get("report", {}).get("weekly_lookback_days", 7))
        report_papers = db.list_recent_days(window_days)
        report_dir = resolve_path(cfg, cfg["storage"]["report_dir"])
        report_llm = llm
        if report_llm is None and report_papers and cfg["_env"].get("llm_api_key") and cfg["_env"].get("llm_model"):
            try:
                report_llm = LLMClient(cfg["_env"])
            except RuntimeError:
                log.warning("LLM is not available; report will keep source-language text")
        since = (datetime.now(timezone.utc) - timedelta(days=window_days)).date().isoformat()
        until = datetime.now(timezone.utc).date().isoformat()
        report_path = generate_report(
            report_papers,
            report_dir,
            cfg.get("report", {}).get("title", "arXiv Research Digest"),
            f"{since} 至 {until}",
            llm=report_llm,
        )
        log.info("Report written to %s", report_path)
        return report_path
    finally:
        db.close()


def downloaded_path(path: Path) -> Path:
    return path
