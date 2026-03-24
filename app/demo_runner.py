from __future__ import annotations

import argparse
import json

from ..config import DemoConfig, OUTPUTS_ROOT, relative_to_demo
from ..core.chart_plugin import generate_chart_markdown
from ..data.review_payloads import build_review_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the review-stage chart plugin MCP demo on one CSV chart case.")
    parser.add_argument("--file-name", default=DemoConfig().default_file_name)
    parser.add_argument("--row-id", type=int, default=DemoConfig().default_row_id)
    args = parser.parse_args()

    payload = build_review_payload(file_name=args.file_name, row_id=args.row_id)
    result = generate_chart_markdown(payload)

    summary_path = OUTPUTS_ROOT / f"{payload['request_id']}__demo_summary.json"
    summary = {
        "review_payload": payload,
        "result": result,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Demo finished.")
    print("Markdown:", result["markdown"])
    print("Chart tag:", result["chart_tag"])
    print("Summary:", relative_to_demo(summary_path))
    print("Chart asset:", result["relative_path"])


if __name__ == "__main__":
    main()
