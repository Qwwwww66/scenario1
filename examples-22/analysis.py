import dynamita.scheduler as ds
import dynamita.tool as dtool
import time
import matplotlib.pyplot as plt

sumo_project = "Python example.sumo"
model = "sumoproject.dll"


def main():
    dtool.extract_dll_from_project(sumo_project, model)
    dtool.extract_parameters_from_project(sumo_project, ".", "init.scs", "")

    ds.sumo.setParallelJobs(4)
    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    for jV in range(10, 1510, 100):
        # Starting a new simulation for every volume (job volume).
        ds.sumo.schedule(
            model,
            commands  = ["execute init.scs",
                        f"set Sumo__Plant__CSTR2__param__L_Vtrain {jV}",
                        "mode steady",
                        "start"
                        ],
            variables = ["Sumo__Time",
                        "Sumo__Plant__Effluent__SNOx",
                        ],
            # Job data accessed by the getJobData(job) API function in call-backs.
            # The 0 in the "SNOx" slot is just a placeholder, data_callback will
            # fill the slot with the proper values.
            jobData   = {
                "Vtrain": jV,
                "SNOx": 0,
                ds.sumo.persistent: True
            }
        )

    print("Jobs started:", ds.sumo.scheduledJobs)

    # Waiting for the jobs to finish.
    while (ds.sumo.scheduledJobs > 0):
        time.sleep(0.1)

    snox = []
    Vtrain = []

    fig, ax = plt.subplots(1, 1)
    for jd in ds.sumo.jobData.values():
        Vtrain.append(jd["Vtrain"])
        snox.append(jd["SNOx"])

    ax.plot(Vtrain, snox)
    fig.suptitle("Effluent SNOx dependence on the volume of the anoxic reactor")
    ax.set_xlabel('V train (m3)')
    ax.set_ylabel('Effluent SNOx (g N.m-3)')
    plt.show()

    ds.sumo.cleanup()


def data_callback(job, data):
    jobData = ds.sumo.getJobData(job)
    jobData["SNOx"] = data["Sumo__Plant__Effluent__SNOx"]


def msg_callback(job, msg):
    print(f"#{job} {msg}")
    # In case of simulation finished sumocore message and end simulation
    if (ds.sumo.isSimFinishedMsg(msg)):
        ds.sumo.finish(job)


main()
