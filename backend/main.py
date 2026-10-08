"""CLI: python main.py --input ./resumes --output ./output/results.json"""

import argparse
import logging
import sys
from pathlib import Path

from app.config import load_settings
from app.llm import SemanticAnalyzer
from app.screening.batch import BatchProcessor


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen and rank resumes (deterministic engine).")
    parser.add_argument("--input", required=True, type=Path, help="folder containing resumes")
    parser.add_argument("--output", required=True, type=Path, help="path of results.json to write")
    parser.add_argument(
        "--no-llm", action="store_true", help="deterministic screening only; skip LLM analysis"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    analyzer = None
    if not args.no_llm:
        analyzer = SemanticAnalyzer.from_settings(settings)
        if analyzer.unavailable_reason:
            logging.getLogger("main").warning(
                "LLM analysis unavailable (%s); continuing with deterministic scoring only",
                analyzer.unavailable_reason,
            )

    try:
        results = BatchProcessor(analyzer=analyzer).process_directory(args.input)
    except NotADirectoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(results.model_dump_json(indent=2), encoding="utf-8")

    s = results.batch_summary
    print(
        f"Screened {s.total_resumes} resumes: {s.eligible} eligible, {s.rejected} rejected, "
        f"{s.failed} failed, {s.duplicates} duplicates -> {args.output}"
    )
    print(f"LLM analysis: {s.llm_status_counts or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
