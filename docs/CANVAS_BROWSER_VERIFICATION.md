# 大画布浏览器验证流程

本流程用于每次改动 Causal Web 或 World Risk Map 后做轻量回归，重点检查大画布页面不会空白、不会被浮层遮挡、缩放拖拽后仍可读。

## 1. 启动与基础 Smoke

```bash
scripts/local_smoke.sh --start
```

如果只需要复测已启动环境：

```bash
scripts/local_smoke.sh
```

通过标准：

- Postgres、Redis、backend、frontend compose service healthy。
- `http://localhost:8000/api/health` 返回 OK。
- `http://localhost:3000` 和 `http://localhost:3000/world-map` 可访问。

## 2. World Risk Map 回归点

打开 `http://localhost:3000/world-map`，按以下顺序检查：

- 首屏地图占主要面积，标题卡、筛选、图层、刷新控件不遮挡核心区域。
- 筛选面板默认折叠；点击“筛选”后弹出玻璃态面板，事件源、品种、机制三组可操作，关闭后地图恢复完整阅读面积。
- 点击“增强”后页面不出现右侧冗余状态卡；MapLibre / deck.gl 预览层不抢占指针事件。
- 点击“地图标签”开关可隐藏或恢复标签；缩放到 150% 左右时标签保持固定屏幕尺寸，不随地图放大失控。
- 点击高风险索引或地图区域后，区域情报档案出现在所有地图控件之上；按 Escape 或关闭按钮可以返回地图。
- 刷新和自动轮询时地图不闪白，旧瓦片请求不会覆盖当前视口。

## 3. Causal Web 回归点

打开 `http://localhost:3000/causal-web`，按以下顺序检查：

- 命令中心预览和独立页面都能显示图谱，不出现空白画布。
- 事件池默认只显示优先级最高事件；筛选“持仓 / 反证 / 预警追踪”时，无直接关联会显示事件源作用域空态。
- 节点 hover 不闪烁、不出现光标重影；点击节点后详情卡不被画布边界或底部状态栏遮挡。
- 深链参数 `event / symbol / region / source` 从新闻、事件智能、世界风险地图跳转后仍保留作用域提示。

## 4. 截图留档建议

在视觉大改或发布前，保留以下截图到 `docs/design-references/regression/`：

- `world-map-light-desktop.png`
- `world-map-enhanced-desktop.png`
- `world-map-filter-open.png`
- `world-map-region-modal.png`
- `causal-web-desktop.png`

截图只作为人工视觉回归基线，不进入生产逻辑。
