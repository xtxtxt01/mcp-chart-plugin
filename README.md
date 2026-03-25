# Chart Plugin MCP

一个面向 `review -> chart plugin` 场景的正式 MCP。

它的职责只有一件事：

- 接收上游直接传入的 `review_payload`
- 先利用 `existing_refs` 尝试成图
- 如首轮失败，再结合 `base_queries` 做补充检索和二次生成
- 返回可直接插入报告的 Markdown 图片引用和相对路径

典型返回中的核心字段是：

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

说明：

- `markdown` 和 `relative_path` 返回的是相对 `MCP_demo/` 根目录的路径
- 最终图片优先导出为 `chart_01.png`
- 如果本机无头 Edge/Chrome 不可用，才回退为 `chart_01.svg`

## 当前流程

### 第一轮：只用上游已有信息

1. 上游直接传入 `review_payload`
2. 将 `existing_refs` 视为上游已有 insights
3. 不对 `existing_refs` 重复做一轮信息抽取
4. 直接调用 baseline prompt + LLM 生成图表

### 第二轮：首轮失败后补检索

只有当第一轮结果为 `empty` 或图表数据无效时，才进入第二轮：

1. 基于以下信息做 LLM query planning：
   - 图表标题
   - 图表描述
   - 写作要求
   - `base_queries`
   - 首轮失败原因
   - 已有 insights 预览
2. 调用 aggSearch
3. 保留：
   - 全部 `existing_refs`
   - live docs top 10
4. 只对新搜到的 live docs 做 LLM 抽取
5. 合并：
   - existing insights
   - live insights
6. 再调用 baseline prompt + LLM 生成图表
7. 渲染最终图片、html 预览和 markdown

## 目录结构

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
    extract_chart_facts.tools.json
    plan_chart_retrieval.tools.json
  assets/
    baseline_chart_prompt.txt
  vendor/
    render_utils.py
    md2html.py
  config.py
  pyproject.toml
  .env.example
  README.md
  HANDOFF.md
```

## 目录职责

### `app/`

- `server.py`
  - MCP server 入口
  - 注册正式 tool 和 schema resources

### `clients/`

- `agg_search.py`
  - aggSearch 客户端
- `llm.py`
  - LLM 客户端
  - 优先 function calling
  - 模型不兼容时退回文本 JSON 解析

### `core/`

- `chart_plugin.py`
  - 插件主流程
  - 两阶段生成逻辑
  - knowledges 合并
  - gap-aware query planning
- `baseline_decider.py`
  - 直接加载 `assets/baseline_chart_prompt.txt`
  - 使用 LLM 输出图表 XML
- `renderer.py`
  - 生成 `.txt/.json/.html`
  - 生成最终图片
  - 优先基于同一份 ECharts option 用无头浏览器导出 PNG
  - 浏览器不可用时回退到 SVG

### `schemas/`

- `function_schemas.py`
  - function calling schema 定义
- `plan_chart_retrieval.tools.json`
  - query planning schema
- `extract_chart_facts.tools.json`
  - knowledges 抽取 schema

### `assets/`

- `baseline_chart_prompt.txt`
  - 原始中文图表生成 prompt
  - 当前直接作为图表生成 LLM prompt 使用

### `vendor/`

- `render_utils.py`
  - ECharts option 和 html 预览链
- `md2html.py`
  - html 渲染辅助

## MCP 暴露内容

### Tool

- `generate_chart_markdown`

输入：

- `review_payload`
- 可选 `config`

### Resources

- `resource://schemas/plan_chart_retrieval`
- `resource://schemas/extract_chart_facts`

## 输入契约

正式接入时，上游必须直接传入 `review_payload`。

### 必填字段

- `request_id`
  - 本次图表请求唯一标识
- `chart_title`
  - 图表标题
- `chart_description`
  - 图表想表达的核心可视化目标
- `existing_refs`
  - 上游已有参考资料或已抽取的 insights 列表
- `write_requirement`
  - 本章/本节写作要求
- `base_queries`
  - 基础检索 queries，用于首轮失败后补检索

### `existing_refs` 格式

`existing_refs` 是一个数组，每项至少建议包含：

```json
{
  "id": 0,
  "content": "已有参考资料或上游抽取结果"
}
```

字段约定：

- `id`
  - 可选，整数或可转整数的标识
- `content`
  - 必填，文本内容

### `base_queries` 格式

`base_queries` 是字符串数组，例如：

```json
[
  "2026 海信 RGB Mini LED 分区数 亮度 色域",
  "2026 TCL SQD Mini LED 分区数 亮度 色域"
]
```

### 最小输入示例

