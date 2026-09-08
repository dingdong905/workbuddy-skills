# 数据 Schema（intake / valuation）

## intake JSON

```json
{
  "company": "全称",
  "ticker": "交易所:代码",
  "as_of": "数据截止日",
  "reporting_basis": "consolidated",
  "currency": "CNY",
  "units": "million",
  "fiscal_year_end": "December",
  "latest_reported_period": {"period": "Q2 2026", "published": "披露日"},
  "datapoints": [
    {
      "metric": "revenue",
      "value": 2147.98,
      "period": "Q2 2026 YTD",
      "basis": "consolidated",
      "unit": "CNY million",
      "source": "2026 half-year report, p.5",
      "source_tier": 1
    }
  ],
  "not_available": ["拿不到的数据如实列出"]
}
```

字段规则：

- `metric` 用英文标准名：revenue / PAT attributable（归母净利润）/ operating cash flow / capital expenditure / cash / debt / equity attributable / share price / market capitalisation；其余自定义但要一致
- `source` 必须含文件名与页码（或公告编号）；行情类写"接口名 + 查询日期"
- `source_tier`：1=法定披露；2=第一方 IR；3=独立二手；4=聚合器/行情接口
- 同一 metric 多期数据拆成多个 datapoint，period 区分（FY2025 / Q2 2026 YTD / Q2 2026 时点数）

## valuation JSON

```json
{
  "company": "全称",
  "ticker": "交易所:代码",
  "as_of": "估值基准日",
  "currency": "CNY",
  "units": "CNY million",
  "market": {"price": 19.89, "shares_out": 567.1, "market_cap": 11279.9, "as_of": "日期"},
  "ev_bridge": {
    "market_cap": 0,
    "total_debt": 0,
    "cash": 0,
    "minority_interest": 0,
    "preferred": 0,
    "lease_liabilities": 0,
    "associate_investments": 0
  },
  "financials": {"pat": 0, "sales": 0, "book_value_equity": 0, "fcf": 0, "dividends": 0},
  "reverse_dcf": {"base_fcf": 0, "wacc": 0.105, "stage1_years": 5, "terminal_growth": 0.03},
  "dcf": {
    "base_fcf": 0, "stage1_growth": 0.08, "stage1_years": 5,
    "fade_years": 5, "terminal_growth": 0.03, "wacc": 0.105,
    "net_debt": 0, "minority": 0, "shares_out": 0
  },
  "scenarios": [
    {"label": "Bear", "prob": 0.25, "eps": 0, "exit_pe": 0},
    {"label": "Base", "prob": 0.50, "eps": 0, "exit_pe": 0},
    {"label": "Bull", "prob": 0.25, "eps": 0, "exit_pe": 0}
  ]
}
```

字段规则：

- `ev_bridge.cash`：经济性口径，含大额存单、定存、理财时需在报告正文说明认定理由
- `financials.pat` 用 TTM 或注明期间；与 intake 数字可勾稽
- `reverse_dcf.base_fcf` 是规范化 FCF（剔除一次性营运资本扰动），假设必须写进报告
- `scenarios` 概率合计 = 1；每情景的 eps/exit_pe 在报告中配关键假设一句话
- 命名文件：`<公司拼音>_intake.json` / `<公司拼音>_valuation.json`，与报告同目录
