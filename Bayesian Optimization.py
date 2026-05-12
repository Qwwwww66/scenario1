import shutil
import os
import dynamita.scheduler as ds
import dynamita.tool as dtool
import time
import pandas as pd
import warnings
warnings.filterwarnings('ignore')



from skopt import gp_minimize
from skopt.space import Real, Integer



test_data_path = 'data/flow_profile.xlsx'
initial_state_folder = 'initial state'
initial_state_filename = 'episode_initial_state.xml'



test_data = pd.read_excel(test_data_path)
test_data = test_data[::]
start_row = 0
end_row = 25
test_data = test_data.iloc[start_row:end_row]
test_data = test_data.reset_index(drop=True)
print(test_data.head())

print(len(test_data))


DO_sat=9.458
V_CSTR=750 #m3
V_CSTR2=1500 #m3
V_CSTR3=3000 #m3
V_CSTR4=1500 #m3



def run_sim_multiple_param(model, init_file, Q_inf, Inf_TCOD, Inf_TKN, CSTR3__DOSP, Q_IMLR, Carbon):

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
    AE = (DO_sat / (1.8 * 1000)) * (V_CSTR * kLa_CSTR + V_CSTR2 * kLa_CSTR2 + V_CSTR3 * kLa_CSTR3+ V_CSTR4 * kLa_CSTR4)
    PE = 0.004 * Q_IMLR + 0.008 * Q_RAS + 0.05 * Q_WAS

    Power = PE + AE
    ME_CSTR = 24 * 0.005 * V_CSTR * kLa_CSTR if kLa_CSTR < 20 else 0
    ME_CSTR2 = 24 * 0.005 * V_CSTR2 * kLa_CSTR2 if kLa_CSTR2 < 20 else 0
    ME_CSTR3 = 24 * 0.005 * V_CSTR3 * kLa_CSTR3 if kLa_CSTR3 < 20 else 0
    ME_CSTR4 = 24 * 0.005 * V_CSTR4 * kLa_CSTR4 if kLa_CSTR4 < 20 else 0

    ME = ME_CSTR + ME_CSTR2 + ME_CSTR3 + ME_CSTR4
    SP = (1 / 1000) * WAS_XTSS * Q_WAS

    OCI = AE + PE + ME + 5 * SP

    ds.sumo.cleanup()

    print('Eff_TCOD=', Eff_TCOD)
    print('Eff_SNHx=', Eff_SNHx)
    print('Eff_TN=', Eff_TN)

    return job, OPEXplant_d, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN


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


space = [
    Real(0.5, 3, name='DO'),
    Integer(17280, 69120, name='IMLR'),
    Real(0, 5, name='Carbon')
]


def objective(CSTR3__DOSP, Q_IMLR, Carbon, model, init_file, Q_inf, Inf_TCOD, Inf_TKN):
    # 调用模拟函数，只关注cost
    job, OPEXplant_d, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN \
        = run_sim_multiple_param(model, init_file, Q_inf, Inf_TCOD, Inf_TKN, CSTR3__DOSP, Q_IMLR, Carbon)
    penalty = 0
    if Eff_TN >= 15:
        penalty += 10000
    if CSTR2_SNOx < 1:
        penalty += 1000
    if Eff_SNHx > 3:
        penalty += 10000
    if Eff_TCOD > 40:
        penalty += 10000

    print('penalty=', penalty)
    return OPEXplant_d + penalty


# 为每个测试数据点进行优化的函数
def optimize_for_episode(model, init_file, episode):
    Q_inf = test_data.at[episode, 'Influent Flow Rate (m3/d)']
    Inf_TCOD = 300
    Inf_TKN = 42

    print('Q_inf=', Q_inf, 'Inf_TCOD=', Inf_TCOD, 'Inf_TKN=', Inf_TKN)

    result = gp_minimize(
        lambda x: objective(x[0], x[1], x[2], model, init_file, Q_inf, Inf_TCOD, Inf_TKN),
        space,
        n_initial_points=10,
        n_calls = 10,
        random_state=42,
        acq_func="EI"
    )


    best_params = result.x

    return best_params, result.fun


def main():
    sumo_project = "AA'OA' Intelligent Control.sumo"
    model = "sim.dll"
    dtool.extract_dll_from_project(sumo_project, model)
    init_file = "init.scs"
    dtool.extract_parameters_from_project(sumo_project, ".", "init.scs", "")

    ds.sumo.setParallelJobs(1)
    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    results_df = pd.DataFrame(columns=[
        'Episode', 'Time', 'DO', 'IMLR', 'Carbon', 'Best Cost'
    ])

    for episode in range(len(test_data)):
        print("Episode: ", episode)

        if episode == 0:
            src_path = os.path.join(initial_state_folder, initial_state_filename)
            dst_path = "episode_initial_state.xml"
            # 如果同级目录已经有这个文件，也要覆盖
            shutil.copyfile(src_path, dst_path)
            print(f"Copied '{src_path}' → '{dst_path}'")



        best_params, best_cost = optimize_for_episode(model, init_file, episode)
        print('best_params=', best_params)
        best_cost = round(best_cost, 1)

        current_time_point = test_data.at[episode, 'Time']


        new_row = pd.DataFrame({
            'Episode': [episode],
            'Time': [current_time_point],
            'DO': [best_params[0]],
            'IMLR': [best_params[1]],
            'Carbon': [best_params[2]],
            'Best Cost': [best_cost]
        })
        results_df = pd.concat([results_df, new_row], ignore_index=True)

        Q_inf = test_data.at[episode, 'Influent Flow Rate (m3/d)']
        Inf_TCOD = 300
        Inf_TKN = 42

        _, _, _, Eff_TCOD, Eff_SNHx, Eff_TN = run_sim_multiple_param(model, init_file, Q_inf, Inf_TCOD, Inf_TKN, *best_params)

        print('Q_inf=', Q_inf)
        print('End of episode Eff_TCOD=', Eff_TCOD)
        print('End of episode Eff_SNHx=', Eff_SNHx)
        print('End of episode Eff_TN=', Eff_TN)

        os.replace("tmp_state.xml", "episode_initial_state.xml")
        print('episode_initial_state modified')

    results_df.to_excel('Initial Action Points After BO.xlsx', index=False)



    # 输出每个episode的优化结果和job
    for index, row in results_df.iterrows():
        print(
            f"Episode {row['Episode']}: Best Parameters = DO: {row['DO']}, IMLR: {row['IMLR']}, Carbon: {row['Carbon']}, Best Cost = {row['Best Cost']}")



main()