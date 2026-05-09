# Zeus World Risk Map 设计与执行计划

> 版本: 0.2 | 日期: 2026-05-08 | 状态: Phase B 已完成，Phase B.2 待规划

## 1. 产品定位

World Risk Map 是 Zeus 的地理风险工作台，用来把预警、新闻事件、天气异常、产区暴露、持仓暴露和因果链路放到同一个空间视图中观察。

它与现有视图的关系：

- **Command Center**：全局运行态与任务入口。
- **Causal Web**：解释事件之间的因果传导。
- **World Risk Map**：解释风险发生在哪里、影响哪个商品、是否已经传导到信号/预警/持仓。

核心使用场景：

- 橡胶：东南亚/海南/云南降水异常、洪涝、割胶节奏、NR/RU 价差传导。
- 原油：中东、俄罗斯、美国页岩油、航运节点和 SC 传导。
- 黑色：澳洲铁矿、华北钢材、焦煤焦炭链路。
- 农产：巴西/美国降水、干旱、物流和出口节奏。

## 2. 交互原则

- 默认显示风险最高的区域，不把世界地图做成装饰背景。
- 地图点击后必须展示来源：预警数、新闻数、信号数、持仓数、天气数据质量。
- 与 Causal Web 联动采用统一作用域：`region_id + symbols + event_ids + time_window`。
- 没有直接关联时明确显示“暂无直接因果联动”，避免模拟关系造成误解。
- 3D 是增强模式，不作为首版默认阅读模式。

## 3. 技术方案

### Phase A：自包含 2.5D 风险地图

当前阶段不引入重型地图依赖，先用 React + SVG + 后端运行态聚合接口完成产品闭环：

- 新增 `/api/world-map`：返回区域风险快照。
- 新增 `/world-map` 页面：世界风险地图、区域热力、右侧详情、Causal Web 跳转。
- 区域配置为可维护静态定义，运行态风险由 `alerts` / `news_events` / `signal_track` / `positions` 聚合。
- 天气字段先标记为 `regional_baseline_seed`，不伪装为实时天气。

### Phase B：真实世界地图层

在 Phase A 数据契约稳定后，先落地无 token、可离线构建的真实世界地图层：

- `world-atlas`：Natural Earth 110m 世界国家边界。
- `topojson-client`：TopoJSON 转 GeoJSON feature / border mesh。
- `d3-geo`：Equal Earth 投影，保持全球视图可读性。
- 风险区域 polygon、热力圈、区域标签和同商品/同合约风险飞线都基于经纬度投影，不再使用手写大陆轮廓。

### Phase B.1：轻动态与轻量地图交互

在不引入 WebGL 的前提下，让默认视图具备运行态动态感：

- 前端每 30 秒自动轮询 `/api/world-map`，保留手动刷新开关。
- 区域风险变化用闪环和 delta 标记呈现，避免用户误以为地图是一次性静态图。
- 同商品/同合约风险飞线增加流动动画，用于表达跨区域联动。
- SVG 视图支持鼠标滚轮缩放、拖拽平移、按钮缩放和一键重置；资源占用仍保持在轻量 SVG 层。

后续如果需要天气栅格、瓦片级热力、地形和超大数据量，再引入：

- MapLibre GL JS：底图、globe、terrain、heatmap 基础能力。
- deck.gl：`GeoJsonLayer`、`HeatmapLayer`、`ArcLayer`、`ScatterplotLayer`、`TileLayer`。
- 后端增加区域 polygon、时间序列风险瓦片、天气栅格聚合接口。

### Phase C：天气与历史异常数据

优先接入免费/公开源：

- Open-Meteo：天气预报与历史天气原型。
- NASA POWER：农业和气象历史日频数据。
- NOAA CDO：更正式的历史气象补充。

计算层：

- 历史均值 baseline：按区域、商品、季节窗口聚合。
- 当前异常：降水距平、温度距平、风速、干旱/洪涝评分。
- 输出 `weather_anomaly_score`，进入区域综合风险。

### Phase D：3D Globe 增强

采用 three.js / React Three Fiber 做增强模式：

- 全球风险脉冲。
- 商品链路飞线。
- 区域预警波纹。
- 时间轴回放。

