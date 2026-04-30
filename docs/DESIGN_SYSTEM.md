# Zeus 设计系统

> 版本: 1.0 | 日期: 2026-04-30 | 状态: 已敲定

## 0. 北极星

**让用户用起来很爽 — 通过密切的人机交互制造"系统在为我活过来"的感觉。**

这不是功能目标，是体验目标。每个设计决策都要回到这个标准：这个改动让用户更"爽"了吗？让人和系统的关系更密切了吗？如果答案是否定的，砍掉。

---

## 1. 设计哲学

### 原则 1：克制的视觉，密集的信息
留白慷慨（Notion 风），但每一寸像素都在传递信息。**80% 的页面只用三种颜色：黑底 + 灰阶 + 一种品牌色**。当第二种颜色出现，必然是为了"需要你注意"。

### 原则 2：系统是活的
通过微动效、状态编排、心跳指示器，让系统永远显得"在思考、在工作、在等你回来"。每个动作有完成感，每个状态有过渡感。

### 原则 3：人机协作，不是单向告知
所有界面都为"对话"留位置：你可以反馈、可以标注、可以追问 AI Companion、可以追溯系统的推理过程。Zeus 不是仪表盘，是研究伙伴。

---

## 2. 设计 Tokens

### 2.1 色彩

#### 背景层级（黑色调灰阶分层，不靠边框分层）

| Token | 值 | 用途 |
|-------|-----|-----|
| `bg-base` | `#000000` | 页面最底层 |
| `bg-surface` | `#0A0A0A` | 一级卡片、主要内容容器 |
| `bg-surface-raised` | `#141414` | 卡片中的卡片、hover 浮起 |
| `bg-surface-overlay` | `#1F1F1F` | Modal、Drawer、Popover |
| `bg-surface-highlight` | `#292929` | 选中、激活状态 |

#### 文字层级

| Token | 值 | 用途 |
|-------|-----|-----|
| `text-primary` | `#FFFFFF` | 主标题、关键数据 |
| `text-secondary` | `#A3A3A3` | 正文、次要信息 |
| `text-muted` | `#737373` | 辅助说明、标签 |
| `text-disabled` | `#404040` | 禁用状态 |

#### 边框

| Token | 值 | 用途 |
|-------|-----|-----|
| `border-subtle` | `#1A1A1A` | 极轻分隔（表格行间） |
| `border-default` | `#262626` | 卡片边框、输入框 |
| `border-strong` | `#404040` | 强调分隔 |

#### 品牌色（双色系统）

| Token | 值 | 用途 |
|-------|-----|-----|
| `brand-emerald` | `#059669` | **品牌主色**：导航、Logo、Tab、链接、主按钮、品牌标识 |
| `brand-emerald-hover` | `#047857` | 主按钮 hover |
| `brand-emerald-muted` | `rgba(5, 150, 105, 0.12)` | 选中态背景、轻量徽章 |
| `brand-orange` | `#F97316` | **行动色**：CTA 按钮、关键数据高亮、Causal Web 信号粒子、信号触发提示 |
| `brand-orange-hover` | `#EA580C` | 行动按钮 hover |
| `brand-orange-muted` | `rgba(249, 115, 22, 0.12)` | 行动徽章背景 |

**关键规则**：品牌绿和品牌橙**不能同时出现在同一区域**。绿色 = "Zeus 在这里"（结构性元素），橙色 = "需要你看这里"（事件性元素）。如果一个区域两者都出现，重新审视设计。

#### 数据语义色（涨跌损益）

| Token | 值 | 用途 |
|-------|-----|-----|
| `data-up` | `#10B981` (emerald-500) | 价格上涨、正收益 |
| `data-down` | `#EF4444` (red-500) | 价格下跌、负收益 |
| `data-flat` | `#A3A3A3` | 持平 |

涨色和品牌绿是**同色系不同明度**，保留品牌一致性，但因为出现上下文从不重叠（品牌绿在导航、涨色在数据），不会混淆。

#### 严重度色阶（预警分级）

预警色用**低饱和背景 + 高饱和文字**的方案，避免和品牌色竞争注意力：

| 级别 | 文字色 | 背景色 |
|------|-------|-------|
| `severity-critical` | `#FCA5A5` | `rgba(239, 68, 68, 0.12)` |
| `severity-high` | `#FCD34D` | `rgba(245, 158, 11, 0.12)` |
| `severity-medium` | `#FDE68A` | `rgba(234, 179, 8, 0.10)` |
| `severity-low` | `#86EFAC` | `rgba(34, 197, 94, 0.10)` |

#### 图表色板（5 色，黑底辨识度优化）

按使用频次排序：

| 序号 | Token | 值 |
|------|-------|-----|
| 1 | `chart-1` | `#10B981` (emerald) |
| 2 | `chart-2` | `#F97316` (orange) |
| 3 | `chart-3` | `#38BDF8` (sky-400) |
| 4 | `chart-4` | `#C084FC` (purple-400) |
| 5 | `chart-5` | `#FB7185` (rose-400) |

超过 5 条线时用同色不同明度区分（80% / 60% / 40% / 20% 透明度），不引入新色相。

#### 状态色

| Token | 值 | 用途 |
|-------|-----|-----|
| `status-success` | `#10B981` | 成功、健康、通过 |
| `status-warning` | `#F59E0B` | 警告、注意 |
| `status-error` | `#EF4444` | 错误、失败 |
| `status-info` | `#38BDF8` | 信息、提示 |

### 2.2 字体

| 角色 | 字体栈 | 用途 |
|------|-------|-----|
| Sans | `Inter, "PingFang SC", "HarmonyOS Sans", -apple-system, sans-serif` | 标题、正文、UI |
| Mono | `"JetBrains Mono", "IBM Plex Mono", "SF Mono", monospace` | 数字、代码、品种代码 |

