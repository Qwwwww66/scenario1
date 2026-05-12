# SUMO 工作区全部脚本逐行解析

---

## 目录结构总览

```
Scenario 1/
├── dynamita/                        # [底层库] SUMO Python API
│   ├── tool.py                      #   工具函数（时间单位、XML/TSV读写、文件解压）
│   ├── scheduler.py                 #   仿真调度器（核心：提交任务、回调、数据管理）
│   ├── dmqclient.py                 #   DMQ 消息队列客户端（进程间通信）
│   └── sumogui.py                   #   通过 DMQ 控制 SUMO GUI 界面
│
├── knowledge control setting.py     # [辅助] 基于进水流量生成规则控制设定值
├── Bayesian Optimization.py         # [优化] 贝叶斯优化寻找最优控制参数
├── RL Control train.py              # [训练] 深度强化学习 DQN 训练
├── RL Control test.py               # [测试] DQN 模型测试评估
├── RL+BO Control test.py            # [测试] 贝叶斯优化 + DQN 混合控制
├── Static Control test.py           # [测试] 静态固定参数控制（基线）
├── Rule-based Control test.py       # [测试] 基于规则的专家控制
│
├── parameters.txt                   # SUMO 模型的常量输入参数
├── init.scs                         # 仿真初始化脚本
├── sim.dll                          # 编译后的仿真模型 DLL
├── AA'OA'.sumo                      # SUMO 项目文件（zip格式）
│
├── RL models/                       # 训练好的 DQN 模型权重
├── RL train and test data/          # 训练和测试数据集
├── dynamic flow/                    # 动态流量测试场景
├── test results/                    # 各策略测试结果
├── initial state/                   # 初始状态文件
└── examples-22/                     # SUMO 官方示例代码
```

---

# 第一部分：底层库 dynamita/

---

## 1. `dynamita/tool.py` — 工具函数库

### 1.1 时间常量定义

```python
msec   = 1
sec    = 1000           # 1 秒 = 1000 毫秒
minute = 60 * sec       # 1 分钟 = 60000 毫秒
hour   = 60 * minute    # 1 小时 = 3,600,000 毫秒
day    = 24 * hour      # 1 天 = 86,400,000 毫秒
week   = 7 * day        # 1 周
```

所有 SUMO 仿真的 `StopTime` 和 `DataComm` 都以毫秒为单位，这些常量方便代码中编写。

### 1.2 数据类定义

**`OPCEntry`**：OPC 通信映射条目，描述一个 OPC 变量与 SUMO 变量的对应关系。包含 IO 方向、数据类型、单位、缩放因子等字段。用于工厂实际 PLC 与 SUMO 模型的连接。

**`VariableEntry`**：存放 SUMO 变量的元信息。包含变量名、类型（REAL/INT）、维度、当前值。用在 XML 状态文件读写中。

**`MappingEntry`**：变量名映射关系。`from_var` → `to_var`，乘以 `multi` 倍率。用于不同命名体系之间的转换。

### 1.3 `convert_to_data(s: str)` — 智能类型转换

```python
def convert_to_data(s: str):
    if s == "" or s == None: return ""
    if ";" in s:             # 分号分隔 → 数组递归转换
        return [convert_to_data(item) for item in s.split(";")]
    try: return int(s)       # 尝试转整数
    except:
        try: return float(s) # 尝试转浮点数
        except: return s     # 否则保持字符串
```

从 SUMO DLL 接收的数据都是字符串，此函数自动转为 Python 原生类型。

### 1.4 `read_sumocore_xml(file_name)` / `write_sumocore_xml(file_name, data)` — XML 状态文件读写

`read_sumocore_xml` 解析如下的 XML 文件：

```xml
<systemstate modelHash="???">
    <real name="Sumo__Plant__CSTR__SCOD">
        <value>45.2</value>
    </real>
</systemstate>
```

返回 `dict[str, VariableEntry]`。

`write_sumocore_xml` 将 dict 写回 XML 文件。

### 1.5 `write_sumocore_script(file_name, data)` — 生成初始化脚本

将 dict 写为 `set 变量名 值;` 格式的脚本文件（即 `init.scs` 的格式）。

### 1.6 `extract_dll_from_project(project, path_to)` — 从 .sumo 解压 DLL

```python
def extract_dll_from_project(project, path_to):
    with zipfile.ZipFile(project, 'r') as zf:   # .sumo 本质是 zip
        with open(path_to, "wb") as f:
            f.write(zf.read("sumoproject.dll"))  # 解压出 DLL
```

`.sumo` 文件本质是一个 zip 压缩包，包含 `sumoproject.dll`（编译后的仿真模型）、`parameters.txt`（参数表）以及各种 TSV 数据文件。

### 1.7 `extract_parameters_from_project(project, tsvdir, script_to, scenario)` — 解压参数并生成 init.scs

此函数做了几件事：

1. 从 `.sumo` 中提取 `parameters.txt`
2. 解析 `[CONSTANT INPUT]` 段，生成 `set 变量名 值;` 写入脚本文件
3. 解析 `[DYNAMIC INPUT]` 段，提取 TSV 文件并生成 `loadtsv` 命令

最终生成的 `init.scs` 内容类似：

