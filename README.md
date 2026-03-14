# OpenClaw 交易复盘助手 V1

本仓库实现了 V1 两层分工：
- OpenClaw 层：正式入口、模型加工、正文输出、回写
- Python 数据服务层：抓取、清洗、标准化、存储、对外提供统一 JSON

当前仅覆盖：
1. 盘前复盘 `pre_market`
2. 9:25 竞价复盘 `auction`
3. 收盘复盘 `close`

不包含午盘复盘、盘中监听、多用户、复杂后台等扩展能力。

## 1. 当前怎么使用

### 1.1 先启动 Python 数据服务

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

默认地址：`http://127.0.0.1:8000`

### 1.2 在 OpenClaw Control UI 中如何触发

当前这台机器上，建议按下面的 agent 与命令使用：

1. 盘前复盘
   - agent：`main`
   - 命令：`/pre_market` 或 `/盘前复盘`
2. 收盘复盘
   - agent：`close-main`
   - 命令：`/close` 或 `/收盘复盘`
3. 竞价复盘
   - agent：`auction-real-main`
   - 命令：`/auction` 或 `/竞价复盘`

说明：
- 最终聊天回复默认只返回正文，不返回 JSON。
- 技术字段仍会写入日志和数据库，便于排查。
- 如果某个 agent 的旧会话残留了历史上下文，直接新开一个 session 再发同一条命令即可。
- 中文入口与英文入口等价，触发的是同一条既有链路，不是单独维护的第二套实现。

### 1.3 当前节点状态

1. `pre_market`
   - 当前数据状态：`real_partial`
   - 说明：核心真实字段已接通，部分观察方向仍为 derived
2. `close`
   - 当前数据状态：`real`
   - 说明：核心复盘口径已接近正式可用
3. `auction`
   - 当前数据状态：`real_partial`
   - 说明：指数竞价、强弱榜、成交榜为真实；方向和情绪仍为 derived
   - 额外说明：如果当前时间不在 `09:15-09:26` 竞价窗口，返回的是最新可用真实快照，并会在 `warnings` 中明确提示

## 2. 项目结构

```text
app/
  api.py                         # FastAPI 路由
  main.py                        # 应用入口
  service.py                     # 业务编排（生成报告、查询、回写）
  storage.py                     # SQLite 存储
  schemas.py                     # 统一数据结构
  providers/
    mock_provider.py             # mock 数据源
    real_pre_market_provider.py  # 盘前真实数据源
    real_auction_provider.py     # 竞价真实数据源
    real_close_provider.py       # 收盘真实数据源

openclaw/
  prompts/                       # 三类正文模板
  scripts/                       # fetch / writeback 辅助脚本
  skills/                        # /pre_market /auction /close 正式入口
  workflows/                     # V1 workflow 蓝图（可选）

tests/
  test_api.py                    # API 基础用例
```

## 3. FastAPI 数据服务

### 3.1 已实现接口

- `GET /health`
- `POST /v1/review/pre-market`
- `POST /v1/review/auction`
- `POST /v1/review/close`
- `GET /v1/reports/today?report_type=pre_market|auction|close`
- `POST /v1/reports/{report_id}/final-text`

### 3.2 统一返回结构

```json
{
  "ok": true,
  "data": {
    "report_id": "auction-2026-03-14-xxxx",
    "report_type": "auction",
    "trade_date": "2026-03-14",
    "generated_at": "2026-03-14T09:25:10+08:00",
    "summary_data": {},
    "raw_data": {},
    "warnings": [],
    "status": "SUCCESS",
    "source": "real_partial"
  },
  "error": null
}
```

约束：
- 外层结构固定：`ok / data / error`
- `summary_data` 给 OpenClaw 生成正文
- `raw_data` 保留技术明细
- 缺失或降级信息进入 `warnings`

### 3.3 直接调用 API 示例

盘前：

```bash
curl -X POST http://127.0.0.1:8000/v1/review/pre-market \
  -H 'Content-Type: application/json' \
  -d '{"use_mock": false}'
```

竞价：

```bash
curl -X POST http://127.0.0.1:8000/v1/review/auction \
  -H 'Content-Type: application/json' \
  -d '{"use_mock": false}'
```

收盘：

```bash
curl -X POST http://127.0.0.1:8000/v1/review/close \
  -H 'Content-Type: application/json' \
  -d '{"use_mock": false}'
```

查看今日报告：

```bash
curl 'http://127.0.0.1:8000/v1/reports/today?report_type=auction'
```

## 4. OpenClaw 层落地方式

当前正式入口以 `skills` 为准：
- [`openclaw/skills/pre_market/SKILL.md`](openclaw/skills/pre_market/SKILL.md)
- [`openclaw/skills/auction/SKILL.md`](openclaw/skills/auction/SKILL.md)
- [`openclaw/skills/close/SKILL.md`](openclaw/skills/close/SKILL.md)

当前 OpenClaw 的职责是：
1. 触发 Python fetch
2. 读取结构化 `summary_data`
3. 调用模型生成正文
4. 回写 `final_text`
5. 默认只把正文回复给用户

`openclaw/workflows/` 下的 YAML 仍保留为 V1 蓝图，但当前联调与正式手动入口以 `skills` 为主，不建议把 README 里的使用方式理解成“必须先导入 workflow 才能手动跑”。

## 5. 存储与排查

SQLite 数据库：
- `.data/market_echo_v1.db`

运行日志：
- `.data/pre_market_runs.jsonl`
- `.data/auction_runs.jsonl`
- `.data/close_runs.jsonl`

保存内容：
1. 报告类型
2. 生成时间
3. 结构化数据
4. 原始数据
5. 最终输出文本
6. 执行状态
7. 错误信息

## 6. 测试

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

当前测试覆盖：
- 健康检查
- 三节点接口生成
- mock / real provider 路由
- 今日结果查询
- `final_text` 回写
