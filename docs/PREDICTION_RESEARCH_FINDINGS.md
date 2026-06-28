# Zeus 预测能力研究结论

> 版本: 1.0 | 日期: 2026-06-28 | 关联: `docs/PREDICTION_AND_HARDENING_PLAN.md`（实施计划）
> 状态: Track 2 研究阶段收口。**反转因子已验证并定稿为生产信号；carry 因子被证明有前景但卡在数据上，未上生产。**

---

## 0. 一句话结论

**单品种方向预测 = 不行**（朴素价格规则在大样本扣成本回测下无 edge）；但**横截面 = 行**——一个经样本内 + 样本外双重验证、扣成本仍显著的商品**横截面反转/价值因子**，是 Zeus 真实的预测优势。它现已作为受治理的影子信号接入完整生命周期。第二个因子 **carry（期限结构）** 被证明是真实、稳健的新维度，但受限于可获取的分合约数据（仅 17 个 SHFE 品种）无法跨过显著性闸门——**一次数据解锁即可转正**。

---

## 1. 方法论：先让真相可测

所有结论都建立在一套严格的回测基础设施上（这是本研究的持久资产，可用于检验任何未来想法）：

| 模块 | 作用 |
|---|---|
| `backtest/replay.py` | 历史回放器：PIT 模式逐日重放信号（49 品种 / 16 年主连历史） |
| `backtest/spread_replay.py` | 相对价值（价差）回测 |
| `backtest/roll_adjust.py` | 换月复权（分合约 dominant-by-OI，链各自收益），剥离 roll 伪迹 |
| `backtest/cross_sectional_ic.py` | 横截面 IC 探针（Spearman 秩 IC，对 roll 幅度伪迹稳健） |
| `backtest/xs_reversal.py` | 横截面多空组合回测（dollar-neutral，扣换手成本） |
| `backtest/walk_forward_xs.py` | 子区间一致性 + 滚动自适应样本外验证 |
| `backtest/multiple_testing.py` | **Deflated Sharpe 闸门**：z > 1.0 **且** p < 0.05，对试验次数与样本长度去偏 |
| `backtest/carry.py` | 期限结构 carry 因子（近月/次月年化展期收益） |

**核心纪律**：任何"看起来有 edge"的结果，都要过换月复权 + Deflated Sharpe + 样本外三关。本研究里这套纪律反复把表面 edge 打回非 edge——这正是它的价值。

---

## 2. 测了什么，判了什么

| 假设 | 方法 | 结论 |
|---|---|---|
| 朴素方向动量 / price_gap | 16 年 / 15968 信号 PIT 回放 | ❌ ~49% 胜率，~0% 净收益，各 horizon 均不过闸 |
| 相对价值价差均值回归 | 12 对、|z|>2 反转、换月复权验真 | ❌ 原始看似显著（Deflated 3.29）但**换月复权后塌掉**——是 roll 伪迹 |
| **横截面反转/价值** | 49 品种、按 60-120d 动量排名多空 | ✅ **验证通过**（见 §3） |
| 多因子组合（反转+价值+低波） | 等权 z-score 合成 | ❌ 不如单 mom_120——价值/低波太相关，稀释强因子 |
| 持仓量（OI）因子 | OI 变化 / 价-OI 背离 IC | ❌ 与反转正交但 IC 弱且符号不稳——正交但无预测力 |
| **carry（期限结构）** | 17 SHFE 品种、近月/次月展期收益 | 🟡 **真因子但卡数据**（见 §4） |

---

## 3. 生产信号：横截面反转（已验证、已定稿）

### 3.1 验证结果

- **样本内**（49 品种、2010-2026、月度调仓、扣 5bp/持仓成本）：mom_120 k=5 → **+23.3% 年化净收益、62% 胜率、Sharpe 1.05、Deflated Sharpe 2.42（显著）**；mom_60 与 k=10 同样过闸。
- **样本外**（滚动自适应 walk-forward：仅用过去窗口选信号，交易下一段未见数据）：k=10 → **+17.2% 年化净、65.5% 胜率、OOS Sharpe 0.94、Deflated Sharpe 2.06、p=0.020（显著）**。
- **稳健性**：4 个日历子区间全为正（Sharpe 0.35-1.59），跨 quantile（k=5/10）与 lookback（60/120d）稳定，gross≈net（成本可承受），Spearman-IC + 腿收益裁剪排除 roll 伪迹。

这是整个调查里**第一个真实、统计显著、扣成本存活**的 edge，与商品横截面价值/反转文献一致（Asness et al.）。**Zeus 真正的"预测"活在横截面（品种排名），不在单品种方向。**

### 3.2 生产信号规格

代码：`app/services/prediction/cross_sectional.py`（`generate_cross_sectional_forecast`）

