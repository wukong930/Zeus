# Zeus

> 商品期货研究与决策智能平台 · 下一代演进于 [Causa](https://github.com/wukong930/Causa)

[![Frontend Prototype](https://img.shields.io/badge/Status-Frontend_Prototype-F97316)](#)
[![Design System v1.0](https://img.shields.io/badge/Design-v1.0-059669)](docs/DESIGN_SYSTEM.md)
[![Architecture v1.2](https://img.shields.io/badge/Architecture-v1.2-059669)](docs/ARCHITECTURE.md)

Zeus 是 Causa 的下一代演进，目标：从"硬编码线性管道"升级为**事件驱动 + 自校准 + 对抗验证**的智能研究平台。**目标用户是把系统信号作为交易决策依据的专业期货交易员**（Goal B）。

## 北极星

> **让用户用起来很爽——通过密切的人机交互制造"系统在为我活过来"的感觉。**

每个设计决策都回到这个标准。

## 当前状态

**✅ 设计完成**：4 份核心文档总计约 4500 行，定义了从架构到产品到执行到视觉的全套规范。

**🚧 前端原型完成**：全部 12 个页面 + 9 个领域组件 + 完整设计系统的可交互演示（纯前端，mock 数据）。

**⏳ 后端待开发**：Python FastAPI 后端将分 12 个 Phase（约 18 周）实施。

## 快速开始

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:3000
```

## 设计文档

| 文档 | 用途 |
|------|------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 系统架构 v1.2（20 个模块 + 数据模型 + 事件流） |
| [`docs/PRD.md`](docs/PRD.md) | 产品需求（11 大功能模块） |
| [`docs/EXECUTION_PLAN.md`](docs/EXECUTION_PLAN.md) | 执行计划 v1.2（12 个 Phase, ~18 周） |
| [`docs/DESIGN_CHANGES.md`](docs/DESIGN_CHANGES.md) | Causa → Zeus 保留 / 删除 / 新增 26 项变更 |
| [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) | 前端设计规范 v1.0（色彩 / 字体 / 组件 / 页面 / 动效） |

## 核心创新

相比 Causa：

- **校准循环**（冷启动）：贝叶斯权重更新 + 影子追踪（前向收益 1d/5d/20d）+ Regime 检测
- **对抗引擎**：3 项统计检验（零假设 + 历史组合 + 结构性反驳），冷启动 90 天 warmup mode
- **混合决策 Alert Agent**：90% 走规则、10% 走 LLM，置信度分层（auto/notify/confirm/arbitrate）
- **PIT 数据架构**：vintage_at 字段 + 双视图（latest / pit），消除回测 lookahead bias
- **合约换月模块**：主力合约自动检测 + 价格序列拼接（adjusted / raw）
- **新闻事件管线**：拆分原 event_driven 为 price_gap + news_event，结构化新闻抽取
- **成本模型分位数**：P25/P50/P75/P90 成本曲线（不只是平均成本），盈亏平衡用 P75/P90
- **Causal Web**：实时因果传导可视化，Zeus 的视觉签名
- **自我学习闭环**：推荐归因 + 用户反馈学习 + Concept Drift + LLM 反思 Agent
- **核心治理守则**：所有自动学习输出永不直接修改主链路决策

## 前端原型亮点

打开就有的视觉冲击：

- **Boot Sequence**：1.5 秒系统唤醒动画（Logo 描线 + Typewriter + 进度条）
- **Causal Web**：动态因果网络图（节点形状区分类型 + 边粗细=置信度 + 实时粒子流动 + 反证节点）
- **Heartbeat Bar**：8px 顶部全局心跳条（数据 / 信号 / Drift / 校准 / Regime）
- **Trade Plan 卡片**：可视化飞行计划（入场 / 止损 / 目标 / 当前价滑动指示器）
- **Confidence Halo**：环形置信度可视化（粗细 = 样本量，完整度 = 置信区间）
- **Sector Heatmap**：板块品种热力图，信号活跃时橙色脉动
- **Probability Fan**：场景推演的概率扇形分布图
- **Cmd+K 命令面板**：跨页面跳转 + 品种搜索 + 操作执行
- **AI Companion**：右下角永驻入口，知道当前页面上下文

## 技术栈

**前端**（已实现原型）：
- Next.js 15 + React 19 + TypeScript
- Tailwind CSS 3.4
- Framer Motion + Lucide Icons
- cmdk + Recharts + ReactFlow

**后端**（设计阶段）：
- Python FastAPI + SQLAlchemy + Alembic
- PostgreSQL 16 + Redis Pub/Sub + Weaviate
- APScheduler + multi-LLM (Anthropic/OpenAI/DeepSeek)

## License

私人项目 · All rights reserved · OracleX