**字号阶梯**：

| Token | 值 | 用途 |
|-------|-----|-----|
| `text-display` | `32px / 1.2 / 700` | Hero 数据（如组合 P&L） |
| `text-h1` | `24px / 1.3 / 600` | 页面标题 |
| `text-h2` | `20px / 1.3 / 600` | 区块标题 |
| `text-h3` | `16px / 1.4 / 600` | 卡片标题 |
| `text-body` | `14px / 1.5 / 400` | 正文（默认） |
| `text-sm` | `13px / 1.4 / 400` | 表格、密集列表 |
| `text-xs` | `12px / 1.4 / 500` | 标签、辅助说明 |
| `text-caption` | `11px / 1.3 / 500` | 微标签、时间戳 |

**字重**：400（regular） / 500（medium） / 600（semibold） / 700（bold）—— 不用 300 或 800。

**数字规范**：所有数字用 `Mono` 字体 + `tabular-nums` + `font-feature-settings: "tnum"`。小数点必须对齐。负数前置 `-`，不要括号。

### 2.3 间距

基准单位 8px，不跨步使用。

| Token | 值 | 典型用途 |
|-------|-----|---------|
| `space-1` | `4px` | 紧密元素之间（icon + 文字） |
| `space-2` | `8px` | 卡片内部小间距 |
| `space-3` | `12px` | 表格行内边距 |
| `space-4` | `16px` | 卡片标准 padding |
| `space-5` | `24px` | 区块之间 |
| `space-6` | `32px` | 主要分区 |
| `space-8` | `48px` | 页面级分区 |
| `space-10` | `64px` | 仅用于 Notion 风的留白页面 |

**留白原则**：研究类页面（Dashboard / Causal Web / Notebook）用 24-48px 留白；数据类页面（Alerts / Positions）用 16-24px。

### 2.4 圆角

| Token | 值 | 用途 |
|-------|-----|-----|
| `radius-xs` | `2px` | 徽章、标签 |
| `radius-sm` | `4px` | **默认**（按钮、卡片、输入框） |
| `radius-md` | `6px` | 大卡片 |
| `radius-lg` | `8px` | Hero 卡片（少用） |
| `radius-full` | `9999px` | 圆形头像、圆形指示器 |

### 2.5 阴影

黑底主题，阴影靠**亮度提升 + 极淡发光**实现：

| Token | 值 | 用途 |
|-------|-----|-----|
| `shadow-sm` | `0 1px 2px rgba(0,0,0,0.5)` | 卡片浮起 |
| `shadow-md` | `0 4px 12px rgba(0,0,0,0.6)` | Modal、Popover |
| `shadow-lg` | `0 8px 24px rgba(0,0,0,0.7)` | Drawer |
| `shadow-glow-emerald` | `0 0 16px rgba(16, 185, 129, 0.35)` | 健康状态指示、品牌强调 |
| `shadow-glow-orange` | `0 0 20px rgba(249, 115, 22, 0.45)` | 关键预警激活、信号脉冲 |
| `shadow-glow-red` | `0 0 16px rgba(239, 68, 68, 0.4)` | Critical 预警 |

发光效果是 Zeus 的视觉签名——在关键时刻（预警、信号触发、新假设产生）使用，平时不滥用。

### 2.6 动效

#### 时长

| Token | 值 | 用例 |
|-------|-----|-----|
| `duration-fast` | `100ms` | Hover 反馈、微调 |
| `duration-base` | `200ms` | 状态切换、按钮 |
| `duration-slow` | `400ms` | Panel 滑入滑出 |
| `duration-deliberate` | `800ms` | Boot Sequence、重大状态变化 |

#### 缓动函数

