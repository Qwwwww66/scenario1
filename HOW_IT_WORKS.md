# SUMO 仿真代码详细运行机制

## 整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  你的 Python 脚本（如 Static Control test.py）                        │
│    │                                                                 │
│    ├─ ① 准备阶段：从 .sumo 项目文件解压 DLL 和参数                     │
│    ├─ ② 注册回调：告诉 SUMO 引擎"数据来了调这个函数"                    │
│    ├─ ③ 提交任务：通过 schedule() 发送命令 + 变量列表                  │
│    ├─ ④ 等待结束：轮询 scheduledJobs 直到为 0                         │
│    └─ ⑤ 读取结果：从 jobData dict 中取出累计的数据                     │
│         │                                                             │
│         ▼                                                             │
│   dynamita.scheduler (Python 封装, scheduler.py)                      │
│    │  - SumoScheduler 类                                              │
│    │  - 把 Python 回调包装成 C 函数指针                                │
│    │  - 把 commands/variables 编码为字符串传给 DLL                     │
│         │                                                             │
│         ▼                                                             │
│   sumoscheduler.dll (C/C++ 原生 DLL)                                  │
│    │  - 管理仿真任务队列                                               │
│    │  - 加载 sim.dll 模型                                              │
│    │  - 调度 SUMO 引擎执行                                             │
│    │  - 通过回调将消息和数据传回 Python                                 │
│         │                                                             │
│         ▼                                                             │
│   sim.dll + SUMO Core (仿真引擎)                                      │
│     - 执行污水处理动态仿真                                             │
│     - 按 DataComm 间隔输出监测变量                                     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 逐步拆解（以 Static Control test.py 为例）

### 步骤 0：导入依赖

```python
import dynamita.scheduler as ds    # 仿真调度器（核心）
import dynamita.tool as dtool      # 工具函数（时间单位、解压、XML解析）
import time
import pandas as pd
```

`dynamita` 文件夹就在工作区中，是纯 Python 模块。其中：
- **`scheduler.py`**：全局单例 `ds.sumo`，管理所有仿真任务
- **`tool.py`**：提供时间常量（`minute`, `hour`, `day`）、XML 读写、从 `.sumo` (zip) 解压文件

---

### 步骤 1：从 SUMO 项目解压 DLL 和参数

```python
sumo_project = "AA'OA'.sumo"
model = "sim.dll"

# 从 .sumo（本质是 zip 文件）中提取 sumoproject.dll，重命名为 sim.dll
dtool.extract_dll_from_project(sumo_project, model)

# 从 .sumo 中提取 parameters.txt，读取并生成 init.scs 脚本
init_file = "init.scs"
dtool.extract_parameters_from_project(sumo_project, ".", "init.scs", "")
```

**`extract_dll_from_project` 做了什么**（`tool.py:194-197`）：

```python
def extract_dll_from_project(project, path_to):
    with zipfile.ZipFile(project, 'r') as zf:       # .sumo 就是 .zip
        with open(path_to, "wb") as f:
            f.write(zf.read("sumoproject.dll"))      # 把里面的 DLL 解出来
```

**`extract_parameters_from_project` 做了什么**（`tool.py:205-246`）：

读取 `.sumo` 内的 `parameters.txt`，解析 `[CONSTANT INPUT]` 段，生成 `init.scs` 脚本文件：

```scs
set Sumo__Plant__param__SRT1_control 1;
set Sumo__Plant__Influent__param__Q 17280;
set Sumo__Plant__Influent__param__TCOD 300;
set Sumo__Plant__CSTR__param__L_Vtrain 750;
set Sumo__Plant__CSTR2__param__L_Vtrain 1500;
set Sumo__Plant__CSTR3__param__L_Vtrain 3000;
set Sumo__Plant__Sideflowdivider__param__Qpumped_target 51840;
set Sumo__Plant__CSTR4__param__L_Vtrain 1500;
set Sumo__Plant__CSTR__param__Qair_NTP 0;
set Sumo__Plant__CSTR2__param__Qair_NTP 0;
set Sumo__Plant__CSTR4__param__Qair_NTP 0;
```

这些是**模型的固定结构参数**，每次仿真都要先执行一遍。

---

### 步骤 2：注册回调函数

```python
ds.sumo.setParallelJobs(1)                        # 单任务串行执行
ds.sumo.message_callback = msg_callback            # 注册消息回调
ds.sumo.datacomm_callback = data_callback          # 注册数据回调
```