```scs
set Sumo__Plant__param__SRT1_control 1;
set Sumo__Plant__Influent__param__Q 17280;
set Sumo__Plant__Influent__param__TCOD 300;
set Sumo__Plant__CSTR__param__L_Vtrain 750;
...（共 10 条 set 命令）
```

### 1.8 其他工具函数

| 函数 | 功能 |
|------|------|
| `read_opc_mapping_csv(file)` | 读取 OPC 映射表 CSV |
| `read_var_mapping_sv(file)` | 读取变量映射表（TSV/CSV） |
| `create_array(begin, end, step, count)` | 生成灵活的数值序列 |
| `create_temp_folder(base)` | 创建随机命名的临时文件夹 |
| `csv_to_tsv(file)` / `tsv_to_csv(file)` | CSV ↔ TSV 格式转换 |
| `get_install_location(version)` | 从 Windows 注册表读取 SUMO 安装路径 |
| `log_print(s)` | 带时间戳的日志打印 |

---

## 2. `dynamita/scheduler.py` — 仿真调度器（核心 API）

### 2.1 类的初始化 `__init__(self, sumoPath)`

```python
class SumoScheduler:
    def __init__(self, sumoPath=""):
        self.version = 'Sumo24'
        self.scheduledJobs = 0          # 当前未完成的任务数
        self.jobData = {}               # job_id → 用户自定义数据字典
        self.persistent = "persistent"   # 标记 jobData 是否持久化
        self._load_sumo(sumoPath)        # 加载 sumoscheduler.dll
```

### 2.2 `_load_sumo(sumoPath)` — 加载 DLL 并注册回调

执行流程：

1. **查找 SUMO 安装路径**：从 Windows 注册表 `HKEY_CURRENT_USER\SOFTWARE\Dynamita\Sumo24\PATHS` 读取 `INST` 值
2. **加载 `sumoscheduler.dll`**：使用 `ctypes.cdll.LoadLibrary()` 加载原生 DLL
3. **设置 DLL 函数签名**：
   ```python
   self._scheduler.schedule.argtypes = [c_char_p, c_char_p, c_char_p, c_int]
   self._scheduler.schedule.restype = c_int
   # ... setParallelJobs, finish, sendCommand, 等
   ```
4. **创建 C 回调函数**：用 `CFUNCTYPE` 包装两个内部 Python 函数
   - `internal_datacomm_callback`：接收仿真数据
   - `internal_message_callback`：接收仿真消息

5. **注册回调到 DLL**：
   ```python
   self._scheduler.register_message_callback(self.c_message_callback)
   self._scheduler.register_datacomm_callback(self.c_datacomm_callback)
   ```

### 2.3 `internal_datacomm_callback(job, msg)` — 数据回调的处理过程

```
DLL 传入的原始数据格式：
"Sumo__Time = 900000|Sumo__Plant__Effluent__TCOD = 25.3|..."

处理步骤：
1. msg.decode('utf8') → 字符串
2. 按 "|" 分割 → ["Sumo__Time = 900000", "Sumo__Plant__Effluent__TCOD = 25.3", ...]
3. 每个元素按 " = " 分割 → ("Sumo__Time", "900000")
4. convert_to_data("900000") → 900000（整数）
5. 构造 data 字典 → {"Sumo__Time": 900000, "Sumo__Plant__Effluent__TCOD": 25.3, ...}
6. 调用用户注册的 self.datacomm_callback(job, data)
```

### 2.4 `internal_message_callback(job, msg)` — 消息回调的处理过程

直接调用用户注册的 `self.message_callback(job, msg.decode('utf8'))`。

### 2.5 `schedule(model, commands, variables, blockDatacomm, jobData)` — 提交仿真任务

```python
def schedule(self, model, commands, variables, blockDatacomm=False, jobData=None):
    varstr = "|".join(variables)    # 变量名用 | 拼接
    # 命令用 ; 拼接，编码为 UTF-8
    id = self._scheduler.schedule(
        model.encode("utf8"),
        (";".join(commands)).encode("utf8"),
        varstr.encode("utf8"),
        int(blockDatacomm)
    )
    self.jobData[id] = jobData      # 关联用户数据字典
    self.scheduledJobs = self._scheduler.getScheduledJobs()
    return id
```

**返回值**：一个整数 `job_id`（通常不需要保留，因为只用单任务串行）。

### 2.6 其他关键方法

| 方法 | 功能 |
|------|------|
| `setParallelJobs(n)` | 设置并行任务数（本项目始终为 1） |
| `finish(job)` | 标记任务完成，递减 scheduledJobs；非持久化数据会被删除 |
| `sendCommand(job, cmd)` | 向正在运行的仿真发送指令 |
| `getJobData(jobId)` | 获取与此 job 关联的数据字典 |
| `isSimFinishedMsg(msg)` | 判断消息是否以 "530004" 开头（仿真结束标志） |
| `cleanup()` | 清空所有 jobData，调用 DLL 清理 |
| `getPYVersion()`/`getDLLVersion()` | 版本检查 |

### 2.7 全局单例

```python
sumo = SumoScheduler()
```

整个项目通过 `ds.sumo` 访问这个全局调度器实例。

---

## 3. `dynamita/dmqclient.py` — DMQ 消息队列客户端

DMQ（Dynamita Message Queue）是 SUMO 的进程间通信机制。

### 3.1 `DMQDllWrapper` 类

初始化时做了以下事情：

