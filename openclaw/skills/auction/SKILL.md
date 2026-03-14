---
name: auction
description: 竞价正式入口（支持 /auction、/竞价复盘）。Python 提供结构化数据，OpenClaw 使用模型生成竞价文本并回写。
user-invocable: true
---

# auction

## 触发方式

用户在 OpenClaw 聊天中输入 `/auction` 或 `/竞价复盘`。
两种输入都必须触发同一条现有 `auction` 链路，不允许分叉实现。

## 执行规则

1. 禁止使用 `exec` 与 `nodes.run`（当前节点不支持 `system.run.prepare`）。
2. 先用 `nodes` 工具拉取结构化数据（fetch）：
```json
{
  "action": "invoke",
  "node": "4c752fdc47dd9f7c942eb42539f408a6dbcf5f5fc2817486c37aac02c8bb40b8",
  "invokeCommand": "system.run",
  "invokeParamsJson": "{\"command\":[\"/bin/zsh\",\"-lc\",\"python3 /Users/Project/Market-Echo/openclaw/scripts/run_auction.py --mode fetch --base-url http://127.0.0.1:8000 --use-mock false --output json\"],\"timeoutMs\":120000}"
}
```
3. 从 `payload.stdout` 解析 JSON，必须拿到 `report_id`、`trade_date`、`summary_data`、`warnings`。
4. 使用模型生成最终竞价文本（`final_text`）：
   - 必须读取并遵循模板文件：`/Users/Project/Market-Echo/openclaw/prompts/auction_prompt.md`
   - 只允许基于 `summary_data` 和 `warnings` 生成，不要自行联网补数据。
   - 一级标题结构必须固定为：
     - `# 9:25 竞价复盘（{trade_date}）`
     - `## 1) 一句话判断`
     - `## 2) 高标 / 核心反馈`
     - `## 3) 板块竞价前列`
     - `## 4) 开盘观察`
     - `## 数据提示`
5. 将 `final_text` 写入：
   - `/Users/huangjunjun/.openclaw/workspace/tmp/auction_final_text.md`
6. 再用 `nodes` 工具执行回写（writeback）：
```json
{
  "action": "invoke",
  "node": "4c752fdc47dd9f7c942eb42539f408a6dbcf5f5fc2817486c37aac02c8bb40b8",
  "invokeCommand": "system.run",
  "invokeParamsJson": "{\"command\":[\"/bin/zsh\",\"-lc\",\"python3 /Users/Project/Market-Echo/openclaw/scripts/run_auction.py --mode writeback --base-url http://127.0.0.1:8000 --report-id <report_id> --final-text-file /Users/huangjunjun/.openclaw/workspace/tmp/auction_final_text.md --output json\"],\"timeoutMs\":120000}"
}
```
7. 若 fetch 或 writeback 任一步失败，只返回必要错误信息，不要虚构结果。
8. 默认最终回复给用户时，只返回 `final_text`，不要展示 `auction_api_response`、`writeback_response`、`report_id`。
9. 最终 assistant 回复必须与 `final_text` 完全一致，不要添加“写入成功”“节点调用”“读取文件”等过程说明前后缀。

## 约束

- 当前只处理 auction，不处理 pre_market / close / 其他节点。
- 当前 auction 优先使用真实数据；若非竞价窗口则只使用最新可用真实快照，不扩展其他节点。
