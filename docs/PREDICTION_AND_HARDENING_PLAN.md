# Zeus 加固与预测能力实施计划

> 版本: 1.0 | 日期: 2026-06-28 | 负责人: 平台团队
> 关联文档: `docs/EXECUTION_PLAN.md`（主计划）、`docs/ARCHITECTURE.md`、`docs/PREDICTION_RESEARCH_FINDINGS.md`（研究结论）
> 状态: Track 1 加固完成（全部 P0/P1 收口，P0-2 密钥轮换为用户配置项）；Track 2 研究阶段收口——**横截面反转因子已验证并定稿为受治理生产信号，carry 因子证明有前景但卡数据未上生产**。详见研究结论文档。

---

## 0. 背景与结论摘要

本计划基于对 Zeus 的一次深度评估。核心结论：

- **工艺优秀**：~4.2 万行后端、673 个测试、PIT 双时态实现正确、四条核心铁律都有针对性测试、前端类型安全教科书级。
- **不是预测系统**：当前是一个规则化的异常检测 + 决策辅助打分引擎。它用人工阈值（z-score、MA 交叉、成本盈亏平衡线、新闻方向）表达方向性意见，并拿真实行情**事后**统计命中率——但**没有经样本外验证的价格方向预测能力**，`backtest/` 目录有统计护栏却无回测引擎，命中率口径把"方向/均值回归/波动"混成一锅。
- **安全与治理有缺口**：110 个 API 端点零认证；`.env` 落了 6 个真实第三方密钥（未进 git）；治理"审批→生效"链路是死代码（`production_effect` 硬编码 `"none"`），审批端点无认证且审批人可伪造。
- **正处开发尾声**：最近 60 个提交里 51 个是系统性 bug 收口（分页非唯一游标、标识归一化），收口未完成（`market_data` 仍在补游标）。

**本计划目标**：(1) 修复评估暴露的硬伤；(2) 在**不破坏"确定性 + 可追溯 + 可治理"**前提下，分期赋予经严格验证的预测能力。

**指导原则**：
1. **先让真相可测，再加模型**——先用现有信号跑一次扣成本的样本外回测，回答"规则到底有没有 edge"，再决定是否值得训模型。
2. **模型即"高风险规则变更"**——走同一套 shadow → governance → approval 轨道；模型永不自动改规则，由人批准某个被验证的版本，且影响有界、带 kill switch。
3. **推理确定可复现，训练离线被 gate**——非确定性关在离线训练里；线上推理钉死 `model_version` + `feature_hash` + PIT 特征快照，同输入同输出。
4. **LLM 边界不变**——预测头是经典 ML 跑数值特征，LLM 继续待在叙事/假设区。

---

## 1. 双轨结构与优先级

| 轨道 | 内容 | 性质 |
|---|---|---|
| **Track 1 — 加固修复** | 评估暴露的安全 / 治理 / 正确性硬伤 | 防御性，部分为对外部署阻断项 |
| **Track 2 — 预测能力** | A → B → C → D 四期，从"测真相"到"有界生产" | 增量价值，新代码为主 |

两轨**有交汇**：Track 2 的 C 期（受治理影子顾问）依赖 Track 1 的 **P0-3（接通治理"审批→生效"闭环）**——把这段死代码接通，既是修复，也是预测模型上线的前置。

---

## 2. Track 1 — 加固与修复

> 分级：**P0** = 对外部署阻断项 / **P1** = 收口与正确性 / **P2** = 质量加固。每条含：问题 → 动作 → 验收 → 回滚。

### P0（对外部署前必须完成）

**P0-1 · API 认证层缺失**
- 问题：`backend/app/main.py:53` 只挂 CORS，110 端点零认证，前端 `next.config.mjs` 把后端裸透传。
- 动作：加全局认证依赖（最小可用：`APIKeyHeader` + 环境 token；治理/settings/strategies 写端点额外角色校验，`reviewed_by`/`decided_by` 改为来自认证主体而非请求体）。
- 验收：未携带凭据的写请求返回 401/403；契约测试覆盖。
- 回滚：认证依赖以 feature flag 包裹，可关闭回退本地模式。

**P0-2 · `.env` 真实密钥**
- 问题：XAI/NOAA/AccuWeather/FRED/EIA/Tushare 6 个 key 明文落盘。
- 动作：轮换这 6 个密钥；生产迁移到 secret manager / docker secrets；`config.py` 默认值改为 fail-closed 占位。
- 验收：仓库与运行环境无明文长期密钥；轮换记录留档。

**P0-3 · 治理"审批→生效"闭环（与 Track 2 / C 期共用）**
- 问题：`api/governance.py:209` 硬编码 `production_effect: "none"`；`apply_signal_calibration_change` 唯一调用方 `try_apply_without_review`（`calibration/updater.py:224`）是死代码。审批仅翻转 status，从不落地。
- 动作（二选一，建议先 A 后 B）：
  - **A（短期）**：在 docs 与 `api/learning.py:167` 注释中明确"当前审批仅为咨询、无自动生效"，消除文档/代码落差。
  - **B（C 期实现）**：实现"读 `status==approved` 行 + 携审批令牌调用 applier"的落地链路；`human_approved` 改为校验审批行令牌/ID 而非可透传布尔。