1. **查找 DMQ.exe**：从 Windows 注册表读取安装路径
2. **检查 DMQ.exe 是否在运行**：`tasklist /fi "ImageName eq dmq.exe"`
3. **如果未运行则启动**：生成 `.bat` 文件，`subprocess.Popen` 启动 DMQ.exe 后台进程。日志保存到 `dmq_logs/` 目录
4. **加载 DMQClient.dll**：`cdll.LoadLibrary("DMQClient.dll")`
5. **注册 DLL 函数签名**：`initModule`, `createQueue`, `sendText`, `getText` 等
6. **调用 `initModule("Python")`** 初始化模块

### 3.2 DMQ 消息队列的基本操作

| 方法 | 功能 |
|------|------|
| `create()` | 创建一个匿名队列，返回 `DMQClient` 实例 |
| `create_specific_queue(key)` | 创建命名队列 |
| `open(key)` | 打开已存在的命名队列 |

### 3.3 `DMQClient` 类

消息队列客户端，提供 `send_data(msg)` 和 `read_data(blocking)` 两个核心方法。

### 3.4 `OPCClient` 类

OPC（OLE for Process Control）工业通信协议的客户端。用于连接真实的 PLC/SCADA 系统，通过 OPC 协议读写变量。

提供了 `read_variables(variable_list)`, `write_variables(variable_dict)` 以及映射版本的 `read_mapped_variables` / `write_mapped_variables`。

**注意**：本项目的主控制脚本没有直接使用 `dmqclient`，而是通过 `scheduler.py` 间接使用的。

---

## 4. `dynamita/sumogui.py` — SUMO GUI 控制

通过 DMQ 消息队列控制 SUMO 的图形化界面。原理：

1. 启动 SUMO GUI：`subprocess.Popen([sumo_exe, project_path, "-dmq", dmq_key])`
2. 通过 `dmq.send_data("core_cmd set 变量 值;")` 向 GUI 发送命令
3. 通过 `dmq.read_data()` 接收 GUI 的消息

**注意**：本项目的主控制脚本也**没有使用这个模块**，它们使用的是 `scheduler.py` 的头less模式（无 GUI 后台仿真）。

---

# 第二部分：基础配置文件

---

## 5. `parameters.txt` — SUMO 模型常量参数

这是从 `.sumo` 项目文件中提取的原始参数表。

```
[CONSTANT INPUT]
Full Symbol                          Value
Sumo__Plant__param__SRT1_control     1
Sumo__Plant__Influent__param__Q      17280
Sumo__Plant__Influent__param__TCOD   300
Sumo__Plant__CSTR__param__L_Vtrain   750
Sumo__Plant__CSTR__param__Qair_NTP   0
Sumo__Plant__CSTR2__param__L_Vtrain  1500
Sumo__Plant__CSTR2__param__Qair_NTP  0
Sumo__Plant__CSTR3__param__L_Vtrain  3000
Sumo__Plant__Sideflowdivider__param__Qpumped_target  51840
Sumo__Plant__CSTR4__param__L_Vtrain  1500
Sumo__Plant__CSTR4__param__Qair_NTP  0
[DYNAMIC INPUT]
```

**各参数含义**：

| 参数 | 含义 | 值 |
|------|------|----|
| SRT1_control | 污泥龄控制开关 | 1（启用） |
| Influent Q | 进水流量 (m³/d) | 17280 |
| Influent TCOD | 进水总 COD (mg/L) | 300 |
| CSTR Vtrain | 厌氧池体积 (m³) | 750 |
| CSTR2 Vtrain | 缺氧池体积 (m³) | 1500 |
| CSTR3 Vtrain | 好氧池体积 (m³) | 3000 |
| CSTR4 Vtrain | 后缺氧池体积 (m³) | 1500 |
| Qair_NTP | 各池曝气量 | 0（被后续 set 覆盖） |
| Qpumped_target | IMLR 泵目标流量 (m³/d) | 51840 |

---

## 6. `init.scs` — 仿真初始化脚本

由 `extract_parameters_from_project()` 自动生成：

```scs
set Sumo__Plant__param__SRT1_control 1;
set Sumo__Plant__Influent__param__Q 17280;
set Sumo__Plant__Influent__param__TCOD 300;
set Sumo__Plant__CSTR__param__L_Vtrain 750;
set Sumo__Plant__CSTR__param__Qair_NTP 0;
set Sumo__Plant__CSTR2__param__L_Vtrain 1500;
set Sumo__Plant__CSTR2__param__Qair_NTP 0;
set Sumo__Plant__CSTR3__param__L_Vtrain 3000;
set Sumo__Plant__Sideflowdivider__param__Qpumped_target 51840;
set Sumo__Plant__CSTR4__param__L_Vtrain 1500;
set Sumo__Plant__CSTR4__param__Qair_NTP 0;
```

每条 `set` 是一个 SUMO 脚本命令，设置模型中的一个参数值。执行后这些值成为仿真的基准，后续 `commands` 中的 `set` 可以覆盖它们。

---

# 第三部分：辅助脚本

---

## 7. `knowledge control setting.py` — 规则控制设定值生成器

### 7.1 步骤 1：读取测试数据

```python
file_path = "data/test flow1.xlsx"
df = pd.read_excel(file_path)
```

读取 Excel 文件，包含 `Influent Flow Rate (m3/d)` 等列。

### 7.2 步骤 2：定义规则函数 `assign_controls(flow)`

