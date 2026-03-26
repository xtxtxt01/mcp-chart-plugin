from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.chart_plugin import generate_chart_markdown
from ..schemas.function_schemas import schema_file_text


mcp = FastMCP(
    name="chart-plugin-mcp",
    instructions=(
        "Review-stage chart plugin. "
        "The server accepts chart tasks from review, uses aggSearch to retrieve chart materials, "
        "plans retrieval intent with one function-call schema, "
        "runs at most one supplementary retrieval round, "
        "and uses one shared LLM configuration for both retrieval planning and chart generation, "
        "feeding existing insights plus selected live docs into the second chart-generation attempt, "
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

@mcp.resource("resource://schemas/plan_chart_retrieval")
def plan_chart_retrieval_schema_resource() -> str:
    """Expose the query-planning function-call schema text for tools configuration."""
    return schema_file_text("plan_chart_retrieval.tools.json")


def main() -> None:
    mcp.run(transport="stdio")


__all__ = ["mcp", "server", "main"]


if __name__ == "__main__":
    main()
