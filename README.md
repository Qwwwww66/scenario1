# SUMO 污水处理厂智能控制研究项目

## 项目概述

本项目使用 **Dynamita SUMO** 软件对 **AA/O 工艺污水处理厂** 进行动态仿真，并比较多种控制策略的优化效果：**静态控制（Static）**、**基于规则的控制（Rule-based）**、**贝叶斯优化（Bayesian Optimization, BO）**、**深度强化学习控制（DRL/DQN）**，以及 **贝叶斯优化+强化学习的混合控制（RL+BO）**。

---

## 目录结构

```
Scenario 1/
├── README.md                              # 本文件
├── AA'OA'.sumo                            # SUMO 污水处理厂仿真项目（主模型）
├── AA'OA' Knowledge Control.sumo           # SUMO 仿真项目（知识控制版本）
├── sim.dll                                # 编译后的仿真模型 DLL（从 .sumo 中解压）
├── init.scs                               # 仿真初始参数脚本
├── parameters.txt                         # 模型常量输入参数
├── episode_initial_state.xml              # 当前回合的初始状态文件
├── tmp_state.xml                          # 仿真结束后的临时状态保存
│
├── Static Control test.py                 # [测试] 静态控制策略（固定 DO/IMLR/Carbon）
├── Rule-based Control test.py             # [测试] 基于规则的控制策略
├── knowledge control setting.py           # [辅助] 根据进水流量生成规则控制设定值
├── Bayesian Optimization.py               # [训练+测试] 贝叶斯优化控制
├── RL Control train.py                    # [训练] DQN 强化学习模型训练
├── RL Control test.py                     # [测试] DQN 强化学习模型测试
├── RL+BO Control test.py                  # [测试] BO初始值 + DQN微调的混合控制
│
├── dynamita/                              # Dynamita SUMO Python API 模块
│   ├── scheduler.py                       # 仿真任务调度器（核心 API）
│   ├── tool.py                            # 工具函数（时间单位、XML读写、文件解压等）
│   ├── dmqclient.py                       # DMQ 消息队列客户端
│   ├── sumogui.py                         # SUMO GUI 相关
│   └── dmq_logs/                          # DMQ 运行日志
│
├── examples-22/                           # SUMO 示例项目参考代码
│   ├── analysis.py                        # 分析脚本
│   ├── dynamic_run.py                     # 动态运行示例
│   ├── mpsim.py / mpoptimization.py       # 多并行仿真和优化示例
│   └── ...                                # 其他示例文件
│
├── RL models/                             # 训练好的 DQN 模型权重（225个 .pth 文件）
│   └── model_ep{编号}.pth                 # 每24个回合保存一次模型
│
├── RL train and test data/                # 训练和测试数据
│   ├── train data.xlsx                    # DQN 训练数据（进水流量等）
│   ├── test data.xlsx                     # 通用测试数据
│   ├── test flow1.xlsx ~ test flow4.xlsx  # 4种不同流量场景的测试数据
│   └── rule_based_control_settings_flow1.xlsx  # 规则控制生成的设定值
│
├── dynamic flow/                          # 动态流量测试数据（备份）
│   ├── test flow1.xlsx ~ test flow4.xlsx  # 流量场景1-4
│   └── backup/                            # 备份文件
│
├── test results/                          # 所有控制策略的测试结果
│   ├── Static_Control_*/                  # 静态控制各场景结果
│   ├── Rule_based_Control_*/              # 规则控制各场景结果
│   ├── RL_Control_*/                      # DQN 控制各场景结果
│   ├── RL+BO_Control_*/                   # 混合控制各场景结果
│   └── *_sim_validation_*.xlsx           # 各策略的验证结果汇总
│
├── initial state/                         # 初始仿真状态文件
│   └── episode_initial_state.xml
│
└── Initial Action Points After BO.xlsx    # 贝叶斯优化后保存的初始动作点
```

---

## 仿真模型：AA/O 工艺

污水处理厂采用 **AA/O（厌氧-缺氧-好氧）工艺**，包含以下主要单元：

| 单元 | 符号 | 体积 (m³) | 说明 |
|------|------|-----------|------|
| CSTR | 反应器1 | 750 | 厌氧池 |
| CSTR2 | 反应器2 | 1,500 | 缺氧池 |
| CSTR3 | 反应器3 | 3,000 | 好氧池（曝气控制） |
| CSTR4 | 反应器4 | 1,500 | 后置缺氧池 |

**关键恒定参数：**
- 进水 COD：300 mg/L
- 进水 TKN：42 mg/L
- 进水流量 Q：17,280 m³/d（基准值）
- SRT1 控制：启用

---

## 控制变量

| 变量 | 范围 | 说明 |
|------|------|------|
| **DO (CSTR3_DOSP)** | 0.5 ~ 3.0 mg/L | 好氧池溶解氧设定值 |
| **IMLR (Q_IMLR)** | 17,280 ~ 69,120 m³/d | 内循环（混合液回流）流量 |
| **Carbon (Carbon_Q)** | 0 ~ 5 (碳源投加量) | 碳源（甲醇/乙酸）投加量 |

---

## 评估指标

仿真运行后计算以下关键指标：

- **EQI**（出水质量指数）：`(2*XTSS + TCOD + 30*SKN + 10*SNHx + 2*TBOD5) * Qeff / 1000`
- **AE**（曝气能耗）：与 kLa 和池容成正比
- **PE**（泵送能耗）：`0.004*Q_IMLR + 0.008*Q_RAS + 0.05*Q_WAS`
- **ME**（混合能耗）：与 kLa 和池容成正比（低曝气时）
- **OCI**（综合运行成本指数）：`AE + PE + ME + 5*SP`
- **OPEXplant_d**（日运营成本）：从 SUMO 成本模型直接输出
- **Power**（总功率）：`AE + PE`