```python
def assign_controls(flow):
    if flow < 20000:
        return 1.5, 20000    # 低流量 → 低 DO=1.5, 低 IMLR=20000
    elif flow < 40000:
        return 2.0, 30000    # 中流量 → 中 DO=2.0, 中 IMLR=30000
    else:
        return 3.0, 40000    # 高流量 → 高 DO=3.0, 高 IMLR=40000
```

基于"初级工程师经验"的三段式规则：
- 流量越大 → 污染物负荷越大 → 需要更高的溶解氧和更大的内循环量

### 7.3 步骤 3：逐行应用规则

```python
df[['DO_Setpoint', 'IMLR_Setpoint']] = df['Influent Flow Rate (m3/d)'].apply(
    lambda x: pd.Series(assign_controls(x))
)
```

为每行数据生成对应的 DO 和 IMLR 设定值。

### 7.4 步骤 4：保存结果

```python
output_file_path = "data/rule_based_control_settings_flow1.xlsx"
df.to_excel(output_file_path, index=False)
```

生成的 Excel 文件被 `Rule-based Control test.py` 读取使用。

---

# 第四部分：五大控制策略脚本

所有五个控制脚本共享相同的基础结构：
1. 模型准备（解压 DLL、注册回调）
2. 读取测试数据
3. 循环每个 episode（每个时间点）
4. 加载初始状态 → 构建控制参数 → 运行仿真 → 读出结果 → 保存状态
5. 结果汇总输出

---

## 8. `Static Control test.py` — 静态固定参数控制（基线测试）

### 8.1 步骤 1：模型准备

```python
dtool.extract_dll_from_project("AA'OA'.sumo", "sim.dll")
dtool.extract_parameters_from_project("AA'OA'.sumo", ".", "init.scs", "")
ds.sumo.setParallelJobs(1)
ds.sumo.message_callback = msg_callback
ds.sumo.datacomm_callback = data_callback
```

### 8.2 步骤 2：读取测试数据

```python
test_data = pd.read_excel('data/test flow4.xlsx')  # 读取流量场景4
test_data = test_data.iloc[0:25]                     # 取前25个时间点
```

### 8.3 步骤 3：主循环

```python
for episode in range(len(test_data)):  # 25 个 episode
```

#### 3a. 首回合加载初始状态

```python
if episode == 0:
    shutil.copyfile("initial state/episode_initial_state.xml",
                    "episode_initial_state.xml")
```

#### 3b. 固定控制参数

```python
DO_fixed = 2          # DO 固定 2.0 mg/L
IMLR_fixed = 34560    # IMLR 固定 34560 m³/d（300% 进水流量）
Carbon_fixed = 0      # 不加碳源
```

#### 3c. 运行仿真

```python
job, EQI, OCI, Power, OPEXplant_d, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN = \
    run_sim_multiple_pram(model, init_file,
        Q_inf, COD_inf, TKN_inf, DO_fixed, IMLR_fixed, Carbon_fixed)
```

#### 3d. 计算奖励

```python
reward = reward_function(EQI, OCI, OPEXplant_d, Power,
    CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN,
    DO_fixed, IMLR_fixed, Carbon_fixed)
```

#### 3e. 状态传递

```python
os.replace("tmp_state.xml", "episode_initial_state.xml")
```

### 8.4 运行仿真的核心函数 `run_sim_multiple_pram()`

这是所有脚本共用的核心函数（约 120 行）。

#### 4a. 提交仿真任务

```python
job = ds.sumo.schedule(
    model,         # "sim.dll"
    commands=[     # 所有指令按顺序执行
        f"execute {init_file}",                        # ① 加载固定参数
        "load episode_initial_state.xml",               # ② 加载上次状态
        "maptoic",                                      # ③ 映射为初始条件
        f"set Sumo__Plant__Influent__param__TCOD {300}",
        f"set Sumo__Plant__Influent__param__Q {Q_inf}", # ④ 覆盖进水流量
        f"set Sumo__Plant__Influent__param__TKN {42}",
        f"set Sumo__Plant__Sideflowdivider__param__Qpumped_target {Q_IMLR}",
        f"set Sumo__Plant__CSTR3__param__DOSP {CSTR3__DOSP}",
        f"set Sumo__Plant__Carbon1__param__Q {Carbon}",
        f"set Sumo__StopTime {15*dtool.minute}",        # ⑤ 仿真15分钟
        f"set Sumo__DataComm {15*dtool.minute}",         # ⑥ 每15分钟回传
        "mode dynamic",                                  # ⑦ 动态模式
        "start"                                          # ⑧ 启动
    ],
    variables=[...],   # 19 个监测变量
    jobData={...}      # 数据存储容器
)
```

**指令执行顺序是关键的**：

```
execute init.scs           → 设置所有固定参数（体积、曝气量、SRT控制等）
load episode...xml         → 加载上一回合结束时的系统状态
maptoic                    → 将状态值映射为当前仿真的初始条件
set Q {Q_inf}              → 覆盖进水流量（每个episode可能不同）
set DOSP {value}           → 覆盖DO设定值
set Qpumped_target {value} → 覆盖IMLR流量
set Carbon {value}         → 覆盖碳源投加量
set StopTime 900000        → 仿真15分钟后停止
set DataComm 900000        → 15分钟时回传一次数据
mode dynamic               → 切换到动态模式
start                      → 开始积分计算
```