- 验收：approved 行能驱动一次受护栏的生产参数写入，且无凭据无法触发。

### P1（收口与正确性）

**P1-1 · symbol 归一化单一真源**
- 问题：`services/symbols.py:11` `re.sub(r"\d+","")` 删所有数字，破坏 `6E`/`ES1!` 等根符号；写侧不归一化、读侧归一化，读写不对称。
- 动作：在 schema/写入层确立 symbol 唯一规范形态（合约信息只进 `contract_month`），或把 `normalize_root_symbol` 改为基于已知品种表的精确映射。
- 验收：写入与查询对同一品种产生一致键；新增带数字符号不再碰撞。

**P1-2 · market_data keyset 游标补齐**（部分已在工作区）
- 问题：`api/market_data.py:209` `/recent` 与 `pit.py:49` `_market_data_pit_statement` 是仅存的非 keyset 游标端点。
- 动作：接入与其余 14 模块一致的 `before_id` 元组游标 + 复合索引；补契约测试。
- 验收：同一时间戳多行翻页不丢不重；`test_list_query_contracts.py` 覆盖。

**P1-3 · adversarial 历史候选查询排序**（enforcing 前必修）
- 问题：`adversarial/engine.py:259` 无 `ORDER BY`，enforcing 模式下选 best candidate 非确定。
- 动作：加 `.order_by(signal_type, regime, id)` + 稳定 tiebreaker。

**P1-4 · 决策路径 `as_of` 必填**
- 问题：`calibration/tracker.py:44` 等多处 `as_of` 默认回退 `now()`，新调用方忘传即静默退化为"读最新"= 未来泄漏。
- 动作：决策路径函数（`get_calibration_weight` 等）`as_of` 改必填，去掉 `now()` 默认。

**P1-5 · 前端硬编码/吞错**
- 问题：`portfolio/page.tsx:55` `totalEquity=100000`、`StatusBar.tsx:13` 写死时间戳、`industry/page.tsx:930` rubber 季节性写死、`event-intelligence/page.tsx:215` 决策吞错。
- 动作：改为真实数据驱动或显式标注 fallback/降级；决策补 `catch` 与错误提示；更新 `FRONTEND_DATA_LOAD_AUDIT.md`。

### P2（质量加固）

- ✅ CI 加 `ruff` + `mypy`（后端，在 dev 容器内跑）；前端加 ESLint（`next/core-web-vitals` flat config，CI 跑 typecheck + lint + build）。
- ✅ 针对真实 Postgres 的 PIT 语句集成测试（`tests/test_pit_integration.py`，`@pytest.mark.integration`，事务回滚隔离，无库时自动 skip）。
- ⏸️ 进程内模块级缓存（`_MARKET_DATA_CACHE` 等 6 处）多副本前迁 Redis —— **评估后决定不迁**。这些是 12s TTL 的只读快照缓存，per-replica 短 TTL 缓存是标准可接受模式，多副本收益边际；而迁移会破坏快速缓存行为测试（async Redis 客户端绑定 event loop，`TestClient` 多 loop 下缓存静默失效，`count==2` 类断言失败，需把 6 处测试改写成 `AsyncClient` 的 Redis 集成测试）并给热路径加复杂度。留作真正需要跨副本共享状态时再做。
- ✅ CORS 加"禁止 `*` + credentials 共存"护栏（通配符自动关 credentials）；生产关闭 `/docs`、`/openapi.json`（auth 开启时）；接入限流（`RateLimitMiddleware`，`RATE_LIMIT_PER_MINUTE`）。

---

## 3. Track 2 — 预测能力（A / B / C / D）

> 每期含：目标、交付物、落地文件、验收门、依赖。

### A 期 · 先让真相可测（不碰模型）

**目标**：在不训任何模型的前提下，回答"现有方向信号扣掉成本后到底有没有 edge"，并修正度量口径。

- **A-1 信号回测引擎**（本次开工）
  - 交付物：`backend/app/services/backtest/signal_backtest.py` —— 在 `SignalTrack`（已存 `direction` + `forward_return_1d/5d/20d` + `outcome`）上，对方向类信号计算**扣滑点后的净方向收益**，聚合出每信号类型与组合的 Sharpe / **Deflated Sharpe**（trials = 信号类型数）/ 命中率 / 路径指标；对信号类型族做 FDR 校正。
  - 复用：`multiple_testing.deflated_sharpe_ratio`、`slippage.calculate_slippage`、`path_metrics.calculate_path_metrics`、`market_data/pit`。
  - 验收门：纯函数可离线测；扣成本命中率与净收益分信号类型给出；Deflated Sharpe 作为 edge 是否显著的统一门。
- **A-2 命中率口径拆分**
  - 把当前混在一起的命中率按语义分三类报告：**方向预测 / 均值回归 / 波动放大**（依据 `signals/outcomes.py` 的三种 outcome 函数）。
  - 落地：在 A-1 报告中产出 by-semantic-class 拆分；前端 governance/analytics 后续消费。
