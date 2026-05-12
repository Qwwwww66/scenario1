import os
import shutil
import dynamita.scheduler as ds
import dynamita.tool as dtool
import time
from scipy.optimize import minimize
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import optim
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
NUM_STATES = 6
NUM_ACTIONS = 7
EPSILON = 0.9
GAMMA = 0.9
LR = 0.01
MEMORY_CAPACITY = 40
Q_NETWORK_ITERATION = 100
BATCH_SIZE = 32
EPISODES = 400

train_data_path = 'RL train and test data/train data.xlsx'
test_data_path = 'data/test data.xlsx'
RL_model_path = 'RL models/'
initial_state_folder = 'initial state'
initial_state_filename = 'episode_initial_state.xml'


DO_sat=9.458
V_CSTR=750 #m3
V_CSTR2=1500 #m3
V_CSTR3=3000 #m3
V_CSTR4=1500 #m3


class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()

        self.fc1 = nn.Linear(NUM_STATES, 30)
        self.fc1.weight.data.normal_(0, 0.1)
        self.fc2 = nn.Linear(30, NUM_ACTIONS)
        self.fc2.weight.data.normal_(0, 0.1)

    def forward(self, x):
        x = self.fc1(x)
        x = F.relu(x)
        x = self.fc2(x)
        return x

class Dqn():
    def __init__(self):
        self.eval_net, self.target_net = Net().to(device), Net().to(device)
        self.memory = np.zeros((MEMORY_CAPACITY, NUM_STATES * 2 + 2))
        self.memory_counter = 0
        self.learn_counter = 0
        self.optimizer = optim.Adam(self.eval_net.parameters(), LR)
        self.loss = nn.MSELoss()
        self.epsilon = EPSILON
        self.epsilon_min = 0.1
        self.epsilon_decay = 0.995
        self.device = device
        self.fig, self.ax = plt.subplots()

    def store_trans(self, state, action, reward, next_state):
        if self.memory_counter % 500 == 0:
            print("The experience pool collects {} time experience".format(self.memory_counter))
        index = self.memory_counter % MEMORY_CAPACITY
        trans = np.hstack((state, [action], [reward], next_state))
        self.memory[index,] = trans
        self.memory_counter += 1

    def choose_action(self, state):
        state = torch.unsqueeze(torch.FloatTensor(state).to(self.device), 0)
        if np.random.rand() < self.epsilon:
            action = np.random.randint(0, NUM_ACTIONS)
        else:
            action_value = self.eval_net.forward(state)
            action = torch.max(action_value, 1)[1].item()
        return action



    def plot(self, ax, x):
        ax.cla()
        ax.set_xlabel("episode")
        ax.set_ylabel("total reward")
        ax.plot(x, 'b-')
        plt.pause(0.000000000000001)

    def learn(self):
        if self.learn_counter % Q_NETWORK_ITERATION == 0:
            self.target_net.load_state_dict(self.eval_net.state_dict())
        self.learn_counter += 1

        sample_index = np.random.choice(MEMORY_CAPACITY, BATCH_SIZE)
        batch_memory = self.memory[sample_index, :]
        batch_state = torch.FloatTensor(batch_memory[:, :NUM_STATES]).to(device)
        batch_action = torch.LongTensor(batch_memory[:, NUM_STATES:NUM_STATES + 1].astype(int)).to(device)
        batch_reward = torch.FloatTensor(batch_memory[:, NUM_STATES + 1: NUM_STATES + 2]).to(device)
        batch_next_state = torch.FloatTensor(batch_memory[:, -NUM_STATES:]).to(device)

        q_eval = self.eval_net(batch_state).gather(1, batch_action)
        q_next = self.target_net(batch_next_state).detach()
        q_target = batch_reward + GAMMA * q_next.max(1)[0].view(BATCH_SIZE, 1)

        loss = self.loss(q_eval, q_target)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

    def decay_epsilon(self):
        self.epsilon = max(self.epsilon * self.epsilon_decay, self.epsilon_min)

    def save_model(self, path):
        try:
            torch.save(self.eval_net.state_dict(), path)
            print(f"Model successfully saved to {path}")
        except Exception as e:
            print(f"Failed to save model: {e}")


