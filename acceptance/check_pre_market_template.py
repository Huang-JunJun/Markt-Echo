from __future__ import annotations

from pathlib import Path

EXPECTED_HEADINGS = [
    "# 盘前复盘（2026-03-11）",
    "## 1) 海内外与期指信号",
    "## 2) 今日关键事件",
    "## 3) 重点观察方向",
    "## 4) 开盘前执行清单",
    "## 数据提示",
]


def main() -> None:
    file_path = Path(__file__).resolve().parent / "pre_market_final_text_sample.md"
    content = file_path.read_text(encoding="utf-8").splitlines()

    found_headings = [line for line in content if line.startswith("#")]

    if found_headings != EXPECTED_HEADINGS:
        raise SystemExit(
            "Template check failed.\n"
            f"Expected: {EXPECTED_HEADINGS}\n"
            f"Found: {found_headings}"
        )

    print("Template check passed: headings match V1 pre-market template exactly.")


if __name__ == "__main__":
    main()
