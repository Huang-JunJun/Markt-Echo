# 盘前节点 V1 验收记录（模型加工正式模式）

日期：2026-03-11（Asia/Shanghai）  
范围：仅 `pre_market`，未推进 close / auction / 其他功能。

## 1) 模式确认（已切换）

- `/pre_market` 触发后：
  - Python 仅返回结构化数据（fetch）
  - OpenClaw 使用模型按模板生成盘前文本
  - Python 执行 writeback 回写 `final_text`
  - 默认给用户只返回最终盘前文本，不返回 JSON 技术字段

相关文件：
- `openclaw/scripts/run_pre_market.py`
- `openclaw/skills/pre_market/SKILL.md`
- `openclaw/prompts/pre_market_prompt.md`

## 2) Python 返回结构（fetch）

`run_pre_market.py --mode fetch --output json` 返回：
```json
{
  "report_id": "pre_market-YYYY-MM-DD-xxxxxxxxxx",
  "trade_date": "YYYY-MM-DD",
  "summary_data": { "...": "..." },
  "warnings": [],
  "pre_market_api_response": { "...": "..." }
}
```

说明：
- Python 不生成自然语言盘前总结。
- `pre_market_api_response`、`report_id` 等技术字段保留用于日志/排查。

## 3) OpenClaw 模板与加工规则

OpenClaw 在 skill 中强制读取：
- `openclaw/prompts/pre_market_prompt.md`

固定一级标题模板：
- `# 盘前复盘（{trade_date}）`
- `## 1) 海内外与期指信号`
- `## 2) 今日关键事件`
- `## 3) 重点观察方向`
- `## 4) 开盘前执行清单`
- `## 数据提示`

## 4) 真实执行证据（默认输出已从 JSON 改为文本）

触发命令：
- `openclaw agent --agent main --session-id pre-market-model-mode-20260311 --message '/pre_market' --json`

原始 run 结果：
- `acceptance/pre_market_model_mode_run.json`
- `status = ok`
- `runId = d4386a3f-7f97-49d4-88ff-9c7ab27f9700`

默认回包（仅文本，无 JSON 技术字段）：
- `acceptance/pre_market_model_mode_final_text.md`
- 首行：`# 盘前复盘（2026-03-11）`

## 5) 技术字段保留与回写证明

调试日志（JSONL）：
- `.data/pre_market_runs.jsonl`
- 本次对应条目：
  - `acceptance/pre_market_model_mode_fetch_log.json`
  - `acceptance/pre_market_model_mode_writeback_log.json`

字段确认：
- fetch 日志中保留：`pre_market_api_response`、`report_id`、`summary_data`、`warnings`
- writeback 日志中保留：`report_id`、`writeback_response`

回写落库确认：
- `acceptance/pre_market_model_mode_today.json`
- `acceptance/pre_market_model_mode_record.json`
- 关键结果：
  - `report_id = pre_market-2026-03-11-edc565428c`
  - `execution_status = SUCCESS`
  - `final_output_text` 非空，首行为 `# 盘前复盘（2026-03-11）`

## 6) 当前结论

- `/pre_market` 已符合“Python 供数 + OpenClaw 模型加工”模式。
- 默认用户看到的是盘前文本，不再是技术验收 JSON。
- 技术字段仍保留在日志与存储中，回写逻辑保持生效。

## 7) 输出收敛复核（Control UI 体验向）

复核命令：
- `openclaw agent --agent main --session-id pre-market-output-converge-20260311 --message '/pre_market' --json`

复核结果：
- `acceptance/pre_market_output_converged_run.json`
- `runId = 3e270d83-a828-4f42-82c0-e867b145dce8`
- `payload_count = 1`
- `payload[0].text` 以 `# 盘前复盘（2026-03-11）` 开头
- `payload[0].text` 不包含：
  - `pre_market_api_response`
  - `writeback_response`
  - `report_id`

正文样例：
- `acceptance/pre_market_output_converged_final_text.md`

回写成功证明：
- `acceptance/pre_market_output_converged_writeback_log.json`
- `acceptance/pre_market_output_converged_record.json`
- 关键字段：
  - `writeback_response.status = SUCCESS`
  - `execution_status = SUCCESS`

## 8) 收尾确认（正式可用前）

本轮触发命令：
- `openclaw agent --agent main --session-id pre-market-finalize-20260311 --message '/pre_market' --json`

本轮结果：
- `acceptance/pre_market_finalize_run.json`
- `runId = 5510fd0d-7835-41e1-977b-5422604b109a`
- `payload_count = 1`
- 最终回复仅正文，不含 `pre_market_api_response` / `writeback_response` / `report_id`
- 正文文件：`acceptance/pre_market_finalize_final_text.md`

数据源状态：
- 当前仍为 `mock`
- 证据：`acceptance/pre_market_finalize_fetch_log.json` 中 `pre_market_api_response.data.source = "mock"`

每次触发的数据获取路径：
1. Control UI 输入 `/pre_market`
2. skill 调用 `run_pre_market.py --mode fetch --use-mock true`
3. 脚本请求 `POST /v1/review/pre-market`
4. API 返回结构化数据（含 `report_id/summary_data/warnings/source`）
5. OpenClaw 模型基于模板生成正文 `final_text`
6. skill 调用 `run_pre_market.py --mode writeback`
7. 脚本请求 `POST /v1/reports/{report_id}/final-text` 回写
8. 返回给用户最终正文

本轮回写验证：
- `acceptance/pre_market_finalize_writeback_log.json`（`writeback_response.status = SUCCESS`）
- `acceptance/pre_market_finalize_record.json`（`execution_status = SUCCESS` 且 `final_output_text` 非空）