这两个回调是**整个数据采集的核心机制**。

#### 消息回调 `msg_callback`

```python
def msg_callback(job, msg):
    print(f"#{job} {msg}")                  # 打印消息内容
    save_finished = msg.startswith("530045") # 530045 是"保存完成"的状态码
    jobData = ds.sumo.getJobData(job)       # 获取与此 job 关联的 dict

    if ds.sumo.isSimFinishedMsg(msg):       # 消息以 "530004" 开头 = 仿真结束
        dtool.log_print("Sending save state...")
        jobData["wait_for_save"] = True
        ds.sumo.sendCommand(job, "save tmp_state.xml;")  # 发送保存状态命令

    if jobData["wait_for_save"] and save_finished:
        dtool.log_print("Save state finished, terminating Sumo.")
        jobData["wait_for_save"] = False
        ds.sumo.finish(job)                 # 通知调度器任务结束
```

SUMO 引擎在关键节点会发送消息，以数字状态码开头：
- `530004`：仿真运行结束
- `530045`：状态保存完成
- 其他消息：日志、警告、错误等

#### 数据回调 `data_callback`

```python
def data_callback(job, data):
    jobData = ds.sumo.getJobData(job)  # 取出关联的存储 dict
    jobData["t"].append(data["Sumo__Time"] / dtool.day)
    jobData["Q_Inf"].append(data["Sumo__Plant__Influent__Q"])
    jobData["Q_Eff"].append(data["Sumo__Plant__Effluent__Q"])
    jobData["Eff_TCOD"].append(data["Sumo__Plant__Effluent__TCOD"])
    jobData["Eff_SNHx"].append(data["Sumo__Plant__Effluent__SNHx"])
    jobData["Eff_TN"].append(data["Sumo__Plant__Effluent__TN"])
    jobData["OPEXplant_d"].append(data["Sumo__Plant__CostCenter__OPEXplant_d"])
    # ... 更多变量
```

每当仿真时间到达 `DataComm` 设定的间隔，SUMO 就回调此函数一次。`data` 参数是一个 dict，格式为：

```python
{
    "Sumo__Time": 900000,
    "Sumo__Plant__Effluent__TCOD": 25.3,
    "Sumo__Plant__Effluent__SNHx": 1.2,
    ...
}
```

**注意**：只包含 `schedule()` 时 `variables` 列表中声明的变量。没声明的不会传回。

---

### 步骤 3：调度仿真任务 `schedule()`——核心

```python
job = ds.sumo.schedule(
    model,          # ① 模型 DLL 路径
    commands=[      # ② 仿真指令序列（字符串列表）
        f"execute {init_file}",                                # 先执行 init.scs（固定参数）
        "load episode_initial_state.xml",                      # 加载上次保存的状态
        "maptoic",                                             # 将状态映射为初始条件
        f"set Sumo__Plant__Influent__param__TCOD {300}",       # 设置进水 COD
        f"set Sumo__Plant__Influent__param__Q {Q_inf}",        # 设置进水流量（动态变化！）
        f"set Sumo__Plant__Influent__param__TKN {42}",         # 设置进水 TKN
        f"set Sumo__Plant__Sideflowdivider__param__Qpumped_target {Q_IMLR}",  # 设置 IMLR
        f"set Sumo__Plant__CSTR3__param__DOSP {CSTR3__DOSP}",  # 设置 DO 设定值
        f"set Sumo__Plant__Carbon1__param__Q {Carbon}",        # 设置碳源投加量
        f"set Sumo__StopTime {15*dtool.minute}",               # 仿真 15 分钟
        f"set Sumo__DataComm {15*dtool.minute}",               # 每 15 分钟回传一次数据
        "mode dynamic",                                        # 切换到动态模式
        "start"                                                # 启动！
    ],
    variables=[     # ③ 声明要采集的变量（SUMO 内部路径名）
        "Sumo__Time",
        "Sumo__Plant__Influent__Q",
        "Sumo__Plant__Effluent__Q",
        "Sumo__Plant__Effluent__TCOD",
        "Sumo__Plant__Effluent__SNHx",
        "Sumo__Plant__Effluent__TN",
        "Sumo__Plant__CostCenter__OPEXplant_d",
        "Sumo__Plant__Effluent__TBOD_5",
        "Sumo__Plant__Effluent__SNOx",
        "Sumo__Plant__Effluent__SKN",
        "Sumo__Plant__Effluent__XTSS",
        "Sumo__Plant__Pipe9__Q",         # IMLR 实际流量
        "Sumo__Plant__Pipe12__Q",        # RAS 回流流量
        "Sumo__Plant__Pipe13__Q",        # WAS 排泥流量
        "Sumo__Plant__Pipe13__XTSS",     # 排泥浓度
        "Sumo__Plant__CSTR__kLaGO2",     # CSTR1 氧传质系数
        "Sumo__Plant__CSTR2__kLaGO2",    # CSTR2 氧传质系数
        "Sumo__Plant__CSTR2__SNOx",      # CSTR2 硝态氮
        "Sumo__Plant__CSTR3__kLaGO2",    # CSTR3 氧传质系数
        "Sumo__Plant__CSTR4__kLaGO2",    # CSTR4 氧传质系数
    ],
    jobData={        # ④ 关联的数据存储容器
        "t": [],
        "Q_Inf": [],
        "Q_Eff": [],
        # ...
        "wait_for_save": False,
        ds.sumo.persistent: True  # 标记为持久化，cleanup 时不删除
    }
)
```

