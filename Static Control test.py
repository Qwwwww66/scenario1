import os
import shutil

from scipy.constants import minute

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
import dynamita.scheduler as ds
import dynamita.tool as dtool
import seaborn as sns
import time
import datetime
from scipy.optimize import minimize
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import optim
import matplotlib.pyplot as plt


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")



test_data_path = 'data/test flow4.xlsx'


initial_state_folder = 'initial state'
initial_state_filename = 'episode_initial_state.xml'

DO_sat=9.458
V_CSTR=750 #m3
V_CSTR2=1500 #m3
V_CSTR3=3000 #m3
V_CSTR4=1500 #m3






def main():


    sumo_project = "AA'OA'.sumo"
    model = "sim.dll"
    dtool.extract_dll_from_project(sumo_project, model)
    init_file = "init.scs"
    dtool.extract_parameters_from_project(sumo_project, ".", "init.scs", "")

    ds.sumo.setParallelJobs(1)
    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    test_data = pd.read_excel(test_data_path)
    test_data = test_data[::]
    start_row = 0
    end_row = 25
    test_data = test_data.iloc[start_row:end_row]
    test_data = test_data.reset_index(drop=True)
    test_filename = os.path.splitext(os.path.basename(test_data_path))[0]

    # 创建时间戳子文件夹
    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    result_folder = os.path.join("test results", f"Static_Control_{test_filename}_{current_time}")

    os.makedirs(result_folder, exist_ok=True)




    results = []
    for episode in range(len(test_data)):
        # state = self.env.reset()  # Assume you have an env attribute in Dqn for simplicity
        # test_data['Time'] = pd.to_datetime(test_data['Time'])
        # time_stamp = test_data.at[episode, 'Time'] + pd.Timedelta(hours=6)

        if episode == 0:
            src_path = os.path.join(initial_state_folder, initial_state_filename)
            dst_path = "episode_initial_state.xml"
            # 如果同级目录已经有这个文件，也要覆盖
            shutil.copyfile(src_path, dst_path)
            print(f"Copied '{src_path}' → '{dst_path}'")

        total_reward = 0
        episode_steps = []
        time_stamp = test_data.at[episode, 'Time (min)']
        Q_inf = test_data.at[episode, 'Influent Flow Rate (m3/d)']
        COD_inf = 300
        TKN_inf = 42
        DO_fixed = 2
        IMLR_fixed = 34560
        Carbon_fixed = 0

        job, EQI, OCI, Power, OPEXplant_d, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN = run_sim_multiple_pram(
            model, init_file,
            Q_inf, COD_inf, TKN_inf,
            DO_fixed, IMLR_fixed, Carbon_fixed
        )

        reward = reward_function(
            EQI, OCI, OPEXplant_d, Power,
            CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN,
            DO_fixed, IMLR_fixed, Carbon_fixed
        )

        results.append({
            'Episode': episode + 1,
            'time': time_stamp,
            'Flow': Q_inf,  # 记录流量
            'DO': DO_fixed,
            'IMLR': IMLR_fixed,
            'Carbon': Carbon_fixed,
            'EQI': EQI,
            'OPEXplant_d': OPEXplant_d,
            'Power': Power,
            'CSTR2_SNOx': CSTR2_SNOx,
            'Eff_TCOD': Eff_TCOD,
            'Eff_SNHx': Eff_SNHx,
            'Eff_TN': Eff_TN,
            'Reward': reward
        })

        print('End of episode Eff_TCOD=', Eff_TCOD)
        print('End of episode Eff_SNHx=', Eff_SNHx)
        print('End of episode Eff_TN=', Eff_TN)
        # 覆盖下一个 episode 的初始状态
        os.replace("tmp_state.xml", "episode_initial_state.xml")
        print('episode_initial_state modified')

        print(f"Episode {episode + 1} | Flow={Q_inf} | EQI={EQI:.2f} | Reward={reward:.2f}")


    save_test_results_to_excel(results, result_folder)


def save_test_results_to_excel(results, result_folder):
    # 构造文件名
    filename = os.path.join(
        result_folder,
        f"Static_test_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )

    # 将 results（list of dicts）直接转成 DataFrame
    main_df = pd.DataFrame(results)

    # 计算除 Episode 和 time 之外所有数值列的平均值
    numeric_cols = [c for c in main_df.columns if c not in ('Episode', 'time')]
    average_values = {col: main_df[col].mean() for col in numeric_cols}
    average_row = pd.DataFrame([average_values], index=['Average'])

    # 把平均行拼到最后
    summary_df = pd.concat([main_df, average_row], ignore_index=False)

    # 写入 Excel
    with pd.ExcelWriter(filename) as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)

    print(f"Results saved to {filename}")





