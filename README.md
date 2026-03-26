# Chart Plugin MCP

一个面向 `review -> chart generation` 场景的正式 MCP。

它接收上游直接传入的 `review_payload`，优先基于已有 `existing_refs` 直接成图；如果首轮失败，则最多补搜 1 轮，并将 `existing insights + top3 live docs` 一起送入第二次图表生成，最终返回可直接插入报告的 Markdown 图片引用。

## 1. 当前能力边界

- 只暴露一个正式 tool：`generate_chart_markdown`
- 只暴露一个 schema resource：`resource://schemas/plan_chart_retrieval`
- 整条链路最多两次 LLM 调用：
  - query planning
  - chart generation
- 只使用一套共享 LLM 配置
- 补搜轮数固定为 1 轮
- 第二轮只保留去重后的 top3 live docs
- 不再做 live docs 文档抽取
- 最终产物只保留 PNG，不再保留 SVG

## 2. MCP 暴露内容

### Tool

- `generate_chart_markdown`

### Resource

- `resource://schemas/plan_chart_retrieval`

## 3. 运行方式

### 直接启动 MCP server

```powershell
python -m MCP_demo
```

也可以使用：

```powershell
python -m MCP_demo.app.server
```

### 安装为本地命令

```powershell
pip install -e .
```

安装后可直接运行：

```powershell
chart-plugin-mcp
```

## 4. 输入契约

正式接入时，上游必须直接传入 `review_payload`。

### 必填字段

- `request_id`
- `chart_title`
- `chart_description`
- `existing_refs`

### 可选字段

- `write_requirement`
- `base_queries`
- `language`

### `existing_refs` 格式

```json
[
  {
    "id": 0,
    "content": "已有参考资料或上游抽取结果"
  }
]
```

### `base_queries` 格式

```json
[
  "基础检索 query 1",
  "基础检索 query 2"
]
```

### 最小输入示例

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

## 5. 输出契约

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

### 上游通常重点使用

- `markdown`
- `relative_path`
- `chart_tag`
- `debug_summary`

### 常见调试字段

- `retrieval_plan`
- `queries`
- `live_search_overview`
- `selected_live_docs`
- `docs_for_generation`
- `knowledges`
- `chart_decision_debug`
- `generation_attempts`
- `retry_gap_report`

## 6. 当前主流程

### 第一轮

1. 上游传入 `review_payload`
2. 将 `existing_refs` 视为已有 insights
3. 直接调用图表生成 LLM
4. 若图表有效，直接渲染输出

### 第二轮

仅当首轮结果为 `empty` 或图表数据无效时触发：

1. 基于图表任务和首轮失败原因做一次 query planning
2. 调用 aggSearch 做一次补搜
3. 对 live docs 去重后仅保留 top3
4. 将 `existing insights + top3 live docs` 一起送入第二次图表生成
5. 输出最终 PNG 图表

## 7. LLM 配置

当前只使用一套共享 LLM 配置。

同一套 LLM 同时用于：

- query planning
- chart generation

### 环境变量

- `MCP_DEMO_LLM_BASE_URL`
- `MCP_DEMO_LLM_API_KEY`
- `MCP_DEMO_LLM_MODEL`
- `MCP_DEMO_LLM_TIMEOUT_S`
- `MCP_DEMO_REQUIRE_HTTPS`
- `MCP_DEMO_FORCE_FUNCTION_CALL`

### 运行时通过 `config.llm` 覆盖

```json
{
  "review_payload": { "...": "..." },
  "config": {
    "llm": {
      "base_url": "https://a.example.com/v1",
      "api_key": "sk-xxx",
      "model": "model-name",
      "timeout_s": 90,
      "force_function_call": true
    }
  }
}
```

兼容说明：

- `config.llm` 可以直接传一套共享配置
- 如果调用方仍传旧的分阶段结构，当前实现会取其中第一套可用配置作为共享 LLM 使用

## 8. aggSearch 配置

- `MCP_DEMO_AGG_HOST`
- `MCP_DEMO_AGG_HOST_HEADER`
- `MCP_DEMO_AGG_PIPELINE`
- `MCP_DEMO_AGG_TIMEOUT_MS`
- `MCP_DEMO_AGG_TOP_K`

说明：

- 当前仓库已经内置 aggSearch client
- 运行环境仍需能访问配置好的 aggSearch endpoint

## 9. 渲染与产物

### 输出目录

- `outputs/`
  - html/json/txt 结果包
- `artifacts/charts/{request_id}/`
  - 最终图表图片 `chart_01.png`

### 渲染行为

- PNG 导出依赖运行环境里本机无头 Edge/Chrome
- 如果本机没有可用 Edge/Chrome，PNG 导出会直接报错

## 10. 主要目录

```text
MCP_demo/
  app/
    server.py
  clients/
    agg_search.py
    llm.py
  core/
    chart_plugin.py
    baseline_decider.py
    renderer.py
  schemas/
    function_schemas.py
    plan_chart_retrieval.tools.json
  assets/
    baseline_chart_prompt.txt
    query_planning_prompt.txt
  vendor/
    echarts.min.js
    render_utils.py
    md2html.py
  config.py
  .env.example
  README.md
  HANDOFF.md
```

## 11. 建议重点查看的调试字段

- `debug_summary.final_stage`
  - 看最终停在哪一轮
- `debug_summary.selected_live_docs_count`
  - 看第二轮实际用了多少 live docs
- `generation_attempts`
  - 看每一轮尝试的摘要
- `retry_gap_report`
  - 看首轮失败原因
- `chart_decision_debug`
  - 看图表决策是否失败、失败在哪