| Token | 值 | 用例 |
|-------|-----|-----|
| `ease-standard` | `cubic-bezier(0.4, 0, 0.2, 1)` | 默认（90% 场景） |
| `ease-accelerate` | `cubic-bezier(0.4, 0, 1, 1)` | 元素离开屏幕 |
| `ease-decelerate` | `cubic-bezier(0, 0, 0.2, 1)` | 元素进入屏幕 |
| `ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | 趣味性元素（Causal Web 节点激活、成就时刻） |

---

## 3. 核心组件规范

### 3.1 Button（按钮）

**变体**：

| 变体 | 视觉 | 用途 |
|------|------|------|
| `primary` | `bg-brand-emerald` + 白字 | 主要操作（保存、确认） |
| `action` | `bg-brand-orange` + 白字 | 高重要度行动（执行交易、触发推演） |
| `secondary` | `border-default` 透明底 + 白字 | 次要操作 |
| `ghost` | 无边框 + `text-secondary`，hover 时浅灰底 | 表格内、紧凑场景 |
| `destructive` | `bg-status-error` + 白字 | 删除、撤销 |

**尺寸**：

| 尺寸 | 高度 | padding | 字号 |
|------|------|---------|------|
| `sm` | 28px | `0 12px` | `text-xs` |
| `md`（默认） | 36px | `0 16px` | `text-body` |
| `lg` | 44px | `0 24px` | `text-h3` |

**状态**：
- 默认 / hover（亮度 +10%）/ active（亮度 -5%，scale 0.98）/ disabled（30% 透明 + cursor not-allowed）/ loading（替换文字为 spinner，保持宽度）

### 3.2 Card（卡片）

```
┌─────────────────────────────────────┐
│ [可选 header 行：标题 + 操作按钮]    │
├─────────────────────────────────────┤
│                                     │
│ 内容                                 │
│                                     │
└─────────────────────────────────────┘
```

- 背景 `bg-surface`
- 边框 `border-subtle`（非常轻）
- 圆角 `radius-sm` (4px)
- 内边距 `space-4` (16px)
- Header / Footer 分隔线用 `border-subtle`，不用粗线
- Hover 时背景升级到 `bg-surface-raised`，过渡 200ms

**变体**：
- `card-flat`（默认）
- `card-elevated`：背景 `bg-surface-raised`，加 `shadow-sm`
- `card-active`：左边框 3px 高亮（品牌绿或橙，看上下文），表示当前激活
- `card-glow`：加 `shadow-glow-orange` 表示需要注意（仅短期使用，比如新预警卡片前 30 秒）

### 3.3 Table（表格）

**视觉规则**：
- 行高 40px（默认）/ 32px（密集）/ 48px（宽松）
- 行间分隔用 `border-subtle`，不用斑马纹
- Hover 行：`bg-surface-raised`
- 选中行：`bg-brand-emerald-muted` + 左边框 3px 品牌绿
- 表头：`text-xs` + `text-muted` + `font-medium`，非粗体
- 数字列右对齐，文本列左对齐
- 数字用 Mono 字体 + tabular-nums

**响应式**：
- < 1024px：横向滚动，固定首列
- < 640px：表格转卡片（每行变一张紧凑卡片）

### 3.4 Badge（徽章）

```
[ Critical ]  [ +0.85% ]  [ 持仓 ]
```

- 高度 20px
- 内边距 `0 8px`
- 字号 `text-xs` + `font-medium`
- 圆角 `radius-xs` (2px)
- 严重度 badge 用低饱和背景 + 高饱和文字
- 数据 badge 用 `bg-surface-raised` + 对应数据色

### 3.5 Tooltip

- 背景 `bg-surface-overlay`
- 文字 `text-primary` `text-sm`
- 边框 `border-default`
- 圆角 `radius-sm`
- 内边距 `space-2 space-3`
- 阴影 `shadow-md`
- 出现延迟 300ms，消失延迟 0ms
- 永远附带小箭头指向触发元素

### 3.6 Modal / Drawer

**Modal**：居中浮窗，背景 backdrop `rgba(0,0,0,0.7)`。
**Drawer**：从右侧滑入（默认），宽度 480px / 640px / 800px / 100% 四档。

- 都用 `bg-surface-overlay` + `shadow-lg`
- 进入：`duration-slow` + `ease-decelerate`
- 退出：`duration-base` + `ease-accelerate`
- 关闭：ESC 键 / 点击背景 / 关闭按钮三种方式

### 3.7 Empty States（空态）

**绝对禁止**："暂无数据" / "No data" / 空白页面。

每个空态包含：
1. **插画**（极简线条，单色）
2. **主标题**（一句话说清楚状态）
3. **辅助说明**（一句话给原因或建议）
4. **行动按钮**（如果可行动）

示例：
```
┌─────────────────────────────────────┐
│                                     │
│         ▓▓▓▓                        │
│       ▓▓    ▓▓                      │
│      ▓        ▓                     │
│       ▓▓    ▓▓                      │
│         ▓▓▓▓                        │
│                                     │
│   未建立持仓                         │
│   添加你的第一笔，让 Zeus 围绕你工作   │
│                                     │
│       [+ 添加持仓]                   │
│                                     │
└─────────────────────────────────────┘
```

### 3.8 Loading States（加载态）

**禁止 spinner**（只在按钮内、< 1 秒短任务时用）。

**默认**：Skeleton（骨架屏）
- 背景 `bg-surface-raised`
- 渐变扫光动画（从左到右），周期 1.5 秒
- 形状对齐目标内容（不要用统一灰条）

**长任务**（> 3 秒）：进度条 + 状态文字
- 进度条：高度 2px，背景 `border-default`，进度条 `bg-brand-emerald`
- 文字：`text-sm` `text-muted`，描述当前阶段

---

## 4. 领域专属组件

这些组件是 Zeus 区别于通用产品的视觉资产。

### 4.1 Causal Web（因果网）

**这是 Zeus 的标志性组件，在 Map 页是主角，其他页面以局部形式出现。**

#### 节点

```
事件型 (Event)：     ⬢   六边形
信号型 (Signal)：    ◆   菱形
指标型 (Metric)：    ■   方形
预警型 (Alert)：     ●   圆形（带光环）
反证型 (Counter)：   ✕   叉号（红色）
```

- 大小 = 影响力（影响下游节点数）：24px / 32px / 48px / 64px 四档
- 亮度 = 新鲜度：刚激活 100% 亮度，每小时衰减 10%，最低 30%
- 边缘脉动 = 当前活跃中（呼吸动画 2 秒周期）

#### 边

- **粗细** = 因果置信度：1px / 2px / 3px / 4px 对应 < 0.5 / 0.5-0.7 / 0.7-0.85 / > 0.85
- **颜色**：
  - 看多链 → 暖橙渐变（`brand-orange` → `chart-2`）
  - 看空链 → 冷红渐变（`data-down` → `chart-5`）
  - 中性 / 未知方向 → 灰
- **样式**：
  - 实线：已验证关联（来自 propagation graph）
  - 虚线：假设性（LLM 提出未验证）
  - 双线：双向影响
- **标签**：边的中点显示 `lag: 1d / hit: 0.72`（hover 显示完整信息）

#### 动画

- **激活**：信号触发时，源节点发出橙色粒子沿边流向下游，下游节点 `ease-spring` 弹出
- **关联发现**：边以"画线"动画从虚到实（800ms）
- **节点点击**：聚焦该节点 + 高亮所有相关边 + 周边节点淡化到 30%

#### 交互模式

| 模式 | 触发 | 行为 |
|------|------|------|
| `Live` | 默认 | 实时显示当前活跃因果链 |
| `Replay` | 点预警卡的⏪ | 回放最近 7 天因果累积 |
| `Explorer` | 点任意节点 | 反向追溯所有原因 / 正向预测所有影响 |
| `Free` | Konami 码彩蛋 | 节点可拖拽随便玩 |

#### 技术实现

- D3-force 物理引擎（节点斥力 + 边吸力）
- react-flow 做交互节点
- SVG 节点 + Canvas 粒子动画（性能）
- 数据来自 propagation graph + 实时事件总线

### 4.2 Heartbeat Bar（心跳条）

页面顶部 8px 高的全局横幅，永远显示。

```
[●数据 14s] [●17 信号活跃] [●Drift: 正常] [●校准 73/100] [●Regime: range_high_vol]
```

- 高度 8px（极窄）
- 数据点之间用 `space-3` 分隔
- 状态指示圆点 6px，颜色按状态：
  - 健康 = `brand-emerald` 带 `shadow-glow-emerald`
  - 警告 = `status-warning`
  - 异常 = `status-error` 带脉动
- 点击任一区块跳转到对应详情

### 4.3 Confidence Halo（置信光环）

任何置信度数字（"85%"）周围有圆形光环：

```
       ╭──╮
       │85│
       ╰──╯