#### 4b. 等待仿真结束

```python
while ds.sumo.scheduledJobs > 0:
    time.sleep(0.1)
```

轮询检查。仿真在后台运行时，DLL 会回调 `data_callback` 和 `msg_callback`。

#### 4c. 读取结果

```python
for jd in ds.sumo.jobData.values():
    Eff_TCOD = jd["Eff_TCOD"][-1]     # 取最后一个值
    Eff_TN = jd["Eff_TN"][-1]
    OPEXplant_d = jd["OPEXplant_d"][-1]
    # ...
```

#### 4d. 计算指标

**EQI（出水质量指数）**：

```python
EQI = (2*Eff_XTSS + Eff_TCOD + 30*Eff_SKN + 10*Eff_SNHx + 2*Eff_TBOD_5) * Q_Eff / 1000
```

**AE（曝气能耗，kWh/d）**：

```python
AE = (DO_sat / (1.8 * 1000)) * (V_CSTR * kLa_CSTR + V_CSTR2 * kLa_CSTR2
      + V_CSTR3 * kLa_CSTR3 + V_CSTR4 * kLa_CSTR4)
```

**PE（泵送能耗，kWh/d）**：

```python
PE = 0.004 * Q_IMLR + 0.008 * Q_RAS + 0.05 * Q_WAS
```

**ME（混合能耗）**：仅当 kLa < 20（曝气不足需搅拌）时计算

```python
ME_CSTR = 24 * 0.005 * V_CSTR * kLa_CSTR if kLa_CSTR < 20 else 0
```

**OCI（综合运行成本指数）**：

```python
OCI = AE + PE + ME + 5 * SP     # SP = 污泥处理成本
```

#### 4e. 清理

```python
ds.sumo.cleanup()
```

### 8.5 数据回调函数 `data_callback(job, data)`

```python
def data_callback(job, data):
    jobData = ds.sumo.getJobData(job)
    jobData["t"].append(data["Sumo__Time"] / dtool.day)        # 转换为天
    jobData["Q_Inf"].append(data["Sumo__Plant__Influent__Q"])
    jobData["Eff_TCOD"].append(data["Sumo__Plant__Effluent__TCOD"])
    # ... 逐项追加到列表
```

每次触发时将 data dict 中的值追加到对应列表。因为 DataComm = StopTime = 15分钟，每个 job 只触发一次。

### 8.6 消息回调函数 `msg_callback(job, msg)`

```python
def msg_callback(job, msg):
    save_finished = msg.startswith("530045")
    jobData = ds.sumo.getJobData(job)

    if ds.sumo.isSimFinishedMsg(msg):   # "530004" = 仿真运行结束
        jobData["wait_for_save"] = True
        ds.sumo.sendCommand(job, "save tmp_state.xml;")

    if jobData["wait_for_save"] and save_finished:  # "530045" = 保存完成
        jobData["wait_for_save"] = False
        ds.sumo.finish(job)  # 标记完成 → scheduledJobs -= 1
```

消息流：
```
530004（仿真结束） → 发送 save 命令 → 530045（保存完成） → finish()
```

### 8.7 奖励函数 `reward_function()`

```python
def reward_function(EQI, OCI, OPEXplant_d, Power, CSTR2_SNOx,
                    Eff_TCOD, Eff_SNHx, Eff_TN, DO, IMLR, Carbon):
    reward = 0
    if Eff_TCOD <= 40 and Eff_SNHx <= 3 and Eff_TN <= 15:  # 达标
        reward += 1.0                    # 基础奖励
        if CSTR2_SNOx > 1:              # 反硝化正常
            reward += 0.1
        reward += 800 / (OPEXplant_d + 1)  # 成本越低越好
        reward += 300 / (EQI + 1)          # 出水质量越好越好
        reward += 400 / (OCI + 1)          # 综合成本越低越好
        reward += 100 / (Power + 1)        # 能耗越低越好
        reward += 0.2 * (1 - DO/DO_sat)**2    # 鼓励低DO
        reward += 0.2 * (1 - IMLR/70000)**2   # 鼓励低IMLR
        reward += 0.2 * (1 - Carbon/5)**2     # 鼓励低碳源
    else:
        reward = -1                      # 不达标 → 惩罚
    return reward
```

### 8.8 结果保存

```python
def save_test_results_to_excel(results, result_folder):
    # 写入 Excel，包含 Summary 表 + 平均值行
    # Summary 表列：Episode, time, Flow, DO, IMLR, Carbon, EQI,
    #               OPEXplant_d, Power, CSTR2_SNOx, Eff_TCOD,
    #               Eff_SNHx, Eff_TN, Reward
```

---

## 9. `Rule-based Control test.py` — 基于规则的控制

与 Static Control 几乎相同，唯一区别在第 3b 步的控制参数来源：

### 控制参数来自规则表

```python
control_data = pd.read_excel("data/rule_based_control_settings_flow1.xlsx")
# ...
DO_setpoint = control_data.at[episode, 'DO_Setpoint']
IMLR_setpoint = control_data.at[episode, 'IMLR_Setpoint']
Carbon_setpoint = 0
```

即用 `knowledge control setting.py` 预先算好的表，按流量分段：