`scheduler.py:132-137` 中的实际执行：

```python
def schedule(self, model, commands, variables, blockDatacomm=False, jobData=None):
    varstr = "|".join(variables)        # 变量名用 | 拼接
    # 命令用 ; 拼接，全部编码为 UTF-8，传给 C DLL
    id = self._scheduler.schedule(
        model.encode("utf8"),
        (";".join(commands)).encode("utf8"),
        varstr.encode("utf8"),
        int(blockDatacomm)
    )
    self.jobData[id] = jobData         # jobData 用 job ID 关联
    self.scheduledJobs = self._scheduler.getScheduledJobs()
    return id
```

**`commands` 中的关键指令解释**：

| 指令 | 作用 |
|------|------|
| `execute init.scs` | 执行初始参数脚本（设定反应器体积等固定参数） |
| `load episode_initial_state.xml` | 加载之前保存的系统状态（各反应器浓度等） |
| `maptoic` | 将加载的状态映射为当前仿真的初始条件 |
| `set 变量路径 值` | 覆盖/设置任意模型参数——**这是改变输入的入口** |
| `set Sumo__StopTime 900000` | 设置仿真停止时间（毫秒），15分钟 = 900,000ms |
| `set Sumo__DataComm 900000` | 设置数据回传间隔，同时也是 `data_callback` 的触发频率 |
| `mode dynamic` | 切换到动态仿真模式 |
| `start` | 开始执行仿真 |

**`set` 指令的执行顺序很重要**：`execute init.scs` 先设置默认值，后续的 `set` 会覆盖。如果 `set` 放在 `execute` 之前则会被覆盖掉。

---

### 步骤 4：等待仿真结束

```python
while ds.sumo.scheduledJobs > 0:
    time.sleep(0.1)   # 每 0.1 秒检查一次，避免忙等待
```

`schedule()` 是非阻塞的——调用后立即返回，仿真在后台运行。通过轮询 `scheduledJobs` 属性判断是否还在运行。

仿真运行时，回调函数在后台被触发：
1. 每到 `DataComm` 时间点 → `data_callback` 被调用 → 数据追加到 `jobData` 列表中
2. 仿真时间到达 `StopTime` → `msg_callback` 收到 `"530004..."` → 发送 `save` 命令
3. 保存完成 → `msg_callback` 收到 `"530045..."` → 调用 `finish()` → `scheduledJobs` 归零

---

### 步骤 5：读取结果

仿真结束后，数据都在 `jobData` 中：

```python
# 遍历所有 job 的数据（通常只有一个）
for jd in ds.sumo.jobData.values():
    Q_inf = jd["Q_Inf"][-1]         # 进水流量系列的最后一个值
    Eff_TCOD = jd["Eff_TCOD"][-1]   # 出水 COD 终值
    Eff_SNHx = jd["Eff_SNHx"][-1]   # 出水氨氮终值
    Eff_TN = jd["Eff_TN"][-1]       # 出水总氮终值
    OPEXplant_d = jd["OPEXplant_d"][-1]  # 日运营成本终值
    # ... 更多变量
```

因为 `DataComm` 设成了和 `StopTime` 相同的值（15分钟），所以每个 job 只触发一次数据回调，列表中只有一个元素。如果 `DataComm` 设得更短（如 1 分钟），列表中会有多个时间点的数据。

然后计算衍生指标：

