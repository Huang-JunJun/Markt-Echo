# OpenClaw 交易复盘助手 V1（最小可用闭环）

本仓库实现了你定义的 V1 两层分工：
- OpenClaw 层：触发、编排、模型总结、输出、手动重跑、查看今日结果
- Python 数据服务层：拉取/清洗/标准化/存储，向 OpenClaw 提供统一结构化 JSON

当前仅覆盖：
1. 盘前复盘
2. 9:25 竞价复盘
3. 收盘复盘

不包含午盘复盘、盘中监听、多用户、复杂后台等扩展能力。

## 1. 项目结构

```text
app/
  api.py                # FastAPI 路由
  main.py               # 应用入口
  service.py            # 业务编排（生成报告、查询、回写）
  storage.py            # SQLite 存储（结构化、原始、状态、最终文本）
  schemas.py            # 统一数据结构
  providers/
    mock_provider.py    # V1 mock 数据源（默认）

openclaw/
  prompts/              # 三类报告提示词模板
  workflows/v1_tasks.yaml  # OpenClaw 任务编排蓝图（调度+手动触发）

tests/
  test_api.py           # API 基础用例
```

## 2. FastAPI 数据服务

### 2.1 启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

默认地址：`http://127.0.0.1:8000`

可选环境变量见 `.env.example`。

### 2.2 已实现接口

- `GET /health`
- `POST /v1/review/pre-market`
- `POST /v1/review/auction`
- `POST /v1/review/close`
- `GET /v1/reports/today?report_type=pre_market|auction|close`
- `POST /v1/reports/{report_id}/final-text`

### 2.3 统一返回结构（示例）

```json
{
  "ok": true,
  "data": {
    "report_id": "pre_market-2026-03-11-xxxx",
    "report_type": "pre_market",
    "trade_date": "2026-03-11",
    "generated_at": "2026-03-11T08:40:00+08:00",
    "summary_data": {},
    "raw_data": {},
    "warnings": [],
    "status": "SUCCESS",
    "source": "mock"
  },
  "error": null
}
```

约束：
- 外层结构固定：`ok/data/error`
- `summary_data` + `raw_data` 双层并存
- 数据缺失通过 `warnings` 提示，不因局部缺失导致整体失败

## 3. 存储策略（V1）

使用 SQLite（`.data/market_echo_v1.db`）保存：
1. 报告类型
2. 生成时间
3. 结构化数据
4. 原始数据
5. 最终输出文本（由 OpenClaw 回写）
6. 执行状态（SUCCESS/PARTIAL/FAILED）
7. 错误信息

## 4. OpenClaw 层落地方式

`openclaw/workflows/v1_tasks.yaml` 提供了 V1 编排蓝图，包含：
- 三个定时任务
  - 盘前：工作日 08:40
  - 竞价：工作日 09:25 + 延迟 10 秒
  - 收盘：工作日 15:10
- 三个手动命令：`/run pre_market`、`/run auction`、`/run close`
- 今日结果查看命令：`/today ...`
- 失败提示分支
- 模型总结后回写 `final_output_text`

`openclaw/prompts/` 中提供三类固定模板提示词。

> 说明：不同 OpenClaw 版本的 workflow 字段命名可能有差异，蓝图需要在 Control UI 内按实际字段映射一次。

盘前单节点验收请使用：
- `openclaw/workflows/v1_pre_market_only.yaml`
- `acceptance/pre_market_acceptance.md`

## 5. 联调顺序（按你的要求）

1. 先做 mock 联调（当前默认已启用）
2. 先落地盘前复盘
3. 再落地收盘复盘
4. 最后优化竞价复盘

## 6. 测试

```bash
pytest
```

当前测试覆盖：
- 健康检查
- 三节点接口生成（含 mock 回退 warning）
- 今日结果查询
- 最终文本回写