def run_sim_multiple_pram(model, init_file, Q_inf, Inf_TCOD, Inf_TKN, CSTR3__DOSP, Q_IMLR, Carbon):


    job = ds.sumo.schedule(
        model,
        commands=[
            f"execute {init_file}",
            "load episode_initial_state.xml",
            "maptoic",
            f"set Sumo__Plant__Influent__param__TCOD {300}",
            f"set Sumo__Plant__Influent__param__Q {Q_inf}",
            f"set Sumo__Plant__Influent__param__TKN {42}",
            f"set Sumo__Plant__Sideflowdivider__param__Qpumped_target {Q_IMLR}",
            #f"set Sumo__Plant__param__SRT1_target {Total_SRT}",
            f"set Sumo__Plant__CSTR3__param__DOSP {CSTR3__DOSP}",
            f"set Sumo__Plant__Carbon1__param__Q {Carbon}",
            f"set Sumo__StopTime {15*dtool.minute}",
            f"set Sumo__DataComm {15*dtool.minute}",
            "mode dynamic",
            "start"
        ],
        variables=[
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
            "Sumo__Plant__Pipe9__Q",
            "Sumo__Plant__Pipe12__Q",
            "Sumo__Plant__Pipe13__Q",
            "Sumo__Plant__Pipe13__XTSS",
            "Sumo__Plant__CSTR__kLaGO2",
            "Sumo__Plant__CSTR2__kLaGO2",
            "Sumo__Plant__CSTR2__SNOx",
            "Sumo__Plant__CSTR3__kLaGO2",
            "Sumo__Plant__CSTR4__kLaGO2",

        ],
        jobData={
            "t": [],
            "Q_Inf": [],
            "Q_Eff": [],
            "Q_WAS": [],
            "Q_RAS": [],
            "Q_IMLR": [],
            "CSTR2_SNOx": [],
            "Eff_SNHx": [],
            "Eff_TCOD": [],
            "Eff_TN": [],
            "Eff_TBOD_5": [],
            "Eff_SNOx": [],
            "Eff_SKN": [],
            "Eff_XTSS": [],
            "WAS_XTSS": [],
            "kLa_CSTR": [],
            "kLa_CSTR2": [],
            "kLa_CSTR3": [],
            "kLa_CSTR4": [],
            "OPEXplant_d": [],
            "wait_for_save": False,
            ds.sumo.persistent: True
        }
    )

    while ds.sumo.scheduledJobs > 0:
        time.sleep(0.1)


    for jd in ds.sumo.jobData.values():
        Q_inf = jd["Q_Inf"][-1]
        Q_IMLR = jd["Q_IMLR"][-1]
        Q_WAS = jd["Q_WAS"][-1]
        Q_RAS = jd["Q_RAS"][-1]
        Q_Eff = jd["Q_Eff"][-1]
        Eff_SNHx = jd["Eff_SNHx"][-1]
        CSTR2_SNOx=jd["CSTR2_SNOx"][-1]
        OPEXplant_d = jd["OPEXplant_d"][-1]
        Eff_TCOD = jd["Eff_TCOD"][-1]
        Eff_TN = jd["Eff_TN"][-1]
        Eff_TBOD_5 = jd["Eff_TBOD_5"][-1]
        Eff_SNOx = jd["Eff_SNOx"][-1]
        Eff_SKN = jd["Eff_SKN"][-1]
        Eff_XTSS = jd["Eff_XTSS"][-1]
        kLa_CSTR = jd["kLa_CSTR"][-1]
        kLa_CSTR2 = jd["kLa_CSTR2"][-1]
        kLa_CSTR3 = jd["kLa_CSTR3"][-1]
        kLa_CSTR4 = jd["kLa_CSTR4"][-1]
        WAS_XTSS = jd["WAS_XTSS"][-1]
        break

    EQI = (2 * Eff_XTSS + Eff_TCOD + 30 * Eff_SKN + 10 * Eff_SNHx + 2 * Eff_TBOD_5) * Q_Eff / 1000

    AE = (DO_sat / (1.8 * 1000)) * (V_CSTR * kLa_CSTR + V_CSTR2 * kLa_CSTR2 + V_CSTR3 * kLa_CSTR3 + V_CSTR4 * kLa_CSTR4)
    PE = 0.004 * Q_IMLR + 0.008 * Q_RAS + 0.05 * Q_WAS
    Power = PE + AE

    ME_CSTR = 24 * 0.005 * V_CSTR * kLa_CSTR if kLa_CSTR < 20 else 0
    ME_CSTR2 = 24 * 0.005 * V_CSTR2 * kLa_CSTR2 if kLa_CSTR2 < 20 else 0
    ME_CSTR3 = 24 * 0.005 * V_CSTR3 * kLa_CSTR3 if kLa_CSTR3 < 20 else 0
    ME_CSTR4 = 24 * 0.005 * V_CSTR4 * kLa_CSTR4 if kLa_CSTR4 < 20 else 0
    ME = ME_CSTR + ME_CSTR2 + ME_CSTR3 + ME_CSTR4
    SP = (1 / 1000) * WAS_XTSS * Q_WAS
    OCI = AE + PE + ME + 5 * SP

    print('EQI=', EQI)
    print('OPEXplant_d=', OPEXplant_d)
    print('Eff_TCOD=', Eff_TCOD)
    print('Eff_SNHx=', Eff_SNHx)
    print('Eff_TN=', Eff_TN)


    ds.sumo.cleanup()

    return job, EQI, OCI, Power, OPEXplant_d, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN


def data_callback(job, data):
    jobData = ds.sumo.getJobData(job)
    jobData["t"].append(data["Sumo__Time"] / dtool.day)
    jobData["Q_Inf"].append(data["Sumo__Plant__Influent__Q"])
    jobData["Q_Eff"].append(data["Sumo__Plant__Effluent__Q"])
    jobData["Q_IMLR"].append(data["Sumo__Plant__Pipe9__Q"])
    jobData["Q_RAS"].append(data["Sumo__Plant__Pipe12__Q"])
    jobData["Q_WAS"].append(data["Sumo__Plant__Pipe13__Q"])
    jobData["Eff_SNHx"].append(data["Sumo__Plant__Effluent__SNHx"])
    jobData["Eff_TCOD"].append(data["Sumo__Plant__Effluent__TCOD"])
    jobData["Eff_TN"].append(data["Sumo__Plant__Effluent__TN"])
    jobData["Eff_TBOD_5"].append(data["Sumo__Plant__Effluent__TBOD_5"])
    jobData["Eff_SNOx"].append(data["Sumo__Plant__Effluent__SNOx"])
    jobData["Eff_SKN"].append(data["Sumo__Plant__Effluent__SKN"])
    jobData["Eff_XTSS"].append(data["Sumo__Plant__Effluent__XTSS"])
    jobData["CSTR2_SNOx"].append(data["Sumo__Plant__CSTR2__SNOx"])
    jobData["WAS_XTSS"].append(data["Sumo__Plant__Pipe13__XTSS"])
    jobData["kLa_CSTR"].append(data["Sumo__Plant__CSTR__kLaGO2"])
    jobData["kLa_CSTR2"].append(data["Sumo__Plant__CSTR2__kLaGO2"])
    jobData["kLa_CSTR3"].append(data["Sumo__Plant__CSTR3__kLaGO2"])
    jobData["kLa_CSTR4"].append(data["Sumo__Plant__CSTR4__kLaGO2"])
    jobData["OPEXplant_d"].append(data["Sumo__Plant__CostCenter__OPEXplant_d"])


def msg_callback(job, msg):
    print(f"#{job} {msg}")
    save_finished = msg.startswith("530045")
    jobData = ds.sumo.getJobData(job)

    if (ds.sumo.isSimFinishedMsg(msg)):
        dtool.log_print("Sending save state...")
        jobData["wait_for_save"] = True
        ds.sumo.sendCommand(job, "save tmp_state.xml;")

    if jobData["wait_for_save"] and save_finished:
        dtool.log_print("Save state finished, terminating Sumo.")
        jobData["wait_for_save"] = False
        ds.sumo.finish(job)


def reward_function(EQI, OCI, OPEXplant_d, Power, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN, DO, IMLR, Carbon):
    reward = 0

    # Rule_based_Control_simulation_test_flow1_20250601. 合规性基础奖励
    if Eff_TCOD <= 40 and Eff_SNHx <= 3 and Eff_TN <= 15:
        reward += 1.0  # 基础合格奖励
        if CSTR2_SNOx > 1:
            reward += 0.1

        # 2. 运维优化目标（越低越好）
        reward += 800 / (OPEXplant_d + 1)
        reward += 300 / (EQI + 1)
        reward += 400 / (OCI + 1)
        reward += 100 / (Power + 1)

        # 3. 引导三维控制变量同步节约（非线性）
        reward += 0.2 * (1 - DO / DO_sat)**2
        reward += 0.2 * (1 - IMLR / 70000)**2
        reward += 0.2 * (1 - Carbon / 5)**2

    else:
        # 若超标严重，惩罚固定值
        reward = -1

    return reward


main()