```python
# 出水质量指数
EQI = (2*Eff_XTSS + Eff_TCOD + 30*Eff_SKN + 10*Eff_SNHx + 2*Eff_TBOD_5) * Q_Eff / 1000

# 曝气能耗
AE = (DO_sat / (1.8*1000)) * (V_CSTR*kLa_CSTR + V_CSTR2*kLa_CSTR2 + V_CSTR3*kLa_CSTR3 + V_CSTR4*kLa_CSTR4)

# 泵送能耗
PE = 0.004 * Q_IMLR + 0.008 * Q_RAS + 0.05 * Q_WAS

# 综合运行成本指数
OCI = AE + PE + ME + 5*SP
```

最后清理：

```python
ds.sumo.cleanup()  # 清空 jobData，释放 DLL 内部资源
```

---

### 步骤 6：状态传递（回合衔接）

每回合结束后：

```python
os.replace("tmp_state.xml", "episode_initial_state.xml")
```

`tmp_state.xml` 是在 `msg_callback` 中通过 `ds.sumo.sendCommand(job, "save tmp_state.xml;")` 保存的。它包含了仿真结束时的全部系统状态（各反应器的 COD、氨氮、硝态氮浓度，污泥浓度，溶解氧等）。

下一次循环时，`commands` 中的 `load episode_initial_state.xml` 会加载这个状态，确保仿真从上一次结束的状态继续。这就是**时序连续性**的实现方式。

---

## 最小可运行示例

以下是一个不依赖 RL/Excel 的最简示例，展示了核心循环：

```python
import os
import shutil
import dynamita.scheduler as ds
import dynamita.tool as dtool
import time

# ========== 回调函数（必须定义） ==========

def data_callback(job, data):
    """仿真数据回传时触发"""
    jd = ds.sumo.getJobData(job)
    for key in jd:
        if key in data:
            jd[key].append(data[key])

def msg_callback(job, msg):
    """仿真消息回传时触发"""
    print(f"[SUMO] {msg}")
    jd = ds.sumo.getJobData(job)
    if ds.sumo.isSimFinishedMsg(msg):
        ds.sumo.sendCommand(job, "save tmp_state.xml;")
    if msg.startswith("530045"):  # 保存完成
        ds.sumo.finish(job)

# ========== 仿真运行函数 ==========

def run_sim(model, init_file, Q_inf, DO_sp, Q_imlr, carbon):
    """运行一次 15 分钟的仿真，返回关键出水指标"""
    job = ds.sumo.schedule(
        model,
        commands=[
            f"execute {init_file}",
            "load episode_initial_state.xml",
            "maptoic",
            f"set Sumo__Plant__Influent__param__Q {Q_inf}",
            f"set Sumo__Plant__CSTR3__param__DOSP {DO_sp}",
            f"set Sumo__Plant__Sideflowdivider__param__Qpumped_target {Q_imlr}",
            f"set Sumo__Plant__Carbon1__param__Q {carbon}",
            f"set Sumo__StopTime {15 * dtool.minute}",
            f"set Sumo__DataComm {15 * dtool.minute}",
            "mode dynamic",
            "start"
        ],
        variables=[
            "Sumo__Plant__Effluent__TCOD",
            "Sumo__Plant__Effluent__SNHx",
            "Sumo__Plant__Effluent__TN",
            "Sumo__Plant__Effluent__XTSS",
            "Sumo__Plant__Effluent__TBOD_5",
            "Sumo__Plant__Effluent__SKN",
            "Sumo__Plant__Effluent__Q",
            "Sumo__Plant__Pipe9__Q",
            "Sumo__Plant__Pipe12__Q",
            "Sumo__Plant__Pipe13__Q",
            "Sumo__Plant__Pipe13__XTSS",
            "Sumo__Plant__CostCenter__OPEXplant_d",
        ],
        jobData={
            "Eff_TCOD": [], "Eff_SNHx": [], "Eff_TN": [],
            "Eff_XTSS": [], "Eff_TBOD_5": [], "Eff_SKN": [],
            "Q_Eff": [], "Q_IMLR": [], "Q_RAS": [], "Q_WAS": [],
            "WAS_XTSS": [], "OPEXplant_d": [],
            ds.sumo.persistent: True
        }
    )

    # 等待仿真结束
    while ds.sumo.scheduledJobs > 0:
        time.sleep(0.1)

    # 读取结果
    for jd in ds.sumo.jobData.values():
        TCOD = jd["Eff_TCOD"][-1]
        SNHx = jd["Eff_SNHx"][-1]
        TN   = jd["Eff_TN"][-1]
        break

    ds.sumo.cleanup()
    return TCOD, SNHx, TN

# ========== 主程序 ==========

if __name__ == "__main__":
    # 1. 准备模型文件
    dtool.extract_dll_from_project("AA'OA'.sumo", "sim.dll")
    dtool.extract_parameters_from_project("AA'OA'.sumo", ".", "init.scs", "")

    # 2. 注册回调
    ds.sumo.setParallelJobs(1)
    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    # 3. 准备初始状态
    shutil.copyfile("initial state/episode_initial_state.xml",
                    "episode_initial_state.xml")

    # 4. 运行 3 个回合，动态改变输入
    for ep in range(3):
        # 每回合改变进水流量和 DO 设定
        Q_inf  = 17280 + ep * 5000    # 流量逐步增大
        DO_sp  = 1.5 + ep * 0.5       # DO 逐步提高
        Q_imlr = 34560
        carbon = 0

        TCOD, SNHx, TN = run_sim("sim.dll", "init.scs",
                                 Q_inf, DO_sp, Q_imlr, carbon)

        print(f"回合{ep} | Q={Q_inf} DO={DO_sp} | "
              f"出水COD={TCOD:.1f} 氨氮={SNHx:.2f} 总氮={TN:.1f}")

        # 状态传递
        os.replace("tmp_state.xml", "episode_initial_state.xml")
```