| 参数 | 值 | 说明 |
|---|---|---|
| `MODEL_VERSION` | `xs_reversal/1.0` | 钉死版本，可复现 |
| `DEFAULT_LOOKBACK` | 120 | 样本外验证最稳的 lookback |
| `DEFAULT_K` | 10 | ~分位腿，OOS 显著的配置 |
| `DEFAULT_HORIZON` | 21 | 月度 |
| 持仓 | 做多 bottom-k（输家）/ 做空 top-k（赢家），dollar-neutral | 反转 |

每次输出一条确定性、point-in-time 的 `ForecastRecord`，带 `feature_hash`（输入指纹）用于审计/复现。`decision_grade` **默认恒为 False（咨询/影子）**——服务永不直接写生产交易决策。

### 3.3 受治理生命周期（已建成）

```
emit（每日影子）→ shadow score（自评展期收益）→ governance 提案
  → 人工审批 → authoritative（有界权重）→ live-divergence 监控 → 自动降级
```

- 影子轨道在生产管线里**复现了回测**：165 条已结算预测 → +17.6% 年化、63% 胜率、Deflated 3.27、全部 decision_grade=False。
- 有界影响（`production/production.py`）：per-symbol + 总敞口封顶；非 authoritative 预测返回空权重（模型错误不会炸账户）。
- 自动降级（`prediction/divergence.py`）：authoritative 信号的实盘 Sharpe/回撤破线 → 单边 kill switch，重新提升仍走治理。

---

## 4. carry 因子：被证明有前景，卡在数据上

代码：`app/services/backtest/carry.py` + CLI `run_carry_probe`（IC）/ `run_carry_backtest`（扣成本多空）

### 4.1 数据约束

| 数据源 | 分合约可用性 |
|---|---|
| Tushare `fut_daily` | ❌ 无权限（`code=40203`，需账户积分升级） |
| AKShare SHFE `get_futures_daily` | ✅ 通 |
| AKShare DCE/CZCE | ❌ 端点挂了 |

→ 只能在 **17 个 SHFE 品种**上做首测（carry 需近月/次月分合约）。

### 4.2 结果

- **IC**：carry 横截面 IC = **+0.091 (t=12.8) @20d、+0.107 (t=15.3) @60d**，随 horizon 单调上升（慢因子签名），与 mom_120 反转相关性仅 **+0.258（基本正交，是个新维度）**。但 t 值被自相关夸大，须看回测。
- **16 年扣成本多空回测**（2010-2026、192 个月、10bp 往返、Deflated 去偏 12 次试验）：全截面排名加权 carry → **+0.45%/月、63% 胜率、Sharpe 0.76、Deflated z=1.21、p=0.114**。
- **闸门状态**：**过了 Sharpe 量级线（z=1.21>1.0），但差在 p<0.05（需 z>1.645，约差 36%）**。
- **关键稳健性**：carry 在全部 4 个子区间为正，**包括 2014-2017 大宗熊市**（Sharpe +1.39/+0.37/+0.74/+0.72）——**不是 2020-2021 牛市伪迹**。walk-forward 样本外一直选 carry 而非反转。

### 4.3 为什么没转正：breadth

基本定律 **IR ≈ IC·√breadth**。17 个品种的 cross-section 太薄；排名加权把 Deflated 从 0.49 抬到 1.21，证明卡点就是品种数。**全 49 品种（√(49/17)=1.7× breadth → Sharpe ~1.3）极大概率过闸**，且能和反转组成正交多因子。

→ **carry 没上生产（治理正确——未过闸）。** carry 的显著性与上线都堵在同一件事：**全市场分合约数据**（最干净的解锁 = Tushare `fut_daily` 升级）。

---

## 5. 已知局限

- 单一数据源（49 个 CN 商品 / AKShare 主连）；live 摩擦高于建模的 5bp/持仓。
- roll 偏差用裁剪处理（衰减而非夸大；Spearman-IC 对其稳健）。
- 反转有**调仓相位敏感**（mom_120 k=10 Sharpe 在不同月内相位 0.81-1.11）——回测 Sharpe 有置信带；live 按固定调度发出，相位固定，非 bug，但建议未来做相位平均增稳。
- 反转是公开因子（容量/拥挤是 live 风险）。

---

## 6. 待决策与后续

研究阶段在 2026-06-28 收口，决策：**先收口已验证的反转，carry 记为待数据。**

后续方向（按 EV）：

1. **解锁全市场分合约数据**（升级 Tushare `fut_daily`）→ 建全 49 品种 carry + carry/反转多因子。**最高 EV**：极大概率让 carry 转正，并把组合 IR 抬到单因子之上。
2. **反转相位平均增稳**：用现有数据即可，让生产信号对调仓时点更鲁棒。
3. （已默认在跑）反转影子轨道持续累积 live track，为正式提升积累证据。
