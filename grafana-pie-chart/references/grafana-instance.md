# Grafana 实例参考（饼图相关）

## 实例信息

- 地址：`http://***REMOVED***`（Grafana，内网直达，Windows Git Bash 下 curl 正常）
- 凭据：服务账号，从用户处获取；脚本中经环境变量 `GRAFANA_AUTH`（格式 `user:password`）传入，勿明文落盘
- 数据源：ClickHouse，`{"type": "grafana-clickhouse-datasource", "uid": "clickhouse"}`

## 核心 API

| 操作 | 方法与路径 | 说明 |
|------|-----------|------|
| 健康检查 | `GET /api/health` | 匿名可用 |
| 列仪表板 | `GET /api/search?query=` | 需 Basic Auth |
| 读仪表板 | `GET /api/dashboards/uid/{uid}` | 含面板 SQL/变量/样式，改动前先备份 |
| 测试查询 | `POST /api/ds/query` | 见下方请求体 |
| 建板/更新 | `POST /api/dashboards/db` | **只能 curl 提交**，payload `{"dashboard": {...}, "folderId": 0, "overwrite": true, "message": "..."}` |

## /api/ds/query 请求体

```json
{
  "queries": [{
    "refId": "A",
    "datasource": {"type": "grafana-clickhouse-datasource", "uid": "clickhouse"},
    "rawSql": "<替换宏后的 SQL>",
    "format": "table",
    "queryType": "sql"
  }],
  "from": "<起毫秒>",
  "to": "<止毫秒>"
}
```

- 响应数据位置：`results.A.frames[0].data.values`（列优先二维数组），列名在 `frames[0].schema.fields[].name`
- 宏替换：`$__timeFilter(col)` → `col >= toDateTime(intDiv(<from_ms>,1000)) AND col <= toDateTime(intDiv(<to_ms>,1000))`；`${topn}` 等 → 直接替换为值
- Python urllib 对 `/api/ds/query` 的 POST 正常（只有 `/api/dashboards/db` 被代理拦）

## 已验证的业务表（ClickHouse）

- `***REMOVED***`：计费明细。关键字段 `user_id, ***REMOVED***, input_tokens, output_tokens, ***REMOVED***, ***REMOVED***, created_at, ***REMOVED***, status`
- `***REMOVED***`：用户字典，`id = ***REMOVED***.user_id`，`***REMOVED***`（客户名）、`email`
- 计费口径：`***REMOVED*** = 'personal' AND status = 'success'`，金额字段 `***REMOVED***`
- ClickHouse 支持 `row_number() OVER (...)` 窗口函数（做"其他"合并扇区时用到）

## 已踩坑清单（勿重复）

1. **urllib POST /api/dashboards/db → 502**：前置代理拦截 Python urllib 的写操作（带 UA 也无效；GET 正常）。解决：curl `--data-binary @file`，或 Python subprocess 调 curl。
2. **饼图 values=false → 渲染错误**：整列被聚成单值。必须 `reduceOptions.values=true`。
3. **扇区标签溢出**：displayLabels 含 name/percent 等长文字会出框。置空 `[]`，信息放图例表格。
4. **横向条形图 ASC LIMIT N = 最小 N 条**：如做条形图需子查询 `ORDER BY x DESC LIMIT ${topn}` 外层再 `ORDER BY x ASC`。
5. **`/render` 截图服务故障**：任何仪表板都返回同一张 固定大小占位 PNG，不能用于视觉验证。
6. **占比口径**：饼图百分比按展示数据（TOP N）内部合计计算；若用户在意"占总盘子"，需说明并确认是否加"其他"合并扇区（默认不加）。

## 标准仪表板命名约定

- 标题：`运营-<主题>`；tags：`***REMOVED***` + `billing`（账单类）
- 默认时间：`now/M` → `now`；快捷范围：今天/近7天/本月/上月/近30天
- 表格样式：tokens 列 unit=short，金额列 decimals=4，按金额降序；客户名列可挂下钻链接 `/d/<旧板uid>?var-user=${__value.text:percentencode}&${__url_time_range}`