```

- 直径 = 数字字号 × 2
- **粗细** = 样本量（细 = 数据少 / 粗 = 数据足）
- **完整度** = 置信区间（残缺 = 不确定）
- **颜色** = 校准状态（暖橙 = 校准期 / 翠绿 = 校准成熟 / 红 = 衰减检测中）

实现：SVG `<circle>` + `stroke-dasharray` 控制残缺度。

### 4.4 Probability Fan（概率扇）

价格图右侧延伸的概率云：

```
价格 ──────────────╮     ╭─ 5% 概率破 5000
                   │   ╱╱
                   │ ╱╱╱╱╱   70% 区间 4500-4800
                   │╱╱╱╱╱╱
当前 ──────────────●╲╲╲╲╲
                   │ ╲╲╲╲╲   25% 跌破 4500
                   │   ╲╲
                   ╰──────╮  5% 概率破 4200

      [────────历史────────│──────预测─────]
```

- 历史价格用细实线（1px）
- 预测扇形分 3 层概率带：
  - P10-P90：浅色填充（透明度 30%）
  - P25-P75：中色填充（透明度 50%）
  - P50：深色实线（中位数路径）
- 颜色：看涨偏 `chart-1`，看跌偏 `chart-5`，中性灰
- 关键分位数标注（如"5% 概率破 5000"）

### 4.5 Hypothesis Cards（假设卡片）

```
┌──────────────────────────────────────┐
│ 焦煤价格 > P75 → 螺纹利润 < 0 (90d)  │
│                                      │
│ 触发: 0.71 命中率                     │
│ 样本: 23 (warmup)                    │
│ 状态: ◐ shadow_testing               │
│                                      │
│ ─ 翻面查看历史 ─                      │
└──────────────────────────────────────┘
```

- 卡片正面：核心信息
- Hover 翻面（CSS 3D transform）显示：所有历史触发记录、命中分布、相关预警
- 拖拽：拖到"激活"区 = 加入监控；拖到"归档"区 = 验证失败
- 当前状态用左边框 3px 颜色表示：proposed / reviewed / shadow_testing / validated / applied

### 4.6 Trade Plan（航班计划单）

每条交易建议显示为可视化"航班计划单"，不是纯文本：

```
┌────────────────────────────────────────────┐
│ RB2510  做多  3 手                          │
│                                            │
│   入场 ─── 止损                  ─── 目标   │
│  ●─────────────────────────────────────●   │
│  4280     4150        当前 4310     4520    │
│  ↑                                     ↑   │
│  Risk -3.0% ─────────────── Reward +5.6%   │
│  R:R = 1:1.87                              │
│                                            │
│  保证金占用  ▓▓▓▓░░░░░░  18%                │
│  组合风险   ▓▓░░░░░░░░  6% (健康)           │
└────────────────────────────────────────────┘
```

- 入场 / 止损 / 目标用价格轴可视化
- 当前价用动态指示器（`brand-orange` 圆点 + 脉动）
- R:R 比直接显示
- 保证金占用 / 组合风险用进度条
- 一键操作：[采纳建议] / [修改] / [拒绝]

### 4.7 Command Palette（命令面板）

`⌘K` 唤起的全局命令面板：

```
┌─────────────────────────────────────────────┐
│ 🔍 搜索品种 / 跳转 / 执行...                  │
├─────────────────────────────────────────────┤
│  跳转                                        │
│    📊 Dashboard                              │
│    🔔 Alerts                                 │
│    🌐 Causal Web                             │
│  品种                                        │
│    ◇ RB2510  螺纹钢主力 持仓中               │
│    ◇ NR2509  天然胶主力                      │
│  操作                                        │
│    ➕ 添加持仓                                │
│    🤖 询问 AI Companion                      │
│    📝 创建笔记                                │
└─────────────────────────────────────────────┘
```

- 模糊搜索（Fuse.js）
- 分组显示：跳转 / 品种 / 操作 / AI / 最近
- ↑↓ 选择，Enter 执行，Esc 关闭
- 置顶最近使用项（个人化）

### 4.8 AI Companion（永驻 AI 助手）

右下角永远存在的入口：

```
                                    ┌──────┐
                                    │ 💬   │
                                    └──────┘
