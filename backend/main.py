"""CLI: python main.py --input ./resumes --output ./output/results.json

A thin wrapper over the same pipeline the API uses (``app.pipeline``).
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.config import load_settings
from app.pipeline import PipelineOptions, build_processor, write_results_atomic


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen and rank resumes (deterministic engine).")
    parser.add_argument("--input", required=True, type=Path, help="folder containing resumes")
    parser.add_argument("--output", required=True, type=Path, help="path of results.json to write")
    parser.add_argument(
        "--no-llm", action="store_true", help="deterministic screening only; skip LLM analysis"
    )
    parser.add_argument(
        "--no-github", action="store_true", help="skip GitHub enrichment (GitHub scores 0)"
    )
    return parser.parse_args(argv)


async def run_cli(args: argparse.Namespace) -> int:
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    options = PipelineOptions(use_llm=not args.no_llm, use_github=not args.no_github)
    processor = build_processor(settings, options)

    try:
        results = await processor.process_directory_async(args.input)
    except NotADirectoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    write_results_atomic(results, args.output)

    s = results.batch_summary
    print(
        f"Screened {s.total_resumes} resumes: {s.eligible} eligible, {s.rejected} rejected, "
        f"{s.failed} failed, {s.duplicates} duplicates -> {args.output}"
    )
    print(f"LLM analysis: {s.llm_status_counts or 'none'}")
    print(f"GitHub enrichment: {s.github_status_counts or 'none'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # The single top-level event loop of the CLI; nothing below it calls asyncio.run().
    return asyncio.run(run_cli(parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
