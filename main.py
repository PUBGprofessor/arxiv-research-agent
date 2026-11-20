from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from arxiv_agent.config import load_config
from arxiv_agent.llm import LLMClient
from arxiv_agent.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor arXiv papers for 3D vision and camera localization.")
    parser.add_argument("command", choices=["run", "test-llm"], nargs="?", default="run")
    parser.add_argument("--force", action="store_true", help="Reprocess fetched records; use cautiously to avoid repeated API costs.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    cfg = load_config()

    if args.command == "test-llm":
        llm = LLMClient(cfg["_env"])
        print(llm.chat("Return only the word OK.", "Connection test.", max_tokens=20))
        return 0

    report = run_pipeline(cfg, force=args.force)
    print(f"\n完成。报告位置：{report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
