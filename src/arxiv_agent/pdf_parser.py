from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# PDF 处理只负责下载和提取文本；论文结论分析由 analyzer 模块完成。

import pymupdf
import requests


def download_pdf(url: str, destination: Path, timeout: int = 90) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 10_000:
        return destination
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "arxiv-research-agent/0.1"})
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"PDF endpoint did not return a PDF (content-type={content_type})")
    destination.write_bytes(response.content)
    return destination


def extract_research_text(pdf_path: Path, max_chars: int = 50000, max_pages: int = 40) -> str:
    """Extract text with page markers; prioritize intro/method/experiment/conclusion pages."""
    with pymupdf.open(pdf_path) as doc:
        page_count = min(len(doc), max_pages)
        pages: list[tuple[int, str]] = []
        for index in range(page_count):
            text = doc[index].get_text("text", sort=True).strip()
            if text:
                pages.append((index + 1, text))

    if not pages:
        raise RuntimeError("No extractable text found in PDF; it may be scanned or image-only.")

    # Keep the opening pages, pages mentioning important sections, their neighbors,
    # and the ending pages. This is a compact first-version strategy, not a substitute
    # for layout-aware parsing of every paper.
    selected: set[int] = set()
    for page_num, _ in pages[:3]:
        selected.add(page_num)
    for i, (_, text) in enumerate(pages):
        lower = text.lower()
        if any(k in lower for k in ["method", "approach", "experiments", "experimental setup", "ablation", "conclusion", "limitations"]):
            selected.add(pages[i][0])
            if i > 0:
                selected.add(pages[i - 1][0])
            if i + 1 < len(pages):
                selected.add(pages[i + 1][0])
    for page_num, _ in pages[-2:]:
        selected.add(page_num)

    chunks = []
    used = 0
    for page_num, text in pages:
        if page_num not in selected:
            continue
        chunk = f"\n\n===== PAGE {page_num} =====\n{text}"
        if used + len(chunk) > max_chars:
            remaining = max_chars - used
            if remaining > 500:
                chunks.append(chunk[:remaining])
            break
        chunks.append(chunk)
        used += len(chunk)
    return "\n".join(chunks)
