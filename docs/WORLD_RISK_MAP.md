# Zeus World Risk Map 设计与执行计划

> 版本: 0.6 | 日期: 2026-05-10 | 状态: Phase C.4 NOAA 站点映射、AccuWeather 当前天气展示与限额保护已完成

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

- Open-Meteo：天气预报与历史天气原型，已接入 `weather_precip_7d`、`weather_temp_max_7d`、`weather_temp_min_7d` 采集。
- NASA POWER：农业和气象历史日频数据，已接入日频 point API 客户端，可作为后续历史 baseline 的来源。
- NOAA CDO：更正式的历史气象补充。

计算层：

- 历史均值 baseline：按区域、商品、季节窗口聚合。当前阶段如缺少历史行，会显式回退 `regional_baseline_seed`。
- 当前异常：降水距平、温度距平、干旱/洪涝评分。
- 输出 `weather_anomaly_score`，进入区域综合风险。

Phase C.1 已完成：

- Open-Meteo base URL 配置化，默认天气地点扩展到橡胶、原油、黑色、农产和农能区域。
- 新增 NASA POWER daily point 客户端，输出与 Open-Meteo 一致的天气行业数据行，便于统一入库。
- `/api/world-map` 会优先使用 `industry_data` 中最新天气行更新区域天气、风险故事和天气 tile 来源；没有真实天气行时保留 seed baseline。
- `dataQuality=partial` 表示该区域已有天气运行态数据，但尚未出现预警/新闻/信号/持仓直接联动。

Phase C.2 已完成：

- NASA POWER baseline 采集支持同一日历窗口的多年度历史均值，输出 `weather_baseline_precip_7d` 与 `weather_baseline_temp_mean_7d`。
- baseline 采集独立开关 `DATA_SOURCE_NASA_POWER_BASELINE_ENABLED`，避免高频调度任务每天重复拉取大窗口历史数据。
- 世界地图天气融合优先使用站点 `region_id` 做作用域匹配，避免 M/Y/SC 等跨区域商品把其它地区天气误算进当前区域。
- 同一区域多站点会按来源站点聚合均值，不再因为商品代码相同只保留最新一条天气行。

Phase C.3 已完成：

- NASA POWER baseline 增加 `weather_precip_pctile_7d` 与 `weather_temp_pctile_7d`，让地图能表达当前天气处在历史分布的哪个位置。
- 世界地图天气风险融合新增分位数加权，极端高分位降水更偏洪涝，极端低分位降水更偏干旱。
- 新增低频 `weather-baseline` 调度任务，默认关闭，可按周运行，避免高频行情 ingest 重复拉取历史窗口。
- NOAA CDO 与 AccuWeather 配置和状态入口已加入；NOAA 需要 token，AccuWeather 用作近实时天气补充，不替代 NASA POWER 历史 baseline。

Phase C.4 已完成：

- NOAA CDO 增加站点映射：按区域经纬度搜索附近 GHCND 站点，再拉取近 7 日 PRCP/TMAX/TMIN，写入统一的 `industry_data` 天气行。
- NOAA 和 AccuWeather 均增加每轮地点数量上限，默认小批量运行，避免本地开发或手动刷新时消耗过多免费额度。
- AccuWeather 当前天气指标进入 World Risk Map：当前气温、1 小时降水、湿度、风速只在真实数据存在时展示，并与 baseline / NASA 历史异常分层共存。
- 世界地图天气源继续走统一融合层：缺少 7 日降水时当前天气只提升可读性和数据质量，不伪装为完整历史异常。

### Phase D：增强渲染路线（3D 暂缓）

当前不继续推进 3D Globe。世界风险地图后续优先做 2D / WebGL 信息阅读和事件组织能力：

- MapLibre / deck.gl 的天气栅格和风险瓦片性能优化。
- 更清晰的毛玻璃浮层、卡片紧凑/展开策略和地图标签避让。
- 数据源可信度、新鲜度、证据密度可视化。
- 与 Event Intelligence Engine 共用 `event_id + symbols + regions + mechanisms` 作用域。

3D 方案保留为远期探索项，不作为当前开发优先级。

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
    - `precipitationPercentile` / `temperaturePercentile`：可选，来自历史窗口分位数。
    - `currentTemperatureC` / `precipitation1hMm` / `humidityPct` / `windKph`：可选，来自 AccuWeather 等当前天气源。
  - `runtime`
  - `causalScope`
  - `dataQuality`