```

- 默认折叠（48px 圆形按钮，`brand-emerald` + `shadow-glow-emerald`）
- 点击展开为 Drawer（宽度 400px）
- 流式响应（边返回边显示）
- **关键**：知道当前页面上下文 —— 在预警详情页问"为什么"，自动注入预警 ID 和数据
- 每次回答附带"引用来源"（哪些信号、哪些数据）
- 会话历史按页面分组保存

### 4.9 Sector Heatmap（板块热力图）

```
┌──────────────────────────────────────────┐
│  黑色  ▓▓▓░░ +0.5  ▓▓▓▓▓ +1.2  ▓▓░░░ -0.3│
│         RB        HC          I           │
│  能化  ▓▓░░░ -0.1  ▓░░░░ -0.6  ▓▓░░░ -0.2│
│         SC        PTA         MA          │
│  ...                                     │
└──────────────────────────────────────────┘
```

- 每板块一行
- 每品种一格，宽度 ≈ 板块内权重
- 颜色：涨绿 / 跌红，明度 = 涨跌幅
- 格内显示品种代码 + 涨跌幅
- 信号活跃时格子边框脉动 `brand-orange`
- Hover 显示详细 tooltip
- 点击进入品种详情

---

## 5. 页面布局

### 5.1 全局结构（桌面）

```
┌─────────────────────────────────────────────────────────────┐
│ Heartbeat Bar (8px)                                          │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│          │                                                  │
│ Sidebar  │            Page Content                          │
│ (220px)  │                                                  │
│          │                                                  │
│          │                                                  │
├──────────┴──────────────────────────────────────────────────┤
│ Status Bar (24px) — 时区 / 数据时间 / 当前用户                │
└─────────────────────────────────────────────────────────────┘
                                                  ┌──────┐
                                                  │ AI 💬│
                                                  └──────┘
```

### 5.2 导航（Sidebar）

```
┌──────────────────────┐
│  ZEUS                │
├──────────────────────┤
│  ⌂ Command Center    │
│  🔔 Alerts        12 │
│  ✈ Trade Plans       │
│  📊 Portfolio Map    │
│  ─                   │
│  🌐 Causal Web       │
│  🏭 Industry Lens    │
│  📋 Sectors          │
│  🔮 Future Lab       │
│  ─                   │
│  🛠 Strategy Forge   │
│  📝 Notebook         │
│  📈 Analytics        │
│  ─                   │
│  ⚙ Settings          │
└──────────────────────┘
```

- 默认展开 220px / 折叠 64px（仅图标）
- 图标 24px Lucide
- 数字徽章用 `bg-brand-orange` 表示新事项
- 当前页用 `bg-brand-emerald-muted` + 左边框 3px `brand-emerald`
- Hover 用 `bg-surface-raised`

### 5.3 响应式断点

| 断点 | 范围 | 行为 |
|------|------|------|
| `mobile` | < 640px | Sidebar 转 Bottom Nav（核心 5 项），表格转卡片，Causal Web 转列表 |
| `tablet` | 640-1024px | Sidebar 默认折叠，可展开 |
| `desktop` | 1024-1536px | Sidebar 默认展开 |
| `wide` | ≥ 1536px | Sidebar 展开 + 内容区双栏布局选项 |

---

## 6. 逐页设计意图

### 6.1 Command Center（首页 / Dashboard）

**目的**：一眼掌握"系统现在告诉我什么"。

**布局**：
```
┌─────────────────────────────────────────────────────────────┐
│ [个人化欢迎条]                                                │
│ 晚上好，OracleX。距上次访问 14 小时。期间：12 条预警 / 3 条相关│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ 因果网（缩略）───────────┐  ┌─ 当日预警流 ──────────┐    │
│  │                           │  │ 🔔 RB cost_pressure  │    │
│  │   实时活跃因果链           │  │ 🔔 NR news_event     │    │
│  │   节点 + 粒子流            │  │ 🔔 ...               │    │
│  │   [展开看全图]             │  └─────────────────────┘    │
│  └───────────────────────────┘                              │
│                                                             │
│  ┌─ 持仓概览 ────────────┐  ┌─ 板块热力图 ──────────┐       │
│  │ RB2510 +1.2% ▓▓▓▓░░  │  │  黑色  ▓▓▓░░  +0.5    │       │
│  │ NR2509 -0.3% ▓▓░░░░  │  │  能化  ▓▓░░░  -0.1    │       │
│  └──────────────────────┘  │  ...                  │       │
│                            └───────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

**关键设计**：
- 个人化欢迎条 = 温度，不是数据
- 因果网缩略图作为视觉锚点（点击进入完整 Causal Web）
- 留白慷慨，每个区块有呼吸感
- 不放性能榜、不放排名 —— Zeus 不是聊天工具，没有"打榜"动机

### 6.2 Alerts

**目的**：处理今天的所有预警。

**布局**：左 320px 筛选侧栏 + 右内容区（卡片堆叠流）。

```
┌─ 筛选 ─────┐  ┌─ 预警流 ─────────────────────────────────┐
│ 严重度      │  │ ┌─────────────────────────────────────┐ │
│ ☑ Critical  │  │ │ 🔴 Critical  09:42                  │ │
│ ☑ High      │  │ │ RB cost_support_pressure             │ │
│ ☐ Medium    │  │ │ 螺纹跌破 P75 边际成本支撑            │ │
│             │  │ │ [⏪ Time Machine] [详情]              │ │
│ 评估器      │  │ └─────────────────────────────────────┘ │
│ ☑ ALL       │  │                                         │
│             │  │ ┌─────────────────────────────────────┐ │
│ 板块        │  │ │ 🟡 High      09:31                  │ │
│ ☑ 黑色      │  │ │ NR news_event                       │ │
│ ☑ 橡胶      │  │ │ 泰国天胶产区暴雨预警                  │ │
│             │  │ └─────────────────────────────────────┘ │
└────────────┘  └─────────────────────────────────────────┘
```

**关键设计**：
- 卡片堆叠（不是表格），新预警从顶部带 `shadow-glow-orange` 飘入
- 每张卡有 Time Machine 入口（核心差异化功能）
- 卡片颜色 = 严重度色阶（左边框 4px）
- 已处理的预警变灰（70% 透明）但保留可见
- 详情 Drawer 滑入 640px 宽