---

## 关键概念速查

### `set` 命令中变量路径的命名规则

```
Sumo__Plant__CSTR3__param__DOSP
│     │      │       │      └── 参数名（溶解氧设定值）
│     │      │       └── param = 这是一个参数（非状态变量）
│     │      └── CSTR3 = 第三个反应器
│     └── Plant = 工艺单元组
└── Sumo = 模型根命名空间
```

状态变量（无 `param`）：

```
Sumo__Plant__Effluent__TCOD     → 出水 COD 浓度
Sumo__Plant__CSTR2__SNOx       → CSTR2 中硝态氮浓度
Sumo__Plant__CSTR3__kLaGO2     → CSTR3 氧传质系数
```

### 时间单位（来自 `tool.py`）

```python
msec   = 1
sec    = 1000          # 1000 毫秒
minute = 60 * sec      # 60000
hour   = 60 * minute   # 3600000
day    = 24 * hour     # 86400000
```

所有 `StopTime`、`DataComm` 都以**毫秒**为单位。

### DataComm 的作用

- 控制 SUMO 引擎回传数据的频率
- 每次回传触发 `data_callback`
- 如果设成和 StopTime 一样 → 只回传一次（仿真结束时）
- 如果设得更短 → 多次回传，可以绘制时间序列曲线

### 状态文件的本质

`episode_initial_state.xml` 是 SUMO 的完整状态快照，包含模型中所有变量的当前值。格式大致如下：

```xml
<systemstate modelHash="...">
    <real name="Sumo__Plant__CSTR__SCOD">45.2</real>
    <real name="Sumo__Plant__CSTR__SSNH">3.1</real>
    <!-- 数百个变量 ... -->
</systemstate>
```

不需要手动编辑——只需用 `load` 加载、用 `save` 保存、用 `maptoic` 映射即可。

---

## 完整数据流总结

```
Excel 进水数据（或代码中硬编码的值）
    │
    │  读取这一回合的进水流量、COD、TKN
    │
    ├─→ 通过 f"set Sumo__... {value}" 命令注入参数
    │
    ├─→ schedule() 提交任务给 C DLL
    │       │
    │       ├─ commands 字符串（所有 set/load/mode/start 指令）
    │       └─ variables 列表（声明要采集哪些数据）
    │
    ▼
SUMO 引擎执行仿真（15 分钟动态模拟）
    │
    │  DataComm 时间点到达 → 回调 data_callback(job, data_dict)
    │       │
    │       └─ 将 data_dict 中的值追加到 jobData 列表
    │
    ▼
仿真结束 → msg_callback 收到 530004 → 保存状态 → 收到 530045 → finish()
    │
    ▼
scheduledJobs 归零 → 轮询结束 → 从 jobData 取最后一条数据
    │
    ▼
计算衍生指标（EQI、OCI、Power、Reward）
    │
    ▼
os.replace("tmp_state.xml", "episode_initial_state.xml")
    │
    └─→ 下一回合的 load 加载此文件，状态连续
```