默认仍保留 2.5D 运行态视图，3D 作为 “Globe Mode”。

## 4. 后端数据契约

`GET /api/world-map`

返回：

- `generated_at`
- `summary`
  - `regions`
  - `elevated_regions`
  - `max_risk_score`
  - `runtime_linked_regions`
- `layers`
  - weather
  - alerts
  - causal
  - positions
- `regions[]`
  - `id`
  - `nameZh` / `nameEn`
  - `commodity`
  - `symbols`
  - `center`
  - `polygon`
  - `riskScore`
  - `riskLevel`
  - `drivers`
  - `story`
    - `headlineZh` / `headlineEn`
    - `triggerZh` / `triggerEn`
    - `chain[]`：按商品属性生成的风险传导步骤，例如天气 → 生产/物流 → 供应/库存 → 价格。
    - `evidence[]`：天气、预警、新闻、信号、持仓或基线证据。
    - `counterEvidence[]`：该链路的反证提示，避免单向叙事。
  - `adaptiveAlerts[]`：由运行态证据和商品镜头生成的动态预警，不写死为固定文案。
  - `weather`
  - `runtime`
  - `causalScope`
  - `dataQuality`

## 4.1 商品自适应风险故事

World Risk Map v2 不再把所有商品套入同一套固定解释，而是引入 **Commodity Lens**：

- 橡胶：降水、厄尔尼诺、割胶天数、原料供应、NR/RU 价差。
- 原油：供应扰动、航运节点、制裁/配额、库存缓冲、SC 风险溢价。
- 黑色：矿山/港口/汽运、炉料成本、钢厂开工、成材利润。
- 农产：降水/干旱、单产、收割/出口节奏、油粕压榨和需求。
- 农能联动：能源成本、生柴需求、农产与能源替代关系。

同一因素会根据商品属性生成不同传导链。例如“洪涝”：

- 橡胶：洪涝 → 割胶窗口收缩 → 原料供应不稳 → NR/RU 支撑。
- 黑色：洪涝 → 港口/矿山/运输受扰 → 发运和库存错配 → 炉料/成材价差波动。
- 农产：洪涝 → 播种/收割和内陆运输放慢 → 出口节奏后移 → 油粕基差波动。

## 5. 执行清单

- [x] 文档设计：产品定位、技术路径、数据契约。
- [x] Phase A 后端接口：运行态聚合 + 区域风险评分。
- [x] Phase A 前端页面：2.5D 地图 + 区域详情 + Causal Web 跳转。
- [x] 导航/命令面板/i18n 同步。
- [x] Phase A.2 商品自适应风险故事：动态预警、证据/反证、点击弹窗。
- [x] Phase B 真实世界地图层：Natural Earth 边界、Equal Earth 投影、地理风险飞线。
- [x] Phase B.1 轻动态交互：自动轮询、风险变化动画、缩放拖拽和重置视图。
- [x] Phase B.1.1 沉浸式 HUD：地图全画布占比提升，标题/统计/筛选/控制转为浮动玻璃态操作层。
- [x] Phase B.1.2 区域情报抽屉：区域详情右侧/底部抽屉化，保持地图上下文并优化传导链阅读。
- [x] Phase B.1.3 可控风险图层：天气、热力、飞线、标签可独立开关，轻量天气 halo 先行验证图层交互。
- [x] Phase B.1.4 区域风险索引与聚焦：高风险区域索引按筛选排序，点击后打开情报抽屉并自动聚焦地图。
- [ ] Phase B.2 MapLibre + deck.gl：天气栅格、瓦片热力和超大数据量增强。
- [ ] Phase C 接入 Open-Meteo / NASA POWER。
- [ ] Phase D 3D Globe 增强。

## 6. 审查优化接续

World Risk Map 首版完成后，继续纳入此前一轮一轮的代码质量审查和性能优化计划。重点新增审查项：

- 地理区域与事件/信号/持仓关联是否真实可追溯。
- 天气 baseline 是否明确标注数据来源和时间窗口。
- 大量区域/事件下的地图渲染性能。
- 与 Causal Web 作用域传递的一致性。