- **A-3 PIT 特征仓库**
  - 交付物：每日快照每个信号的**连续特征**（非布尔阈值）+ `vintage_at`，作为 B 期训练矩阵。需 Alembic 迁移（新表 `signal_feature_snapshot`）+ 回填脚本。
  - 验收门：特征可按 `as_of` 点查、无未来泄漏（PIT 测试）。

### B 期 · 离线训练预测头

**目标**：在 A-3 特征仓库上训练**被残酷验证**的概率预测模型。

- 目标变量：扣成本后、固定 horizon（5/20 日）前向收益的**方向 + 幅度**，输出**等渗校准后的概率**。
- 模型：正则化线性（Ridge/Lasso/ElasticNet）+ 梯度提升树（LightGBM）；面板 + 合约固定效应；集成分歧大则弃权。
- 验证：**purged + embargoed walk-forward**（复用 `walk_forward`）+ **Deflated Sharpe + FDR**（复用 `multiple_testing`）+ **净成本**（复用 `slippage`）+ 锁箱样本外 + **校准曲线**（前端已有 `ReliabilityCurve`）。
- 交付物：模型 artifact（版本 + hash）+ 训练/验证报告（IR、准确率、校准、因子归因）。
- 验收门：锁箱样本外通过 Deflated-Sharpe 显著且净成本为正，否则结论为"无显著可交易 edge"（同样是合格产出）。

### C 期 · 受治理的影子顾问（依赖 P0-3）

**目标**：模型作为**非权威影子顾问**接入，先观察、不决策。

- 交付物：`backend/app/services/prediction/` —— 发出 `ForecastRecord`（概率 + 预期收益 + 不确定度 + `model_version` + `feature_hash` + 输入快照，完全可复现可追溯）。
- 接线：走现有 `shadow_tracker` 跑影子，`live_divergence` 监控回测—实盘背离；积累线上校准。
- **强制前置**：接通 P0-3 的"审批→生效"闭环——模型从影子升权威必须经人工治理审批。
- 验收门：影子运行 N 周，线上校准与回测一致；无凭据无法把模型升为权威输入。

### D 期 · 有界生产

**目标**：模型以**有界、可降级**方式影响生产。

- 影响封顶（例如只在 clamp 内调 `calibration_weight` 或 sizing tilt）；背离超阈值**自动降级回影子**；全程审计；定期重训走同一套闸。
- 验收门：影响幅度可配置且有上限；kill switch 可一键降级；审计链完整。

---

## 4. 里程碑与建议顺序

```
A-1 信号回测引擎  ──►  A-2 口径拆分  ──►  A-3 特征仓库  ──►  B 离线模型  ──►  C 影子顾问  ──►  D 有界生产
(本次开工)             │                                          ▲
                       │                                          │
P1 收口修复（并行）────┘                          P0-3 治理闭环（C 期前置，与 P1 并行）

P0-1/P0-2 安全项：任意对外部署前完成（与上面任意阶段并行，不阻塞本地研发）
```

- **关键判定点**：A-1/A-2 结果若显示"现有规则扣成本后无显著 edge"，则 B 期改为"先做特征工程找新因子"而非急于训模型——避免给噪声镀金。
- 本系统当前无认证，推断为本地/内部研发态，故 P0 安全项**不阻塞**研发推进，但**阻塞任何对外部署**。

---

## 5. 全局验收与质量门

任何进入生产链路的预测/规则变更必须同时满足：
1. **确定性可复现**：钉死 model/feature 版本与 PIT 快照，同输入同输出。
2. **净成本为正**：扣滑点后仍有正向 edge。
3. **统计显著**：Deflated Sharpe 过门 + FDR 校正后未被拒。
4. **校准良好**：可靠性曲线对齐，不只看准确率。
5. **经影子 → 治理**：先影子非权威运行，再人工审批升权威。

---

## 6. 风险登记

| 风险 | 缓解 |
|---|---|
| 模型过拟合（金融预测头号杀手） | purge/embargo + Deflated Sharpe + FDR + 锁箱；宁可结论为"无 edge" |
| Regime 漂移导致回测好看实盘打脸 | 影子 + live-divergence + 自动降级 |
| 把"模型说涨"当可交易 | 强制净成本门；不打赢滑点不算 hit |
| 治理闭环接通后被绕过 | `human_approved` 改令牌校验；审批主体来自认证 |
| 接通"审批→生效"引入未授权写入 | applier 全程 `@review_required` + 审批行令牌；migration + 回滚 |

---

## 7. 立即执行项（本次会话）

**A-1 信号回测引擎第一刀**：实现 `signal_backtest.py` + 测试，在现有 `SignalTrack` 历史上回答——**现有方向类信号扣掉滑点成本后，是否还有统计显著的方向预测 edge？** 纯函数 + 薄 DB loader，零迁移、零生产改动，复用现有统计护栏。这是整个预测路线"测真相"的地基，也是 B 期模型必须超越的 baseline。
