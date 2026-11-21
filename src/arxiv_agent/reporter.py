from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .llm import LLMClient

# 报告生成模块：将数据库中的结构化结果整理为中文 Markdown 文献简报。


def _md_list(values: Any) -> str:
    """把可选的单值或列表格式化为 Markdown 列表。"""
    if not values:
        return "- 论文未明确说明\n"
    if isinstance(values, str):
        values = [values]
    return "".join(f"- {v}\n" for v in values)


def _paper_section(p: dict[str, Any], llm: LLMClient | None = None) -> str:
    """生成单篇论文报告；可用模型将初筛和分析字段翻译为中文。"""
    screening = p.get("screening") or {}
    analysis = p.get("full_analysis") or {}
    score = p.get("score") if p.get("score") is not None else screening.get("relevance_score", 0)
    labels = screening.get("topic_labels", [])
    def zh(value: Any) -> str:
        text = str(value or "")
        if not text or llm is None:
            return text
        try:
            return llm.chat(
                "Translate the supplied academic text into natural Simplified Chinese. Preserve names, technical terms, numbers, and citations. Return only the translation.",
                text,
                max_tokens=1600,
            ).strip()
        except Exception:
            return text

    out = [
        f"### {p['title']}\n\n",
        f"- **相关度：** {score}/10（{p.get('relevance_level', '未评估')}）\n",
        f"- **主题：** {', '.join(labels) if labels else ', '.join(p.get('topic_groups', []))}\n",
        f"- **作者：** {', '.join(p.get('authors', [])[:8])}{' 等' if len(p.get('authors', [])) > 8 else ''}\n",
        f"- **首次提交：** {p.get('published', '')[:10]}\n",
        f"- **分类：** {', '.join(p.get('categories', []))}\n",
        f"- **链接：** [{p['arxiv_id']}]({p.get('abs_url', '')})\n\n",
        f"**摘要中的研究问题：** {zh(screening.get('core_problem', '未提取'))}\n\n",
        f"**初筛判断：** {zh(screening.get('relevance_reason', '未提取'))}\n\n",
    ]
    if analysis:
        def zh_list(values: Any) -> str:
            if not values:
                return "- 论文未明确说明\n"
            if isinstance(values, str):
                values = [values]
            return "".join(f"- {zh(value)}\n" for value in values)

        reproducibility = analysis.get("reproducibility", {})
        if isinstance(reproducibility, dict):
            reproducibility = {key: zh(value) for key, value in reproducibility.items()}
        out.extend([
            "**一句话概述：** " + zh(analysis.get("one_sentence_summary", "未提取")) + "\n\n",
            "**任务定义与假设：**\n" + zh_list(analysis.get("assumptions_and_inputs")),
            "**核心方法：**\n" + zh(analysis.get("core_method", "论文未明确说明")) + "\n\n",
            "**方法创新：**\n" + zh_list(analysis.get("key_innovations")),
            "**几何/优化细节：**\n" + zh_list(analysis.get("geometry_or_optimization")),
            "**实验数据集：**\n" + zh_list(analysis.get("datasets")),
            "**评价指标：**\n" + zh_list(analysis.get("metrics")),
            "**定量结果：**\n" + zh_list(analysis.get("quantitative_results")),
            "**消融实验：**\n" + zh_list(analysis.get("ablations")),
            "**局限性：**\n" + zh_list(analysis.get("limitations")),
            "**可复现性：**\n" + json.dumps(reproducibility, ensure_ascii=False) + "\n\n",
            "**对当前研究的潜在帮助：**\n" + zh(analysis.get("connection_to_researcher", "未提取")) + "\n\n",
            "**可进一步探索的问题：**\n" + zh_list(analysis.get("follow_up_ideas")),
            "**证据定位：**\n" + zh_list(analysis.get("evidence_notes")),
        ])
    else:
        out.append("**摘要：**\n\n" + zh(p.get("abstract", "")) + "\n\n")
    out.append("\n---\n\n")
    return "".join(out)


def generate_report(papers: list[dict[str, Any]], output_dir: Path, title: str, window_label: str, llm: LLMClient | None = None) -> Path:
    """按相关度分组写出日报、周报和 latest 快捷报告。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    high = [p for p in papers if (p.get("score") or 0) >= 7]
    medium = [p for p in papers if 4.5 <= (p.get("score") or 0) < 7]
    low = [p for p in papers if (p.get("score") or 0) < 4.5]
    lines = [
        f"# {title}\n\n",
        f"**统计区间：** {window_label}  \n",
        f"**生成时间：** {datetime.now().astimezone().isoformat(timespec='minutes')}  \n",
        f"**发现论文：** {len(papers)} 篇；**高相关：** {len(high)} 篇；**中相关：** {len(medium)} 篇；**低相关：** {len(low)} 篇。\n\n",
        "> 说明：相关度分数是 LLM 根据标题和摘要给出的初筛判断，不代表论文质量或同行评审结论。全文分析以可提取到的 PDF 文本为依据；未找到的信息会标注为未明确说明。\n\n",
        "## 一、本期重点论文\n\n",
    ]
    if high:
        for p in high:
            lines.append(_paper_section(p, llm))
    else:
        lines.append("本期没有达到高相关阈值的论文。\n\n")
    if medium:
        lines.append("## 二、值得留意的邻近研究\n\n")
        for p in medium:
            lines.append(_paper_section(p, llm))
    lines.append("## 三、低相关论文\n\n")
    lines.append(f"本期有 {len(low)} 篇论文低于中相关阈值，默认不展开，以控制阅读成本。\n")

    now = datetime.now().astimezone()
    content = "".join(lines)
    daily_path = output_dir / "daily" / f"{now.strftime('%Y-%m-%d')}.md"
    daily_path.parent.mkdir(parents=True, exist_ok=True)
    daily_path.write_text(content, encoding="utf-8")

    iso_year, iso_week, _ = now.isocalendar()
    weekly_path = output_dir / "weekly" / f"{iso_year}-W{iso_week:02d}.md"
    weekly_path.parent.mkdir(parents=True, exist_ok=True)
    weekly_path.write_text(content, encoding="utf-8")

    (output_dir / "latest.md").write_text(content, encoding="utf-8")
    return daily_path
