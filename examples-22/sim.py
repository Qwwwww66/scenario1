import dynamita.scheduler as ds
import dynamita.tool as dtool
import time
import matplotlib.pyplot as plt

sumo_project = "Python example.sumo"
model = "sumoproject.dll"


def main():
    dtool.extract_dll_from_project(sumo_project, model)
    dtool.extract_parameters_from_project(sumo_project, ".", "init.scs", "")

    ds.sumo.setParallelJobs(1)
    # ds.sumo.setLogDetails(6) # Use this for debugging.
    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    ds.sumo.schedule(
        model,
        commands  = ["execute init.scs",
                    f"set Sumo__StopTime {1*dtool.day}",
                    f"set Sumo__DataComm {1*dtool.hour}",
                    "mode dynamic",
                    "start"
                    ],
        variables = ["Sumo__Time",
                    "Sumo__Plant__CSTR3__SNHx",
                    "Sumo__Plant__CSTR3__SNOx",
                    ],
        # Job data accessed by the getJobData(job) API function in call-backs.
        jobData    = {
            "SNHx": [],
            "SNOx": [],
            "t": [],
            ds.sumo.persistent: True
        }
    )

    print("Jobs started:", ds.sumo.scheduledJobs)

    while (ds.sumo.scheduledJobs > 0):
        time.sleep(0.1)

    # Print the header of the result table.
    print("Sumo__Time\tCSTR3__SNHx\tCSTR3__SNOx")

    fig, axes = plt.subplots(1, 1)

    for jd in ds.sumo.jobData.values():
        plot_data(jd, axes)

    fig.suptitle("One day simulation from initial conditions")
    axes.set_xlabel('Time (days)')
    axes.set_ylabel('CSTR3 State variables (g N.m-3)')
    plt.legend(loc='upper right', title='Legend')
    plt.show()

    ds.sumo.cleanup()


def data_callback(job, data):
    jobData = ds.sumo.getJobData(job)
    # Sumo__Time is in milliseconds, convert it to days.
    jobData["t"].append(data["Sumo__Time"] / dtool.day)
    jobData["SNHx"].append(data["Sumo__Plant__CSTR3__SNHx"])
    jobData["SNOx"].append(data["Sumo__Plant__CSTR3__SNOx"])


def msg_callback(job, msg):
    print(f"#{job} {msg}")
    if (ds.sumo.isSimFinishedMsg(msg)):
        ds.sumo.finish(job)


def plot_data(jobData, axes):
    t = jobData["t"]
    snhx = jobData["SNHx"]
    snox = jobData["SNOx"]

    # Print the result points before plotting.
    for i in range(len(t)):
        row = "%.8f" % t[i] + \
            "\t%.8f" % snhx[i] + \
            "\t%.8f" % snox[i]
        print(row)

    axes.plot(t, snhx, label='SNHx')
    axes.plot(t, snox, label='SNOx')


main()