def main():

    sumo_project = "AA'OA'.sumo"
    model = "sim.dll"
    dtool.extract_dll_from_project(sumo_project, model)
    init_file = "init.scs"
    dtool.extract_parameters_from_project(sumo_project, ".", "init.scs", "")

    ds.sumo.setParallelJobs(1)
    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    train_data = pd.read_excel(train_data_path)
    train_data = train_data[::]
    train_data = train_data.reset_index(drop=True)

    net = Dqn()
    print("The DQN is collecting experience...")
    step_counter_list = []

    if not os.path.exists(RL_model_path):
        os.makedirs(RL_model_path)

    for episode in range(len(train_data)):
        print('len(train_data)=',len(train_data))
        print('episode=', episode)

        if episode == 0:
            src_path = os.path.join(initial_state_folder, initial_state_filename)
            dst_path = "episode_initial_state.xml"
            # 如果同级目录已经有这个文件，也要覆盖
            shutil.copyfile(src_path, dst_path)
            print(f"Copied '{src_path}' → '{dst_path}'")

        DO_initial=2
        Q_IMLR_initial=40000
        #SRT_initial=15
        Carbon_initial = 0

        COD_inf = 300
        TKN_inf = 42

        state = [train_data.at[episode, 'Influent Flow Rate (m3/d)'],
                 COD_inf,
                 TKN_inf,
                 DO_initial,
                 Q_IMLR_initial,
                 Carbon_initial]

        next_state = state
        step_counter = 0
        print('episode=', episode)
        for step in range(20):
            step_counter += 1
            # env.render()
            action = net.choose_action(state)
            if action == 0:
                next_state[3] = max(0.5, state[3] - 0.5)
            if action == 1:
                next_state[3] = min(3, state[3] + 0.5)
            if action == 2:
                next_state[4] = max(17280, state[4] -10000)
            if action == 3:
                next_state[4] = min(69120, state[4] + 10000)
            if action == 4:
                next_state[5] = max(0, state[5] - 0.5)
            if action == 5:
                next_state[5] =min(2.5, state[5] + 0.5)
            if action == 6:
                next_state =state
            job, EQI, OCI, OPEXplant_d, Power, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN = (
                run_sim_multiple_pram(model, init_file, state[0], state[1], state[2], state[3], state[4], state[5])
            )

            print('job=', job, 'EQI=', EQI, 'OCI=', OCI, 'Power=', Power, 'OPEXplant_d=', OPEXplant_d, 'CSTR2_SNOx=', CSTR2_SNOx, 'Eff_TCOD=', Eff_TCOD, 'Eff_SNHx=', Eff_SNHx, 'Eff_TN=', Eff_TN)

            reward = reward_function(EQI, OCI, OPEXplant_d, Power, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN,
                                     next_state[3], next_state[4], next_state[5])
            print('state=', state, 'action=', action, 'reward=', reward)


            net.store_trans(state, action, reward, next_state)

            if net.memory_counter >= MEMORY_CAPACITY:
                net.learn()
                if True:
                    print("episode {}, the reward is {}".format(episode, round(reward, 3)))
            # if True:
            #     step_counter_list.append(step_counter)
            #     net.plot(net.ax, step_counter_list)
            #     break
            state = next_state

        if (episode + 1) % 24 == 0:  # 每24个episodes保存一次模型
            model_filename = f"model_ep{episode + 1}.pth"
            model_save_path = os.path.join(RL_model_path, model_filename)
            net.save_model(model_save_path)

        os.replace("tmp_state.xml", "episode_initial_state.xml")

        net.decay_epsilon()



def run_sim_multiple_pram(model, init_file, Q_inf, Inf_TCOD, Inf_TKN, CSTR3__DOSP, Q_IMLR, Carbon):
    job = ds.sumo.schedule(
        model,
        commands=[
            f"execute {init_file}",
            # The first state.xml needs to be created in Sumo and copied to this folder.
            # The first run will save a new state.xml at the end, overwriting the previous.
            "load episode_initial_state.xml",
            "maptoic",
            f"set Sumo__Plant__Influent__param__TCOD {Inf_TCOD}",
            f"set Sumo__Plant__Influent__param__Q {Q_inf}",
            f"set Sumo__Plant__Influent__param__TKN {Inf_TKN}",
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
    ME = ME_CSTR + ME_CSTR2 + ME_CSTR3+ ME_CSTR4
    SP = (1 / 1000) * WAS_XTSS * Q_WAS
    OCI = AE + PE + ME + 5 * SP

    ds.sumo.cleanup()

    return job, EQI, OCI, OPEXplant_d, Power, CSTR2_SNOx, Eff_TCOD, Eff_SNHx, Eff_TN


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