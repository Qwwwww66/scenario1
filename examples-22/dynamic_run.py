import dynamita.scheduler as ds
import dynamita.tool as dtool
import time
import matplotlib.pyplot as plt

sumo_project = "Dynamic Python example.sumo"
model = "sumoproject.dll"


# Command for dynamic run. It is a one liner, we need the semicolon separators.
dynamic_cmd = (
    f"set Sumo__StopTime {dtool.day};"
    f"set Sumo__DataComm {dtool.hour};"
    "maptoic;"
    "mode dynamic;"
    "start"
)

def main():
    dtool.extract_dll_from_project(sumo_project, model)
    dtool.extract_parameters_from_project(sumo_project, ".", "init.scs", "")

    ds.sumo.setParallelJobs(4)
    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    for SRT2_Target in [5, 8, 11, 15]:
        ds.sumo.schedule(
            model,
            commands  = ["execute init.scs",
                        f"set Sumo__Plant__param__SRT2_target {SRT2_Target}",
                        "mode steady",
                        "start"
                        ],
            variables = ["Sumo__Time",
                        "Sumo__Plant__Effluent__SNHx"
                        ],
            # Job data accessed by the getJobData(job) API function in call-backs.
            jobData    = {
                "SRT2_Target": SRT2_Target,
                "SNHx": [],
                "t": [],
                "steady": True,
                ds.sumo.persistent: True
            }
        )

    print("Jobs started:", ds.sumo.scheduledJobs)

    while (ds.sumo.scheduledJobs > 0):
        time.sleep(0.1)

    fig, axes = plt.subplots(1, 1)
    for jd in ds.sumo.jobData.values():
        plot_data(jd, axes)
    fig.suptitle("Flow dependence of effluent SNHx for various SRT2 targets")
    axes.set_xlabel('Time (days)')
    axes.set_ylabel('Total Effluent SNHx (g N.m-3)')
    axes.legend(loc='center right', title='SRT2 Target (d)')
    plt.show()

    ds.sumo.cleanup()


def data_callback(job, data):
    jobData = ds.sumo.getJobData(job)

    if not jobData["steady"]:
        t = jobData["t"]
        t.append(data["Sumo__Time"] / dtool.day)
        snhx = jobData["SNHx"]
        snhx.append(data["Sumo__Plant__Effluent__SNHx"])


def msg_callback(job, msg):
    print(f"#{job} {msg}")
    if (ds.sumo.isSimFinishedMsg(msg)):
        jobData = ds.sumo.getJobData(job)
        if jobData["steady"]:
            jobData["steady"] = False
            ds.sumo.sendCommand(job, dynamic_cmd)
        else:
            ds.sumo.finish(job)


def plot_data(jobData, axes):
    t = jobData["t"]
    snhx_storage = jobData["SNHx"]
    SRT2_Target = jobData["SRT2_Target"]

    axes.plot(t, snhx_storage, label=str(SRT2_Target))


main()
