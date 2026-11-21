from __future__ import annotations

import json
from typing import Any

from .llm import LLMClient

# 初筛仅使用标题与摘要，避免在筛选阶段就下载和处理整篇论文。


SCREEN_SYSTEM = """You are a rigorous academic literature triage assistant specializing in 3D computer vision and camera localization.
Evaluate only what is supported by the supplied title and abstract. Do not infer unreported experiments, results, code availability, or technical details.
The researcher's profile is provided by the user message. Prioritize map-based visual localization, camera pose estimation, relative pose, structureless localization, robust pose aggregation, image matching, geometric verification, PnP/RANSAC, SLAM, and 3D scene representations used for localization.
Return exactly one valid JSON object. No Markdown and no text outside JSON.
Schema:
{
  "relevance_score": 0-10,
  "dimension_scores": {"task_alignment": 0-10, "method_overlap": 0-10, "innovation_potential": 0-10, "evaluation_evidence": 0-10},
  "relevance_level": "high|medium|low",
  "topic_labels": ["..."],
  "task_type": ["..."],
  "core_problem": "...",
  "method_keywords": ["..."],
  "potential_contribution": "...",
  "relevance_reason": "...",
  "limitations_or_unknowns": ["..."],
  "read_full_paper": true
}
Score with this weighted rubric. Give each dimension a 0-10 score, then calculate the weighted overall score:
- task_alignment (30%): does the paper solve visual localization, camera pose estimation, relative pose, or a closely related 3D vision problem?
- method_overlap (30%): does it contribute to geometry, matching, robust estimation, pose aggregation, map representation, or related techniques?
- innovation_potential (25%): does the abstract indicate a non-trivial algorithmic or conceptual contribution rather than only an application?
- evaluation_evidence (15%): does the abstract provide credible datasets, metrics, comparisons, or reproducibility clues? Do not assume code exists if not stated.
Overall = 0.30*task_alignment + 0.30*method_overlap + 0.25*innovation_potential + 0.15*evaluation_evidence.
Score bands: 9-10 direct and substantial contribution; 7-8 clearly relevant; 5-6 adjacent technique with plausible transfer; 3-4 weak connection; 0-2 irrelevant. If evidence is insufficient, lower confidence and state unknowns.
"""


def screen_paper(llm: LLMClient, profile: str, paper: dict[str, Any], groups: list[str]) -> dict[str, Any]:
    user_prompt = f"""Research profile:
{profile}

Matched topic groups: {', '.join(groups)}

Paper metadata:
Title: {paper['title']}
Authors: {', '.join(paper.get('authors', []))}
Submitted: {paper.get('published', '')}
Categories: {', '.join(paper.get('categories', []))}
Abstract:
{paper['abstract']}

Assess relevance for this researcher. Be conservative and distinguish camera pose estimation from human/object pose estimation.
"""
    result = LLMClient.parse_json(llm.chat(SCREEN_SYSTEM, user_prompt, max_tokens=1800))
    score = float(result.get("relevance_score", 0) or 0)
    result["relevance_score"] = max(0.0, min(10.0, score))
    if result["relevance_score"] >= 7:
        result["relevance_level"] = "high"
    elif result["relevance_score"] >= 4.5:
        result["relevance_level"] = "medium"
    else:
        result["relevance_level"] = "low"
    return result