### 6.3 Trade Plans（推荐）

**目的**：评估并采纳交易建议。

**布局**：每个建议一张完整 Trade Plan 卡片（4.6 节定义），垂直堆叠。

**关键设计**：
- Plan 卡片 = 视觉化执行计划（不是文字描述）
- "采纳"按钮触发持仓预填 → 导航到 Portfolio Map
- 每个 Plan 附带"为什么"折叠区（信号路径 + 反证 + 历史类比）

### 6.4 Portfolio Map（持仓）

**目的**：可视化展示持仓在传导图中的暴露。

**布局**：
- 上方：组合健康度仪表盘（VaR / 集中度 / 相关性）
- 中间：**持仓 × 传导图叠加**——把你的持仓品种在 Causal Web 里高亮，下游被影响品种用虚线圈出
- 下方：持仓列表（紧凑表格，含动态止盈止损）

**关键设计**：
- 持仓不是列表，是地图上的位置
- 每个持仓品种是地图上一个 lighting node
- 关联节点（被持仓影响的下游）用虚线圈显示"暴露范围"
- 风控告警时持仓节点变红 + 闪烁

### 6.5 Industry Lens（成本模型）

**目的**：研究品种的成本结构和利润空间。

**布局**：
- 顶部：品种切换 Tab（RB / HC / I / J / JM / NR / RU）
- 主体：**双栏**
  - 左 50%：成本分解瀑布图 + 利润率趋势图
  - 右 50%：成本曲线分位数图（横轴价格，纵轴累积产能 %），叠加当前价格线
- 底部：动态调价计算器（Notion 风的滑块）

**关键设计**：
- 数据来源标签贴在每个数据点旁（透明度文字）："来源: 公开 / LLM 提取 / 手动 - 误差 ±5%"
- 价格触及 P75 / P90 时该位置脉动（提示成本支撑）
- 调价计算器：滑块拖动时整个瀑布图实时重算（200ms 内响应）

### 6.6 Sectors

**目的**：板块层面的方向判断。

**布局**：
- 顶部：板块热力图（4.9 节）
- 中间：选中板块的"板块卡片"（核心因子 + 决策度 conviction_float + 历史命中率）
- 底部：板块内品种对比（小型多线图）

### 6.7 Causal Web（信号传导）

**目的**：Zeus 的标志性页面，全屏因果网交互。

**布局**：
- 全屏 Causal Web（4.1 节）
- 右侧 320px Drawer：节点详情、关联、历史
- 顶部模式切换（Live / Replay / Explorer / Free）
- 左下角控件：缩放 / 居中 / 截图

**关键设计**：
- 这是用户的"地图房间"，每天都该来一次
- Live 模式默认开启，看着系统在思考是种享受
- 截图按钮支持导出（带水印），方便分享研究

### 6.8 Future Lab（场景推演）

**目的**：跑模拟、做 What-if。

**布局**：
- 上方：场景配置区（选品种、设假设条件、调参数）
- 主体：**概率扇**（4.4 节）作为视觉主角
- 下方：模拟路径列表（前 N 条样本路径，可点击查看完整轨迹）
- 右侧 Drawer：LLM 生成的情景叙事报告

**关键设计**：
- 假设输入用滑块和拖拽，不用纯输入框
- 模拟开始时有 "lab is brewing" 动画（给重型计算 5-30 秒一个"科学感"）
- 推演完成后整个屏幕有轻微 `shadow-glow-emerald` 闪过 = 完成感

### 6.9 Strategy Forge（回测）

**目的**：策略研究和参数调优。

**布局**：标准回测平台 UX（参数面板 + 资金曲线 + 详细指标 + 持仓时间分布）。在 Zeus 风格化。

### 6.10 Notebook（研究笔记）

**目的**：你的个人知识库。

**布局**：
- 左 240px：笔记树状目录（按品种 / 按主题 / 按时间）
- 主体：Markdown 编辑器（类 Notion 体验）
- 右 280px：当前笔记的关联（关联的预警 / 关联的假设 / 关联的交易）

**关键设计**：
- 假设卡片可以从笔记中拖出（4.5 节）
- 笔记内 `@RB2510` 自动链接到品种页
- 笔记内 `#hypothesis:xxx` 自动关联到假设
- Annotation Layer：可以贴便签到任何图表 / 预警 / 推演

### 6.11 Analytics

**目的**：系统运行健康度 + 个人交易归因。

**布局**：三 Tab
- Tab 1: 推荐归因（月度报表，6.17）
- Tab 2: 校准仪表盘（每个信号类型的 reliability diagram + 样本量）
- Tab 3: Drift 监控（PSI 趋势 + 相关性矩阵变化）

**关键设计**：
- Tab 1 是 Goal B 的命脉，给最大权重
- Tab 2 透明度极高 —— 你能看到系统在每一步的不确定性
- Tab 3 提供历史快照（"半年前的 Drift 状态"），方便对比

### 6.12 Settings

**目的**：系统配置。

**布局**：标准 Settings 布局（左侧分组 + 右侧表单）。

---

## 7. 交互规范

### 7.1 Boot Sequence（启动动画）

每次冷启动 / 刷新页面，1.5 秒序列：

```
0ms:   纯黑屏（背景 #000）
0-200ms:  顶部 Heartbeat Bar 出现（淡入），心跳 ●●● 开始脉动
200-400ms: Sidebar 从左滑入，Logo 字符逐个出现（typewriter 效果）
400-800ms: 页面内容渐显（按 z-index 分层 fade in）
800-1500ms: 因果网节点逐个亮起（如果在 Dashboard），ease-spring
1500ms:  Boot 完成，AI Companion 按钮带 shadow-glow-emerald 闪一下
```

