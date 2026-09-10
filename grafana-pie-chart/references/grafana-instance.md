# Grafana 实例接入参考（饼图相关）

> 本文件只固化**通用 API 行为与接入约定**。实例特定的地址、凭据、表结构、业务口径一律用尖括号占位符表示，运行时从用户处获取，禁止写入 skill 落盘。

## 实例信息（占位符约定）

| 项 | 占位符 | 获取方式 |
|----|--------|---------|
| 地址 | `http://<grafana-host>[:<port>]` | 用户提供，内网地址不落盘 |
| 认证 | 环境变量 `GRAFANA_AUTH`（格式 `user:password`） | 用户在 shell 中 export；勿明文写入任何文件 |
| 数据源 | ClickHouse 插件 `{"type": "grafana-clickhouse-datasource", "uid": "<ds-uid>"}` | 从用户或 `GET /api/dashboards/uid/<uid>` 回读确认 |
| 业务表 | `<schema>.<fact_table>`（事实表）、`<schema>.<dim_table>`（维度表） | 用户提供或查库确认，skill 不预设表名 |

以下 API 行为按 Grafana 通用 REST 语义描述，不绑定具体版本号；若实例版本较旧，先 `GET /api/health` 探测再操作。

## 核心 API

| 操作 | 方法与路径 | 说明 |
|------|-----------|------|
| 健康检查 | `GET /api/health` | 通常匿名可用 |
| 列仪表板 | `GET /api/search?query=` | 需 Basic Auth |
| 读仪表板 | `GET /api/dashboards/uid/{uid}` | 含面板 SQL/变量/样式，改动前先备份 |
| 测试查询 | `POST /api/ds/query` | 见下方请求体 |
| 建板/更新 | `POST /api/dashboards/db` | **只能 curl 提交**，payload `{"dashboard": {...}, "folderId": 0, "overwrite": true, "message": "..."}` |

## /api/ds/query 请求体

```json
{
  "queries": [{
    "refId": "A",
    "datasource": {"type": "grafana-clickhouse-datasource", "uid": "<ds-uid>"},
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

## 业务表与口径（每次由用户提供，不固化）

- 事实表/维度表表名、字段、关联键：首次使用时向用户确认，全部以占位符进入 SQL
- 统计口径（状态过滤、来源过滤等业务条件）：**必须由用户明确确认后填入**，skill 不预置任何业务口径
- ClickHouse 支持 `row_number() OVER (...)` 窗口函数（做"其他"合并扇区时用到）

## 已踩坑清单（Grafana/饼图通用，勿重复）

1. **饼图 values=false → 渲染错误**：整列被聚成单值。必须 `reduceOptions.values=true`。
2. **扇区标签溢出**：displayLabels 含 name/percent 等长文字会出框。置空 `[]`，信息放图例表格。
3. **横向条形图 ASC LIMIT N = 最小 N 条**：如做条形图需子查询 `ORDER BY x DESC LIMIT ${topn}` 外层再 `ORDER BY x ASC`。
4. **占比口径**：饼图百分比按展示数据（TOP N）内部合计计算；若用户在意"占总盘子"，需说明并确认是否加"其他"合并扇区（默认不加）。

## 环境相关限制（按需验证，不预设）

- **写操作提交方式**：首选 curl `--data-binary @file`。部分环境的**前置代理会拦截 Python urllib 的 POST**（GET 正常、带 UA 也无效、返回 502）；遇此现象时改用 curl 或 Python subprocess 调 curl。
- **视觉验证**：`/render` 截图服务在部分环境不可用（任何仪表板都返回同一张固定占位 PNG）。不要依赖截图做验证，统一以 `GET` 回读 JSON 数据验证代替。

## 仪表板命名约定

- 标题：`<业务前缀>-<主题>`；tags：`<团队标签>` + `<业务标签>`（由用户或既有仪表板惯例确定）
- 默认时间：`now/M` → `now`；快捷范围：今天/近7天/本月/上月/近30天
- 表格样式：数值列 unit=short，金额列 decimals=4，按金额降序；标签列可挂下钻链接 `/d/<drilldown-uid>?var-<var>=${__value.text:percentencode}&${__url_time_range}`
