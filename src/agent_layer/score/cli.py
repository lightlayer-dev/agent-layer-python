"""CLI entry point for agent-layer-score."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .scanner import scan
from .reporter import format_report, format_json, badge_url


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agent-layer-score",
        description="Score any API or website for agent-readiness — like Lighthouse for AI agents",
    )
    parser.add_argument("url", help="URL to score")
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output results as JSON"
    )
    parser.add_argument("--badge", action="store_true", help="Output a shields.io badge URL")
    parser.add_argument(
        "--timeout", type=int, default=10000, help="Request timeout in ms (default: 10000)"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=20,
        help="Minimum score (0-100). Exit 1 if below threshold.",
    )
    parser.add_argument("--user-agent", type=str, default=None, help="Custom User-Agent string")

    args = parser.parse_args()

    try:
        report = asyncio.run(
            scan(
                args.url,
                timeout_s=args.timeout / 1000,
                user_agent=args.user_agent,
            )
        )

        if args.json_output:
            print(format_json(report))
        elif args.badge:
            url = badge_url(report.score)
            print(url)
            print(f"\nMarkdown: ![Agent-Ready]({url})")
        else:
            print(format_report(report))

        if report.score < args.threshold:
            print(f"\nScore {report.score} is below threshold {args.threshold}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Scan failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
