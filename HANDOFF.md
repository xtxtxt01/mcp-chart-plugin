# 图表生成 MCP 交付说明

本次交付内容为一个可独立调用的 **图表生成 MCP**，用于在 review / DeepResearch 阶段根据图表任务描述、已有参考资料和补充检索结果生成最终图表，并返回可直接插入报告的 Markdown 图片引用。

## 1. 仓库地址

GitHub 仓库：

- `https://github.com/xtxtxt01/mcp-chart-plugin.git`

## 2. MCP 用途

该 MCP 负责图表生成这一项能力，输入为一条图表任务的 `review_payload`，输出为：

- 图表 Markdown 引用
- 图表相对路径
- 图表类型
- 调试摘要信息

适合在 DeepResearch / review 阶段被主流程按需调用。

## 3. 启动方式

该 MCP 采用 `stdio` 方式启动。

启动命令：

```bash
python -m MCP_demo
```

也可使用：

```bash
python -m MCP_demo.app.server
```

## 4. 正式使用的 Tool

正式接入时只使用以下 tool：

- `generate_chart_markdown`

## 5. 最小输入格式

`generate_chart_markdown` 的输入为：

```json
{
  "review_payload": {
    "request_id": "case-001",
    "chart_title": "图表标题",
    "chart_description": "图表描述",
    "write_requirement": "写作要求",
    "existing_refs": [
      {
        "id": 0,
        "content": "已有参考资料或上游抽取结果"
      }
    ],
    "base_queries": [
      "基础检索 query 1",
      "基础检索 query 2"
    ]
  }
}
```

字段说明：

- `request_id`：本次图表请求唯一标识，必填
- `chart_title`：图表标题，必填
- `chart_description`：图表的具体绘制目标，必填
- `write_requirement`：本章/本节写作要求，可选
- `existing_refs`：上游已有参考资料或已抽取结果，必填
- `base_queries`：基础检索 query，首轮无法成图时用于补充 aggSearch，可选

`existing_refs` 每项至少建议为：

```json
{
  "id": 0,
  "content": "文本内容"
}
```

`base_queries` 为字符串数组，例如：

```json
[
  "2026 海信 RGB Mini LED 分区数 亮度 色域",
  "2026 TCL SQD Mini LED 分区数 亮度 色域"
]
```

## 6. 输出格式

典型输出中的核心字段如下：

```json
{
  "success": true,
  "markdown": "![图表标题](artifacts/charts/case-001/chart_01.png)",
  "relative_path": "artifacts/charts/case-001/chart_01.png",
  "chart_tag": "radar",
  "debug_summary": {
    "used_agg_search": false,
    "attempt_count": 1,
    "final_stage": "existing_insights_only"
  }
}
```

主要字段说明：

- `markdown`：可直接插入报告的 Markdown 图片引用
- `relative_path`：图表相对路径
- `chart_tag`：图表类型，如 `bar-line` / `radar` / `pie` / `funnel` / `treemap` / `sunburst` / `sankey` / `empty`
- `debug_summary`：调试摘要信息

## 7. 当前核心流程

当前 MCP 的图表生成流程为两阶段：

1. 先基于 `existing_refs` 直接尝试生成图表
2. 如果首轮结果为 `empty` 或图表无效，则：
   - 基于图表描述、基础 query、首轮失败原因做 LLM query planning
   - 调用 aggSearch 补充检索
   - 将 `existing_refs + 新检索文档` 合并后重新抽取与生成图表

## 8. LLM 使用说明

LLM 主要用于以下三个环节：

- query planning
- 信息抽取（JSON，function calling 优先）
- 图表生成（基于 baseline prompt 直接输出 XML）

图表生成阶段使用中文 baseline prompt，最终返回真实图表文件，而不是仅返回占位说明。

当前支持为三个环节分别配置不同的 LLM：

- `planning`
- `extraction`
- `chart_generation`

如果没有单独配置某个环节，则自动回退到全局默认 LLM 配置。

### 通过环境变量配置

可选的分阶段环境变量包括：

- `MCP_DEMO_LLM_PLANNING_BASE_URL`
- `MCP_DEMO_LLM_PLANNING_API_KEY`
- `MCP_DEMO_LLM_PLANNING_MODEL`
- `MCP_DEMO_LLM_PLANNING_TIMEOUT_S`
- `MCP_DEMO_LLM_PLANNING_REQUIRE_HTTPS`
- `MCP_DEMO_LLM_PLANNING_FORCE_FUNCTION_CALL`

- `MCP_DEMO_LLM_EXTRACTION_BASE_URL`
- `MCP_DEMO_LLM_EXTRACTION_API_KEY`
- `MCP_DEMO_LLM_EXTRACTION_MODEL`
- `MCP_DEMO_LLM_EXTRACTION_TIMEOUT_S`
- `MCP_DEMO_LLM_EXTRACTION_REQUIRE_HTTPS`
- `MCP_DEMO_LLM_EXTRACTION_FORCE_FUNCTION_CALL`

- `MCP_DEMO_LLM_CHART_BASE_URL`
- `MCP_DEMO_LLM_CHART_API_KEY`
- `MCP_DEMO_LLM_CHART_MODEL`
- `MCP_DEMO_LLM_CHART_TIMEOUT_S`
- `MCP_DEMO_LLM_CHART_REQUIRE_HTTPS`
- `MCP_DEMO_LLM_CHART_FORCE_FUNCTION_CALL`

### 通过 tool 调用时传入 `config`

调用方也可以在调用 `generate_chart_markdown` 时，通过 `config.llm` 传入三阶段配置：

```json
{
  "review_payload": { "...": "..." },
  "config": {
    "llm": {
      "planning": {
        "base_url": "https://a.example.com/v1",
        "api_key": "sk-planning",
        "model": "planning-model",
        "timeout_s": 60,
        "force_function_call": true
      },
      "extraction": {
        "base_url": "https://b.example.com/v1",
        "api_key": "sk-extraction",
        "model": "extraction-model",
        "timeout_s": 90,
        "force_function_call": true
      },
      "chart_generation": {
        "base_url": "https://c.example.com/v1",
        "api_key": "sk-chart",
        "model": "chart-model",
        "timeout_s": 90
      }
    }
  }
}
```

字段说明：

- `planning`：用于 query planning
- `extraction`：用于 knowledges 抽取
- `chart_generation`：用于 baseline prompt 图表生成

如果只想覆盖其中一个阶段，只传对应那一段即可。

## 9. 运行依赖

项目依赖和环境变量见仓库内：

- `pyproject.toml`
- `.env.example`
- `README.md`

安装建议：

```bash
pip install -e .
```

## 10. 输出目录

运行后，主要产物输出到以下目录：

- `artifacts/charts/{request_id}/`
  - 最终图表图片
- `outputs/`
  - html/json/txt 结果包