```json
{
  "review_payload": {
    "request_id": "case-001",
    "chart_title": "对比海信与TCL在2026年主导的两种Mini LED技术路线的核心画质参数差异",
    "chart_description": "对比海信与TCL在2026年主导的两种Mini LED技术路线的核心画质参数差异，直观展示其在分区、亮度、色域等关键指标上的技术分化。",
    "write_requirement": "请生成一张可直接插入报告的图表。",
    "existing_refs": [
      {
        "id": 0,
        "content": "TCL在2026年推出SQD-Mini LED技术，98英寸版本配备20736个万象分区，峰值亮度突破10000nits，实现100% BT.2020全局高色域覆盖。"
      },
      {
        "id": 1,
        "content": "海信在2026年主打RGB-Mini LED技术，峰值亮度为7000-9000nits，色域覆盖为100-110% BT.2020。"
      }
    ],
    "base_queries": [
      "2026 海信 RGB Mini LED 分区数 亮度 色域",
      "2026 TCL SQD Mini LED 分区数 亮度 色域"
    ]
  }
}
```

## 输出字段

当前返回中最常用的字段包括：

- `success`
- `markdown`
- `relative_path`
- `chart_tag`
- `debug_summary`

同时还会返回调试字段，例如：

- `retrieval_plan`
- `queries`
- `live_search_overview`
- `docs_for_extraction`
- `docs_for_generation`
- `knowledges`
- `references`
- `extraction_debug`
- `chart_decision_debug`
- `generation_attempts`
- `retry_gap_report`

## LLM 使用方式

当前有 3 个 LLM 环节：

1. `plan_chart_retrieval`
   - 做 query planning
   - 输入包含图表任务和 gap report
   - function calling 优先

2. `extract_chart_facts`
   - 实际输出结构为 `knowledges[]`
   - prompt 使用中文“信息提取专家”模板
   - function calling 优先

3. 图表生成
   - 直接使用 `assets/baseline_chart_prompt.txt`
   - 输出 XML
   - 再解析为图表 spec

## 渲染行为

会产出两类文件：

### 1. `outputs/*.html`

- ECharts 真预览
- 由 `vendor/render_utils.py` 的 option 生成

### 2. `artifacts/charts/{request_id}/chart_01.png|svg`

- 最终 markdown 引用的图表文件
- 优先使用同一份 ECharts option 经无头 Edge/Chrome 导出 PNG
- 浏览器不可用时回退到 SVG

因此，新生成的 case 中：

- `outputs/*.html`
- `artifacts/charts/.../chart_01.png`

应尽量保持一致。

## 运行方式

### 1. 启动 MCP server

```powershell
python -m MCP_demo
```

或：

```powershell
python -m MCP_demo.app.server
```

### 2. 作为可安装项目使用

在 `MCP_demo/` 目录下：

```powershell
pip install -e .
```

安装后可用：

```powershell
chart-plugin-mcp
```

## 配置

统一配置在 `config.py`，主要环境变量如下：

### aggSearch

- `MCP_DEMO_AGG_HOST`
- `MCP_DEMO_AGG_HOST_HEADER`
- `MCP_DEMO_AGG_PIPELINE`
- `MCP_DEMO_AGG_TIMEOUT_MS`
- `MCP_DEMO_AGG_TOP_K`

### retrieval / generation

- `MCP_DEMO_MAX_QUERIES`
- `MCP_DEMO_MAX_DOCS`
- `MCP_DEMO_EXISTING_REFS_QUOTA`
- `MCP_DEMO_LIVE_DOCS_QUOTA`

说明：

- 当前主流程实际采用的是：
  - `existing_refs` 全保留
  - `live docs` top 10

### LLM

- `MCP_DEMO_LLM_BASE_URL`
- `MCP_DEMO_LLM_API_KEY`
- `MCP_DEMO_LLM_MODEL`
- `MCP_DEMO_LLM_TIMEOUT_S`
- `MCP_DEMO_REQUIRE_HTTPS`
- `MCP_DEMO_FORCE_FUNCTION_CALL`

参考：

- `.env.example`

## 输出目录

### 最终图表文件

位于：

```text
artifacts/charts/{request_id}/chart_01.png
```

如浏览器导出失败，则可能是：

```text
artifacts/charts/{request_id}/chart_01.svg
```

### 调试产物

位于 `outputs/`：

- `mcp_demo_chart__{request_id}.txt`
- `mcp_demo_chart__{request_id}.json`
- `mcp_demo_chart__{request_id}.html`

## 最值得看的调试字段

如果你要定位某次成图过程，优先看：

- `generation_attempts`
- `retry_gap_report`
- `debug_summary`
- `chart_decision_debug`
- `docs_for_extraction`
- `docs_for_generation`
- `knowledges`

其中：

- `generation_attempts`
  - 能看出首轮是否只用了 existing insights
  - 第二轮是否补了 aggSearch
- `retry_gap_report`
  - 能看出第一次成图失败的原因
- `debug_summary.final_stage`
  - 能看出最终停在哪一轮

## 分阶段 LLM 配置

当前支持为三个环节分别配置不同的 LLM：

- `planning`
- `extraction`
- `chart_generation`

如果没有单独配置某个环节，则自动回退到全局默认 LLM 配置。

### 环境变量方式

除全局默认值外，还支持：

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

### 运行时 `config` 传参方式

调用 `generate_chart_markdown` 时，也可以在 `config.llm` 中分别传入：

```json
{
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
```
