---
name: pre_market
description: 盘前正式入口。Python 仅供数，OpenClaw 使用模型生成盘前文本并回写。
user-invocable: true
---

# pre_market

## 触发方式

用户在 OpenClaw 聊天中输入 `/pre_market`。

## 执行规则

1. 禁止使用 `exec` 与 `nodes.run`（当前节点不支持 `system.run.prepare`）。
2. 先用 `nodes` 工具拉取结构化数据（fetch）：
```json
{
  "action": "invoke",
  "invokeCommand": "system.run",
  "invokeParamsJson": "{\"command\":[\"/bin/zsh\",\"-lc\",\"python3 /Users/Project/Market-Echo/openclaw/scripts/run_pre_market.py --mode fetch --base-url http://127.0.0.1:8000 --use-mock true --output json\"],\"timeoutMs\":120000}"
}
```
3. 从 `payload.stdout` 解析 JSON，必须拿到 `report_id`、`trade_date`、`summary_data`、`warnings`。
4. 使用模型生成最终盘前文本（`final_text`）：
   - 必须读取并遵循模板文件：`/Users/Project/Market-Echo/openclaw/prompts/pre_market_prompt.md`
   - 只允许基于 `summary_data` 和 `warnings` 生成，不要自行联网补数据。
   - 一级标题结构必须固定为：
     - `# 盘前复盘（{trade_date}）`
     - `## 1) 海内外与期指信号`
     - `## 2) 今日关键事件`
     - `## 3) 重点观察方向`
     - `## 4) 开盘前执行清单`
     - `## 数据提示`
5. 将 `final_text` 写入：
   - `/Users/huangjunjun/.openclaw/workspace/tmp/pre_market_final_text.md`
6. 再用 `nodes` 工具执行回写（writeback）：
```json
{
  "action": "invoke",
  "invokeCommand": "system.run",
  "invokeParamsJson": "{\"command\":[\"/bin/zsh\",\"-lc\",\"python3 /Users/Project/Market-Echo/openclaw/scripts/run_pre_market.py --mode writeback --base-url http://127.0.0.1:8000 --report-id <report_id> --final-text-file /Users/huangjunjun/.openclaw/workspace/tmp/pre_market_final_text.md --output json\"],\"timeoutMs\":120000}"
}
```
7. 若 fetch 或 writeback 任一步失败，只返回必要错误信息，不要虚构结果。
8. 默认最终回复给用户时，只返回 `final_text`，不要展示 `pre_market_api_response`、`writeback_response`、`report_id`。
9. 最终 assistant 回复必须与 `final_text` 完全一致，不要添加“写入成功”“节点调用”“读取文件”等过程说明前后缀。

## 约束

- 只处理 pre_market，不处理 close / auction / 其他节点。
- 不扩展功能，不补充无关建议。