每天打开 Zeus 都该有"系统在为我活过来"的仪式感。

### 7.2 Status Choreography（状态编排）

| 事件 | 视觉响应 |
|------|---------|
| 数字增长 | 滚动数字（CountUp.js），300ms |
| 新预警到达 | 从 Heartbeat Bar 脉冲一下 → 列表顶部带 shadow-glow-orange 飘入 |
| 信号在 Causal Web 触发 | 源节点橙色光晕扩散 → 粒子沿边流动 → 下游节点弹起 |
| 任务完成 | 绿色对勾打钩动画（300ms） |
| 错误 | 红色短促震动（horizontal shake，3 次）|
| Drift 状态切换 | Heartbeat Bar 对应圆点平滑过渡（不是突变） |

### 7.3 Empty States 设计

每个页面都必须有完整设计的空态。在 docs/EMPTY_STATES.md 单独维护清单（实施时创建）。

### 7.4 键盘快捷

| 快捷键 | 功能 |
|--------|------|
| `⌘K` | 打开 Command Palette |
| `⌘/` | 打开 AI Companion |
| `⌘Shift+C` | 进入 Comparison Lens |
| `⌘B` | 折叠/展开 Sidebar |
| `?` | 显示快捷键帮助 |
| `g` then `d` | Goto Dashboard |
| `g` then `a` | Goto Alerts |
| `g` then `m` | Goto Causal Web |
| `Esc` | 关闭 Modal / Drawer |

### 7.5 Achievement Moments（成就时刻）

不是 popup，是 Dashboard 顶部一行小字 + 12px 高度横幅，淡进淡出（5 秒后自动收起）：

> 📊 第一个校准桶达标了 — RB momentum_low_vol 现在有 100 个样本

样式：背景 `brand-emerald-muted`，文字 `text-primary`，左边 emoji。点击进入对应详情。

### 7.6 Easter Eggs（彩蛋）

| 彩蛋 | 触发 | 效果 |
|------|------|------|
| Causal Web Free Mode | Konami 码 ↑↑↓↓←→←→BA | 节点变可拖拽自由模式 |
| Logo 主题切换 | 长按 Logo 3 秒 | 品牌绿在深翠 #059669 ↔ 鲜翠 #10B981 间切换 |

控制在两个，**不张扬，让用户偶然发现**。

---

## 8. 动效规范

### 8.1 时长选择

| 场景 | 时长 |
|------|------|
| Hover / focus | 100ms |
| Button press | 100ms |
| 状态切换（Tab / Toggle） | 200ms |
| Modal / Drawer 进入 | 400ms |
| Modal / Drawer 退出 | 200ms |
| 页面切换 | 250ms（淡入淡出） |
| Boot Sequence | 1500ms（编排） |
| Causal Web 节点激活 | 600ms（spring） |
| 数字滚动 | 300-600ms（依距离） |

### 8.2 缓动选择

- 默认：`ease-standard`（90% 场景）
- 进入屏幕：`ease-decelerate`
- 离开屏幕：`ease-accelerate`
- 趣味元素：`ease-spring`（节点激活、成就、彩蛋）

### 8.3 性能约束

- 60fps 是底线
- 优先用 CSS transform / opacity（不用 width / height / top / left）
- 复杂动画用 `will-change`（用完移除）
- 移动端禁用 backdrop-filter（性能杀手）
- prefers-reduced-motion 时所有动画时长 ≤ 100ms 或禁用

---

## 9. 图标系统

### 9.1 主图标库：Lucide

**理由**：
- 设计语言最接近 OKX 的几何抽象感
- 与 Tailwind 4 配套良好
- 1500+ 图标覆盖通用场景
- 可调粗细（stroke-width）

**默认规格**：
- 尺寸 24px / 20px / 16px 三档
- stroke-width 1.5px（默认）/ 2px（粗体强调）
- color 继承父元素 `currentColor`

### 9.2 自定义图标

以下场景需要自定义图标（通过 SVG 实现）：

| 类别 | 图标 | 用途 |
|------|------|------|
| 节点类型 | event / signal / metric / alert / counter | Causal Web |
| 板块标识 | 黑色 / 能化 / 农产品 / 有色 / 贵金属 / 橡胶 | 板块快速识别 |
| Zeus Logo | 主 logo / 简化 logo / icon-only | 品牌 |
| 状态指示 | heartbeat / drift / calibration | 心跳条专用 |

存放在 `frontend/src/components/icons/`，每个图标一个 React 组件。

### 9.3 图标使用规则

- 不混用图标库（除 Lucide + 自定义之外不引入第三方）
- 不在同一界面用不同 stroke-width
- 不给图标加阴影（除非是大尺寸装饰性使用）
- 文字旁的图标永远 16px，垂直居中

---

## 10. 可访问性

### 10.1 对比度

- 正文文字 vs 背景：≥ 7:1（AAA）
- 大字（≥ 18px）：≥ 4.5:1（AA）
- 非文字元素（边框、图标）：≥ 3:1

