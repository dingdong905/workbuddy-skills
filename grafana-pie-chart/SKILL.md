---
name: grafana-pie-chart
description: 在 Grafana 中创建/修改饼图（piechart）面板的标准化流程，基于 ClickHouse SQL 数据源。适用于"画饼图 / 做占比图 / TOP N 饼图 / 改饼图"等需求。固化了数据映射（values=true）、扇区无文字、图例表格、SQL TOP N 等已踩坑验证的硬性约束，以及该 Grafana 实例的 API 提交方式与代理限制。
agent_created: true
---

# Grafana 饼图绘制规范

## 概述

按本规范在 Grafana（ClickHouse 数据源）上制作饼图面板。规范来自实际踩坑验证（v6 定稿），核心是三条硬性约束：**数据映射必须 `values=true`、扇区不显示文字、信息全部放右侧图例表格**。

## 触发场景

- 用户要求"画个饼图 / 占比图 / 分布图"
- 在 Grafana 仪表板上新增 piechart 面板
- 修改现有饼图的样式、数据、占比口径
- 制作"TOP N 占比"类面板（如客户月账单 TOP 10）

## 硬性约束（必须遵守）

1. **数据映射**：`options.reduceOptions` 必须为 `{"calcs": ["lastNotNull"], "fields": "", "values": true}`。
   - `values: true` = 每行数据一个扇区（字符串列自动作扇区标签）。
   - `values: false` 会把整列数值聚成单值，饼图渲染错误——这是最常见错误。

2. **扇区文字**：`options.displayLabels` 必须为 `[]`（空数组）。
   - 扇区上显示"名称+百分比"等长文字会溢出面板边框。
   - 所有信息放右侧图例：`{"displayMode": "table", "placement": "right", "showLegend": true, "values": ["value", "percent"]}`。

3. **SQL 形态**：恰好两列——第一列字符串（标签），第二列数值（扇区大小）；TOP N 用 `ORDER BY <数值列> DESC LIMIT ${topn}`，最大值排第一（Grafana 按数据顺序顺时针渲染）。

4. **不加"其他/Others"合并扇区**：默认纯 TOP N。百分比按 TOP N 内部合计计算（合计恒为 100%）。若业务上需要"占总盘子比例"，必须先向用户说明口径差异并确认后再加（用 `row_number() OVER` 取 rk > N 求和 UNION ALL）。

5. **不改动既有仪表板**：参考现有仪表板只做只读查询（GET）；新建用独立 uid，除非用户明确要求修改旧板。

## 标准面板 JSON 模板

从 `assets/pie-panel-v6.json` 复制完整面板定义，仅需替换：标题、gridPos、id、targets 中的 rawSql、以及需要保留下钻时的 links。模板与当前线上版本（***REMOVED*** v6）完全一致。

## 工作流程

### 1. 测试 SQL（提交前必做）

通过 `POST /api/ds/query` 验证数据，手工替换 Grafana 宏：

- `$__timeFilter(col)` → `col >= toDateTime(intDiv(<from_ms>,1000)) AND col <= toDateTime(intDiv(<to_ms>,1000))`
- `${var}` → 实际值（如 topn=10）

ClickHouse target 结构：`{"datasource": {"type": "grafana-clickhouse-datasource", "uid": "clickhouse"}, "format": 1, "queryType": "sql", "rawSql": "..."}`。响应在 `results.A.frames[0].data.values`（列优先数组）。详细 API 说明见 `references/grafana-instance.md`。

### 2. 组装并提交仪表板

- payload：`{"dashboard": {..., "uid": "<新uid>", "version": 0}, "folderId": 0, "overwrite": true}`
- **必须用 curl 提交**：`curl -u <auth> -X POST -H "Content-Type: application/json" --data-binary @<file>.json http://<grafana>/api/dashboards/db`
- **禁止用 Python urllib POST**：该实例前置代理会拦截（即使带 User-Agent 也返回 502；GET 不受影响）。Python 脚本内用 subprocess 调 curl。

### 3. 回读验证

`GET /api/dashboards/uid/<uid>` 确认：饼图面板存在、`reduceOptions.values=true`、`displayLabels=[]`、SQL 正确。

## 注意事项

- 该实例 `/render` 截图服务故障（返回固定占位图），不要用它做视觉验证，以数据验证代替。
- 凭据不落盘：脚本中从环境变量 `GRAFANA_AUTH`（格式 `user:password`）读取。
- 凭据、实例地址等环境细节见 `references/grafana-instance.md`。
- 改动已有面板时，改动前先 GET 保存本地备份 JSON。