| 进水流量 | DO | IMLR | Carbon |
|----------|-----|------|--------|
| < 20000 | 1.5 | 20000 | 0 |
| 20000-40000 | 2.0 | 30000 | 0 |
| > 40000 | 3.0 | 40000 | 0 |

**其他所有部分与 Static Control 完全相同。** 没有多步优化，每个 episode 只运行一次仿真。

---

## 10. `Bayesian Optimization.py` — 贝叶斯优化

### 10.1 步骤 1：定义搜索空间

```python
from skopt import gp_minimize
from skopt.space import Real, Integer

space = [
    Real(0.5, 3, name='DO'),              # DO 连续变量 [0.5, 3]
    Integer(17280, 69120, name='IMLR'),    # IMLR 整数变量 [17280, 69120]
    Real(0, 5, name='Carbon')             # Carbon 连续变量 [0, 5]
]
```

### 10.2 步骤 2：目标函数

```python
def objective(CSTR3__DOSP, Q_IMLR, Carbon, model, init_file, Q_inf, Inf_TCOD, Inf_TKN):
    job, OPEXplant_d, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN = \
        run_sim_multiple_param(model, init_file, Q_inf, Inf_TCOD, Inf_TKN,
                               CSTR3__DOSP, Q_IMLR, Carbon)

    penalty = 0
    if Eff_TN >= 15:    penalty += 10000
    if CSTR2_SNOx < 1:  penalty += 1000
    if Eff_SNHx > 3:    penalty += 10000
    if Eff_TCOD > 40:   penalty += 10000

    return OPEXplant_d + penalty
```

每次调用运行一次仿真（15分钟），返回 OPEX + 超标惩罚。惩罚值 10000 远大于典型 OPEX（~500-2000），确保贝叶斯优化避开不达标的参数区域。

### 10.3 步骤 3：gp_minimize 执行贝叶斯优化

```python
def optimize_for_episode(model, init_file, episode):
    Q_inf = test_data.at[episode, 'Influent Flow Rate (m3/d)']

    result = gp_minimize(
        lambda x: objective(x[0], x[1], x[2], model, init_file,
                           Q_inf, Inf_TCOD, Inf_TKN),
        space,
        n_initial_points=10,    # 先随机采样10个点建立初始模型
        n_calls=10,             # 总共评估10次（这里=仅初始10次）
        random_state=42,        # 随机种子，保证可复现
        acq_func="EI"           # Expected Improvement 采集函数
    )
    return result.x, result.fun  # 返回最优参数和对应的目标值
```

**注意**：`n_initial_points=10` + `n_calls=10` 意味着只做 10 次初始随机采样，没有额外的贝叶斯迭代。这是为了快速得出结果而设置的（实际应用中可以增大 `n_calls` 到 50+）。

### 10.4 步骤 4：按 episode 顺序优化

```python
for episode in range(len(test_data)):
    if episode == 0:
        shutil.copyfile("initial state/episode_initial_state.xml",
                        "episode_initial_state.xml")

    best_params, best_cost = optimize_for_episode(model, init_file, episode)

    # 用最优参数再运行一次，获取完整的出水指标
    _, _, _, Eff_TCOD, Eff_SNHx, Eff_TN = run_sim_multiple_param(...)

    os.replace("tmp_state.xml", "episode_initial_state.xml")
```

每个 episode 做 10 次仿真，25 个 episode 共 250 次仿真。

### 10.5 步骤 5：保存最优参数表

```python
results_df.to_excel('Initial Action Points After BO.xlsx', index=False)
```

输出表含：`Episode, Time, DO, IMLR, Carbon, Best Cost`。

这个文件后续被 `RL+BO Control test.py` 用作初始解。

### 10.6 与其他脚本的关键区别

| 方面 | Static/Rule-based | Bayesian Optimization |
|------|-------------------|-----------------------|
| 每episode仿真次数 | 1次 | 10次 |
| 参数选择方式 | 固定/查表 | 高斯过程搜索最优 |
| 目标 | 测试效果 | 寻找最优参数 |
| 输出 | 测试结果 | 最优参数表 + 测试结果 |

---

## 11. `RL Control train.py` — DQN 强化学习训练

### 11.1 步骤 1：定义神经网络结构

```python
class Net(nn.Module):
    def __init__(self):
        self.fc1 = nn.Linear(6, 30)    # 输入6维状态 → 30维隐藏层
        self.fc2 = nn.Linear(30, 7)    # 30维隐藏层 → 7个动作的Q值

    def forward(self, x):
        x = F.relu(self.fc1(x))        # ReLU 激活
        x = self.fc2(x)                 # 输出 Q(s, a)
        return x
```

**6 维状态空间**：`[进水流量, COD_inf, TKN_inf, DO当前值, IMLR当前值, Carbon当前值]`

**7 个离散动作**：

| 动作编号 | 含义 | 范围约束 |
|----------|------|----------|
| 0 | DO - 0.5 | ≥ 0.5 |
| 1 | DO + 0.5 | ≤ 3.0 |
| 2 | IMLR - 10000 | ≥ 17280 |
| 3 | IMLR + 10000 | ≤ 69120 |
| 4 | Carbon - 0.5 | ≥ 0 |
| 5 | Carbon + 0.5 | ≤ 2.5 |
| 6 | 保持不变 | — |

### 11.2 步骤 2：DQN 智能体类 `Dqn()`

#### 2a. 经验回放存储

