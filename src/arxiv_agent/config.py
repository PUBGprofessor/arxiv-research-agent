from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

# 配置根目录固定为项目目录，避免从其他工作目录启动时找不到配置。


def load_config() -> dict[str, Any]:
    """读取 YAML 与 .env 配置，并将运行期环境选项放入内部字段。"""
    load_dotenv(ROOT / ".env")
    path = ROOT / "config.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg["_root"] = ROOT
    cfg["_env"] = {
        "llm_base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "llm_api_key": os.getenv("LLM_API_KEY", ""),
        "llm_model": os.getenv("LLM_MODEL", ""),
        "llm_timeout": int(os.getenv("LLM_TIMEOUT", "180")),
        "disable_pdf_analysis": os.getenv("DISABLE_PDF_ANALYSIS", "0").strip() == "1",
    }
    return cfg


def resolve_path(cfg: dict[str, Any], value: str) -> Path:
    """将相对存储路径解析到项目根目录，绝对路径保持原样。"""
    path = Path(value)
    return path if path.is_absolute() else cfg["_root"] / path