**出水达标约束：**
- Eff_TCOD <= 40 mg/L
- Eff_SNHx（氨氮） <= 3 mg/L
- Eff_TN（总氮） <= 15 mg/L
- CSTR2_SNOx（缺氧池硝态氮） > 1 mg/L

---

## 控制策略对比

### 1. 静态控制（Static Control）
**文件**: `Static Control test.py`

固定控制参数，不做任何自适应调节：
- DO = 2.0 mg/L
- IMLR = 34,560 m³/d
- Carbon = 0

**用途**: 作为其他策略的基线对比。

---

### 2. 基于规则的控制（Rule-based Control）
**文件**: `Rule-based Control test.py`, `knowledge control setting.py`

初级工程师经验规则：根据进水流量分段设定 DO 和 IMLR：
- 低流量 (< 20,000 m³/d) → DO=1.5, IMLR=20,000
- 中流量 (20,000~40,000) → DO=2.0, IMLR=30,000
- 高流量 (> 40,000) → DO=3.0, IMLR=40,000

**用途**: 代表传统人工经验的自动化水平。

---

### 3. 贝叶斯优化（Bayesian Optimization）
**文件**: `Bayesian Optimization.py`

使用 **scikit-optimize** 的 `gp_minimize` 进行高斯过程贝叶斯优化：
- 搜索空间：DO ∈ [0.5, 3], IMLR ∈ [17,280, 69,120], Carbon ∈ [0, 5]
- 采集函数：Expected Improvement (EI)
- 每个回合：10 个初始点 + 10 次评估
- 目标函数：`OPEXplant_d + 超标惩罚项`
- 结果保存在 `Initial Action Points After BO.xlsx`

**用途**: 提供全局最优参数参考，作为 RL+BO 混合策略的初始解。

---

### 4. 深度强化学习（DRL / DQN）
**文件**: `RL Control train.py`（训练）, `RL Control test.py`（测试）

Deep Q-Network (DQN) 架构：
- **状态空间（6维）**: [进水流量, COD, TKN, DO当前值, IMLR当前值, Carbon当前值]
- **动作空间（7个离散动作）**:
  - 0/1: DO ± 0.5
  - 2/3: IMLR ± 10,000
  - 4/5: Carbon ± 0.5
  - 6: 保持不变
- **网络结构**: 两层全连接（6→30→7），ReLU激活
- **超参数**: ε=0.9 (decay 0.995→0.1), γ=0.9, LR=0.01, Memory=40, Batch=32
- **每回合**: 20步仿真（每步15分钟）
- **模型保存**: 每24个回合保存一次（共225个检查点）

**RL 模型路径**: `RL models/model_ep{episode}.pth`

---

### 5. 贝叶斯优化 + 强化学习混合控制（RL+BO）
**文件**: `RL+BO Control test.py`

先用贝叶斯优化的结果作为初始状态（DO, IMLR, Carbon），然后使用训练好的 DQN 模型进行 20 步微调优化。

**用途**: 结合全局优化（BO）与在线自适应调节（DQN）的优势。

---

## 如何使用

### 环境要求
- Python 3.8+
- Dynamita SUMO 24（已安装并注册）
- 依赖库：`torch`, `numpy`, `pandas`, `scipy`, `scikit-optimize`, `matplotlib`, `seaborn`, `openpyxl`

### 运行步骤

1. **提取 DLL 和参数**（脚本自动完成）：
   ```python
   dtool.extract_dll_from_project("AA'OA'.sumo", "sim.dll")
   dtool.extract_parameters_from_project("AA'OA'.sumo", ".", "init.scs", "")
   ```

2. **训练 DQN 模型**：
   ```bash
   python "RL Control train.py"
   ```

3. **运行贝叶斯优化**：
   ```bash
   python "Bayesian Optimization.py"
   ```

4. **测试各控制策略**（使用不同流量场景 flow1~4）：
   ```bash
   python "Static Control test.py"
   python "Rule-based Control test.py"
   python "RL Control test.py"
   python "RL+BO Control test.py"
   ```

5. **结果查看**：所有测试结果保存在 `test results/` 中，按策略和场景分类。

---

## 数据流

```
进水流量数据（test flow*.xlsx）
    │
    ├──→ Static Control       → DO/IMLR/Carbon 固定值      → SUMO仿真 → 出水指标 + 成本
    ├──→ Rule-based Control   → 按流量分段查表              → SUMO仿真 → 出水指标 + 成本
    ├──→ Bayesian Optimization→ gp_minimize 搜索最优参数    → SUMO仿真 → OPEX + 惩罚
    ├──→ RL Control           → DQN 自适应选择动作          → SUMO仿真 → 奖励函数
    └──→ RL+BO Control        → BO初始 + DQN微调            → SUMO仿真 → 奖励函数
                                      │
                                      ▼
                               test results/（Excel 报告）
```

---

## 文件修改日期概要

| 文件 | 最后修改 | 说明 |
|------|----------|------|
| `AA'OA'.sumo` | 2025-05-20 | 工厂模型 |
| `Bayesian Optimization.py` | 2025-06-15 | BO 优化 |
| `RL Control train.py` | 2026-04-30 | RL 训练 |
| `RL Control test.py` | 2025-06-27 | RL 测试 |
| `RL+BO Control test.py` | 2025-06-27 | 混合控制 |
| `Static Control test.py` | 2025-07-20 | 静态控制 |
| `Rule-based Control test.py` | 2025-08-07 | 规则控制 |
| `sim.dll` | 2026-04-30 | 最新编译模型 |