实测当前色板：
- `text-primary` (#FFF) on `bg-base` (#000) = 21:1 ✓
- `text-secondary` (#A3A3A3) on `bg-base` (#000) = 9.7:1 ✓
- `text-muted` (#737373) on `bg-base` (#000) = 4.9:1 ✓ (大字 OK)

### 10.2 键盘

- 所有交互元素必须可 Tab
- focus 状态必须有 2px outline `brand-emerald`
- 跳过导航的 "Skip to content" 链接（屏幕阅读器友好）
- Modal / Drawer trap focus 在内部

### 10.3 屏幕阅读器

- 所有图标按钮必须有 `aria-label`
- 状态变化用 `aria-live="polite"`（预警）/ `assertive`（错误）
- 数据表格用 `<th>` + `scope`
- 装饰性图片用 `aria-hidden="true"`

### 10.4 减弱动效

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

并在代码层面：因果网粒子动画关闭、Boot Sequence 跳过。

---

## 11. 实现优先级

10 个额外功能 + 12 个核心组件不可能一次到位。建议这样分层实施：

### P0（Phase 1 完成时必须有）

设计系统基础就位，日常使用不卡。

| 项 | 说明 |
|----|------|
| 色彩 / 字体 / 间距 / 圆角 / 阴影 / 动效 Tokens | CSS 变量 + Tailwind 配置 |
| Button / Card / Table / Badge / Tooltip / Modal / Drawer | 基础组件 |
| Empty States / Loading States | 必备 |
| Sidebar + Heartbeat Bar | 全局结构 |
| 11 个页面的基础布局 | 页面通了，但视觉效果不必到位 |

### P1（Phase 5 完成时应有）

Zeus 的灵魂功能。这些不到位，Zeus 还是个"普通工具"。

| 项 | 关联 Phase | 优先 |
|----|-----------|------|
| **Causal Web** 完整版 | Phase 2-3（数据就绪后） | ★★★ 最高 |
| Boot Sequence | Phase 1 | ★★★ |
| Status Choreography（核心动画） | Phase 1-5 | ★★★ |
| Cmd+K Command Palette | Phase 5 | ★★★ |
| AI Companion | Phase 5 | ★★ |
| Trade Plan 视觉化卡片 | Phase 5 | ★★ |
| Confidence Halo | Phase 3（校准就绪后） | ★★ |
| 个人化欢迎条 | Phase 5 | ★★ |
| Sector Heatmap | Phase 1 | ★★ |

### P2（Phase 9 之前补齐）

锦上添花。完整体验。

| 项 | 关联 Phase | 优先 |
|----|-----------|------|
| Time Machine | Phase 5-6 | ★★ |
| Probability Fan | Phase 8 | ★★ |
| Hypothesis Cards | Phase 9 | ★★ |
| Comparison Lens | Phase 5+ | ★ |
| Annotation Layer | Phase 6+ | ★ |
| Achievement Moments | 任意 Phase | ★ |
| Sound Design | 最后 | ★ |
| Easter Eggs | 最后 | ★ |
| Regime Cape（背景） | 最后 | ★ |

### P3（按兴趣可选）

不做也不影响产品。

| 项 |
|----|
| 多人协作（如未来扩展） |
| 移动端独立 App |
| 主题切换（Light Mode） |

---

## 12. 附录

### 12.1 色彩语义对照表（防混淆）

| 颜色 | 角色 | 不要用作 |
|------|------|---------|
| `brand-emerald` #059669 | Zeus 品牌 / 导航 / 主按钮 | 数据涨跌、预警等级 |
| `brand-orange` #F97316 | 关键行动 / 信号高光 | 数据涨跌、Medium 预警 |
| `data-up` #10B981 | 价格上涨 / 正收益 | 品牌、按钮 |
| `data-down` #EF4444 | 价格下跌 / 负收益 | 状态错误（虽然是同色） |
| `severity-medium` (low-sat orange) | Medium 预警 | 行动按钮 |

### 12.2 动效预设代码

```css
/* tokens */
--ease-standard: cubic-bezier(0.4, 0, 0.2, 1);
--ease-decelerate: cubic-bezier(0, 0, 0.2, 1);
--ease-accelerate: cubic-bezier(0.4, 0, 1, 1);
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);

--duration-fast: 100ms;
--duration-base: 200ms;
--duration-slow: 400ms;
--duration-deliberate: 800ms;

/* animations */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes glowPulse {
  0%, 100% { box-shadow: 0 0 16px rgba(249, 115, 22, 0.45); }
  50% { box-shadow: 0 0 24px rgba(249, 115, 22, 0.7); }
}

@keyframes heartbeat {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

@keyframes shimmer {
  0% { background-position: -1000px 0; }
  100% { background-position: 1000px 0; }
}
```

### 12.3 推荐技术栈（前端）

| 类别 | 选择 | 理由 |
|------|------|------|
| 框架 | Next.js 16 + React 19 | Causa 已用 |
| 样式 | Tailwind 4 | 已用 + 设计 tokens 友好 |
| 组件库 | shadcn/ui (基础) + 自定义 | 不引入沉重 UI 库 |
| 图标 | Lucide React | 见 9.1 |
| 图表 | Recharts (基础) + visx (复杂自定义) | 黑底支持好 |
| 因果网 | react-flow + d3-force + canvas-particles | 见 4.1 |
| 命令面板 | cmdk | shadcn 也用这个 |
| 动效 | Framer Motion + CSS 原生 | 复杂的用 Framer，简单的用 CSS |
| 表格 | TanStack Table | 标准 |
| Markdown | react-markdown + rehype-prism | Notebook 用 |
| 通知 | Sonner | 极简 toast |

### 12.4 设计参考截图

实施期间维护截图库于 `docs/design-references/`：
- OKX 暗色主题截图（标注我们借鉴的部分）
- Linear 命令面板（参考 Cmd+K）
- Notion 编辑器（参考 Notebook）
- TradingView 图表（参考 Industry Lens）
- Bloomberg Terminal（参考 Heartbeat 调性）

实施时持续更新参考库。

---

## 13. 维护

- 任何新组件加入必须在本文档中先定义 spec
- 视觉决策有争议时，回到 §0 北极星："这让用户更爽了吗？"
- 每个 Phase 结束做一次设计 review，更新本文档
- 与 ARCHITECTURE.md / EXECUTION_PLAN.md 对齐：本文档定义"长什么样"，那两个文档定义"做什么"