`GET /api/world-map/tiles?layer=all|weather|risk&resolution=coarse|medium`

返回：

- `generatedAt`
- `resolution`
- `layer`
- `summary`
  - `weatherCells`
  - `riskCells`
  - `maxIntensity`
  - `dataSources`
- `cells[]`
  - `id`
  - `layer`：`weather` 或 `risk`
  - `regionId`
  - `center`
  - `polygon`：经纬度 tile 多边形，由前端投影到当前地图坐标
  - `metric`：`precipitation_anomaly_pct` / `flood_risk` / `drought_risk` / `composite_risk`
  - `value`
  - `intensity`
  - `riskLevel`
  - `dataQuality`
  - `source`

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
- [x] Phase B.2.1 WebGL 图层准备层：区域风险、天气异常和风险等级预聚合为密度网格，可映射到 deck.gl HeatmapLayer / TileLayer。
- [x] Phase B.2.2 渲染模式护栏：新增轻量/增强模式切换和 WebGL 图层准备面板，为 MapLibre/deck.gl 接入保留回退路径。
- [x] Phase B.2.3 deck.gl 预览层：安装 MapLibre/deck.gl 构建链路，并在增强模式中叠加 Polygon/Scatterplot/Arc WebGL 预览层。
- [x] Phase B.2.4 MapLibre 离线底图壳层：增强模式动态初始化 MapLibre，加载本地国家边界和风险区域 GeoJSON，无外部瓦片依赖。
- [x] Phase B.2.5 WebGL 视图同步：MapLibre/deck.gl 增强层进入 SVG viewBox 坐标系，共享地图拖拽和缩放变换。
- [x] Phase B.2.6 增强层图层联动：MapLibre/deck.gl 增强层跟随现有热力、密度、飞线开关的可见状态。
- [x] Phase B.2.7 增强模式阅读层：基于当前筛选区域生成主读区、跨区传导、证据密度和联动区域摘要，让增强模式服务信息阅读。
- [x] Phase B.2.8 天气瓦片预览层：基于区域降水距平、洪涝和干旱风险生成 deck.gl tile-like 天气栅格，并跟随天气图层开关联动。
- [x] Phase B.2.9 天气/风险瓦片后端契约：新增 `/api/world-map/tiles`，前端增强层优先使用后端 tile 数据，并保留本地生成回退。
- [x] Phase B.2.10 视口瓦片裁剪：`/api/world-map/tiles` 支持 `min_lat/max_lat/min_lon/max_lon`，前端缩放/拖拽后按当前可视范围刷新瓦片，放大时自动切换 medium resolution。
- [ ] Phase B.2 MapLibre + deck.gl：天气栅格、瓦片热力和超大数据量增强。
- [x] Phase C.1 Open-Meteo / NASA POWER 客户端与 World Map 天气融合。
- [x] Phase C.2 NASA POWER 历史季节 baseline 与区域作用域融合。
- [x] Phase C.3 异常分位数、NOAA/AccuWeather 配置入口与 baseline 调度降频策略。
- [x] Phase C.4 NOAA CDO station mapping、AccuWeather 当前天气 UI 深化与请求限额保护。
- [x] Phase D.1 证据健康阅读层：区域返回 `evidenceHealth`，展示证据密度、来源可信度、数据新鲜度、支持证据和反证覆盖。
- [x] Phase D.2 风险动量阅读层：区域返回 `riskMomentum`，首屏展示升温 / 降温 / 稳定、动量原因和地图脉冲。
- [ ] Phase D 2D / WebGL 信息阅读增强，3D Globe 暂缓。
- [ ] Phase E Event Intelligence Engine 联动：事件源筛选、商品影响机制和证据/反证链。

## 6. 审查优化接续

World Risk Map 首版完成后，继续纳入此前一轮一轮的代码质量审查和性能优化计划。重点新增审查项：

- 地理区域与事件/信号/持仓关联是否真实可追溯。
- 天气 baseline 是否明确标注数据来源和时间窗口。
- 大量区域/事件下的地图渲染性能。
- 与 Causal Web 作用域传递的一致性。