```python
def store_trans(self, state, action, reward, next_state):
    index = self.memory_counter % MEMORY_CAPACITY  # 循环覆盖，容量=40
    trans = np.hstack((state, [action], [reward], next_state))
    self.memory[index] = trans
    self.memory_counter += 1
```

#### 2b. ε-greedy 动作选择

```python
def choose_action(self, state):
    if np.random.rand() < self.epsilon:       # 以 ε 概率随机探索
        action = np.random.randint(0, 7)
    else:                                      # 以 (1-ε) 概率选择最优
        action_value = self.eval_net.forward(state)
        action = torch.max(action_value, 1)[1].item()
    return action
```

ε 从 0.9 指数衰减到 0.1（每 episode 乘 0.995）。

#### 2c. DQN 学习更新

```python
def learn(self):
    # 每100次学习同步目标网络
    if self.learn_counter % 100 == 0:
        self.target_net.load_state_dict(self.eval_net.state_dict())

    # 随机采样 batch
    sample_index = np.random.choice(40, 32)  # 从40条记忆中取32条

    # 计算 Q_target = r + γ * max_a' Q_target(s', a')
    q_eval = self.eval_net(batch_state).gather(1, batch_action)
    q_next = self.target_net(batch_next_state).detach()
    q_target = batch_reward + 0.9 * q_next.max(1)[0]

    # MSE 损失 + Adam 优化
    loss = self.loss(q_eval, q_target)
    self.optimizer.zero_grad()
    loss.backward()
    self.optimizer.step()
```

### 11.3 步骤 3：主训练循环

```python
for episode in range(len(train_data)):     # 遍历训练数据所有时间点
    state = [Q_inf, COD_inf, TKN_inf, DO_initial, Q_IMLR_initial, Carbon_initial]

    for step in range(20):                  # 每个 episode 20 步
        action = net.choose_action(state)   # ① ε-greedy 选动作
        # ② 根据动作更新下一状态
        next_state = apply_action(state, action)
        # ③ 运行仿真（15分钟）
        job, EQI, OCI, Power, OPEXplant_d, ... = run_sim_multiple_pram(...)
        # ④ 计算奖励
        reward = reward_function(EQI, OCI, OPEXplant_d, Power, ...)
        # ⑤ 存入经验池
        net.store_trans(state, action, reward, next_state)
        # ⑥ 当经验池满了，开始学习
        if net.memory_counter >= 40:
            net.learn()
        state = next_state

    # 每24个episode保存一次模型
    if (episode + 1) % 24 == 0:
        torch.save(net.eval_net.state_dict(), f"RL models/model_ep{episode+1}.pth")

    # 状态传递
    os.replace("tmp_state.xml", "episode_initial_state.xml")
    net.decay_epsilon()
```

**每个 episode 的执行流程**：

```
状态 s₀ → 选动作 a₀ → 下一状态 s₁ → 仿真 → 奖励 r₀ → 存入经验池 → 学习
  │
  └→ s₁ → 选动作 a₁ → s₂ → 仿真 → 奖励 r₁ → 存入经验池 → 学习
        │
        └→ ... (重复20步)
            │
            └→ 保存状态 → 下一episode
```

**关键超参数**：

| 参数 | 值 | 说明 |
|------|-----|------|
| GAMMA | 0.9 | 折扣因子 |
| LR | 0.01 | Adam 学习率 |
| MEMORY_CAPACITY | 40 | 经验池大小（循环覆盖） |
| BATCH_SIZE | 32 | 每次学习采样数 |
| Q_NETWORK_ITERATION | 100 | 目标网络更新频率 |
| EPSILON | 0.9 → 0.1 | ε 指数衰减（0.995^episode） |

### 11.4 RL 训练特有的奖励函数

```python
def reward_function(EQI, OCI, OPEXplant_d, Power, CSTR2_SNOx,
                    Eff_TCOD, Eff_SNHx, Eff_TN, DO, IMLR, Carbon):
    reward = 0
    if Eff_TCOD <= 40 and Eff_SNHx <= 3 and Eff_TN <= 15:
        reward += 1.0
        if CSTR2_SNOx > 1: reward += 0.1
        reward += 800 / (OPEXplant_d + 1)   # OPEX 越低越好
        reward += 300 / (EQI + 1)            # EQI 越低越好
        reward += 400 / (OCI + 1)            # OCI 越低越好
        reward += 100 / (Power + 1)          # Power 越低越好
        reward += 0.2 * (1 - DO/DO_sat)**2
        reward += 0.2 * (1 - IMLR/70000)**2
        reward += 0.2 * (1 - Carbon/5)**2
    else:
        reward = -1
    return reward
```

目的是引导智能体在达标前提下尽量节约运行成本。

---

## 12. `RL Control test.py` — DQN 模型测试

### 12.1 与训练脚本的主要区别

| 方面 | `RL Control train.py` | `RL Control test.py` |
|------|-----------------------|----------------------|
| 模型 | 新建随机权重 | 加载训练好的权重 `model_ep4800.pth` |
| ε值 | ε=0.9，逐步衰减 | ε=0.99（几乎不探索） |
| 探索 | ε-greedy | ε-greedy（高ε = 倾向最优） |
| 模型保存 | 每24episode保存 | 不保存 |
| 记录步数 | 不记录 | 每步详细记录（Step, Action, DO, IMLR等） |
| 结果输出 | 模型文件 | Excel 报告 + 每episode最优步 |

