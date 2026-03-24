from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.chart_plugin import generate_chart_markdown
from ..data.review_payloads import build_review_payload
from ..schemas.function_schemas import schema_file_text


mcp = FastMCP(
    name="chart-plugin-mcp-demo",
    instructions=(
        "Review-stage chart plugin demo. "
        "The server accepts chart tasks from review, uses aggSearch to retrieve chart materials, "
        "plans retrieval intent with one function-call schema, "
        "extracts structured knowledges with another function-call schema, "
        "and uses the original baseline prompt plus LLM to decide chart XML, "
        "then returns markdown image content."
    ),
)
server = mcp


@mcp.tool(name="generate_chart_markdown", structured_output=True)
def generate_chart_markdown_tool(
    review_payload: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate chart markdown from a review-stage chart task."""
    return generate_chart_markdown(review_payload=review_payload, config_dict=config)


@mcp.tool(name="build_review_payload_demo", structured_output=True)
def build_review_payload_demo(file_name: str, row_id: int) -> dict[str, Any]:
    """Build one demo review payload from a CSV case for local replay."""
    return build_review_payload(file_name=file_name, row_id=row_id)


@mcp.resource("resource://schemas/extract_chart_facts")
def extract_chart_facts_schema_resource() -> str:
    """Expose the function-call schema text for tools configuration."""
    return schema_file_text("extract_chart_facts.tools.json")


@mcp.resource("resource://schemas/plan_chart_retrieval")
def plan_chart_retrieval_schema_resource() -> str:
    """Expose the query-planning function-call schema text for tools configuration."""
    return schema_file_text("plan_chart_retrieval.tools.json")


def main() -> None:
    mcp.run(transport="stdio")


__all__ = ["mcp", "server", "main"]


if __name__ == "__main__":
    main()