### 12.2 步骤 1：加载预训练模型

```python
RL_model_path = 'RL models/model_ep4800.pth'
net = Dqn()
net.eval_net.load_state_dict(torch.load(RL_model_path, map_location=device))
net.eval_net.eval()
```

加载第 4800 episode 时保存的模型权重，切换到评估模式。

### 12.3 步骤 2：每个 episode 20 步仿真

```python
for step in range(20):
    action = net.choose_action(state)   # 使用训练好的策略选动作
    # 更新状态 → 运行仿真 → 计算奖励
    # 记录每一步的详细数据
    episode_steps.append({
        'Step': step + 1,
        'Action_Index': action,
        'DO': state[3],
        'IMLR': state[4],
        'Carbon': state[5],
        'EQI': EQI, 'Power': Power,
        'OPEXplant_d': OPEXplant_d,
        'CSTR2_SNOx': CSTR2_SNOx,
        'Eff_TCOD': Eff_TCOD,
        'Eff_SNHx': Eff_SNHx,
        'Eff_TN': Eff_TN,
        'Reward': reward
    })
```

### 12.4 步骤 3：选择最优步

```python
best_step = max(episode_steps, key=lambda x: x['Reward'])
```

每个 episode 的 20 步中，选择奖励最高的那一步作为"最佳策略"输出。

### 12.5 步骤 4：结果保存

结果分为两种文件：

1. **每 episode 最优动作文件**：`Best_Action_Summary_ep{N}.xlsx`
   - 列：Episode, Time, Best_Action, Best_DO, Best_IMLR, Best_Carbon

2. **汇总报告**：`RL_test_results_{timestamp}.xlsx`
   - Summary 表：每个 episode 一行 + 平均值行
   - Episode_1, Episode_2, ... 表：每个 episode 的 20 步详细记录

---

## 13. `RL+BO Control test.py` — 贝叶斯优化 + DQN 混合控制

### 13.1 与纯 RL 测试的区别

这个脚本结合了两种方法：

1. **从贝叶斯优化的结果中读取初始值**
2. **用 DQN 在初始值基础上微调**

```python
baysian_results = pd.read_excel('Initial Action Points After BO.xlsx')

# 状态初始值来自 BO 结果，而非硬编码！
state = [test_data.at[episode, 'Influent Flow Rate (m3/d)'],
         COD_inf, TKN_inf,
         baysian_results.at[episode, 'DO'],       # ← BO 优化的 DO
         baysian_results.at[episode, 'IMLR'],      # ← BO 优化的 IMLR
         baysian_results.at[episode, 'Carbon']]    # ← BO 优化的 Carbon
```

对比纯 RL 测试：

| | 纯 RL 测试 | RL+BO 混合 |
|------|------------|-------------|
| 初始 DO | 硬编码 2.0 | BO 最优值 |
| 初始 IMLR | 硬编码 34560 | BO 最优值 |
| 初始 Carbon | 硬编码 2 | BO 最优值 |
| DQN 做 20 步 | ✓ 从硬编码值开始 | ✓ 从 BO 最优值开始微调 |

### 13.2 IMLR 步长不同

- 纯 RL：IMLR 步长 ±10000
- RL+BO：IMLR 步长 ±5000（更精细的微调）

### 13.3 其他部分与 `RL Control test.py` 完全相同

---

# 第五部分：共用组件总结

## 所有测试脚本的共用框架

```
┌─────────────────────────────────────────────┐
│  1. 模型准备                                 │
│     extract_dll, extract_parameters          │
│     setParallelJobs, 注册回调                │
├─────────────────────────────────────────────┤
│  2. 读取测试数据 (pd.read_excel)             │
│     创建结果文件夹                            │
├─────────────────────────────────────────────┤
│  3. for episode in range(len(test_data)):   │
│        if episode == 0: 复制初始状态          │
│        确定本回合控制参数                     │
│        run_sim_multiple_pram(...)            │
│        计算奖励                              │
│        记录结果                              │
│        os.replace("tmp_state.xml", ...)      │
├─────────────────────────────────────────────┤
│  4. 保存结果到 Excel                         │
└─────────────────────────────────────────────┘
```

## 五大策略的本质差异

| 策略 | 控制参数来源 | 每episode仿真次数 | 是否有学习/优化 |
|------|-------------|-------------------|----------------|
| Static | 固定值 | 1 | 无 |
| Rule-based | Excel 查表（三段式规则） | 1 | 无 |
| Bayesian Opt | gp_minimize 搜索 | 10 | 有（在线优化） |
| RL train | DQN ε-greedy 选择 | 20 | 有（在线学习） |
| RL test | DQN 最优策略选择 | 20 | 仅推理（无学习） |
| RL+BO test | BO初始 + DQN 微调 | 20 | 仅推理（无学习） |

## 各脚本的仿真总次数

| 脚本 | 25episode × 每次仿真数 | 总仿真次数 |
|------|------------------------|-----------|
| Static Control | 25 × 1 | **25** |
| Rule-based Control | 25 × 1 | **25** |
| Bayesian Optimization | 25 × 10 | **250** |
| RL Control train | ~400 × 20 | **~8000** |
| RL Control test | 25 × 20 | **500** |
| RL+BO Control test | 25 × 20 | **500** |
