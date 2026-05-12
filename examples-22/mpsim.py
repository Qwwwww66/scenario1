import dynamita.scheduler as ds
import dynamita.tool as dtool
import time

sumo_project = "mpexample.sumo"
model = "sumoproject.dll"

# When to stop the simulation (in days).
TargetStopTime = 0.2


dynamic_cmd = (
    f"set Sumo__StopTime {int(TargetStopTime * dtool.day)};"
    f"set Sumo__DataComm {dtool.minute};"
    "maptoic;"
    "mode dynamic;"
    "start;"
)

def test():
    dtool.extract_dll_from_project(sumo_project, model)
    dtool.extract_parameters_from_project(sumo_project, ".", "init.scs", "")

    SNHx = run(muNITO=0.9, KNHx_NITO_AS=0.7)
    print(f"SNHx at day 0.2 is {SNHx} (muNITO: 0.9, KNHx_NITO_AS: 0.7)")


def run(muNITO, KNHx_NITO_AS):
    ds.sumo.setParallelJobs(1)
    # ds.sumo.setLogDetails(6) # Use this for debugging.
    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    # Starting a steady state simulation with the given muNITO and KNHx_NITO_AS.
    job = ds.sumo.schedule(
        model,
        commands  = ["execute init.scs",
                    f"set Sumo__Plant__param__Sumo1__muNITO {muNITO};",
                    f"set Sumo__Plant__param__Sumo1__KNHx_NITO_AS {KNHx_NITO_AS};"
                    "mode steady",
                    "start"
                    ],
        variables = ["Sumo__Time",
            "Sumo__Plant__Effluent__SNHx"
        ],
        # Job data to collect simulation results and to store some flags, e.g.:
        # simulation mode (steady or not) and persistent mode.
        jobData    = {
            "steady": True,
            "t": 0.0,
            "SNHx": 0.0,
            ds.sumo.persistent: True
        }
    )

    while (ds.sumo.scheduledJobs > 0):
        time.sleep(0.1)

    # The simulation is finished at this point, extracting the SNHx value from
    # the job data. It was stored in the data_callback function.
    jd = ds.sumo.getJobData(job)
    SNHx = jd["SNHx"]
    ds.sumo.cleanup()
    return SNHx


def data_callback(job, data):
    jobData = ds.sumo.getJobData(job)

    # Extracting the effluent ammonia in dynamic mode (not steady state mode),
    # and storing in the job data at the target time.
    if not jobData["steady"]:
        # Sumo__Time is in milliseconds, converting to days.
        t = data["Sumo__Time"] / dtool.day
        if t == TargetStopTime:
            jobData["t"] = t
            jobData["SNHx"] = data["Sumo__Plant__Effluent__SNHx"]


def msg_callback(job, msg):
    # print(f"#{job} {msg}")
    if (ds.sumo.isSimFinishedMsg(msg)):
        jobData = ds.sumo.getJobData(job)
        # When the steady state simulation is finished we continue with
        # a dynamic simulation. We set the initial conditions of the dynamic
        # simulation to the results of the steady state using the 'maptoic'
        # command in the dynamic commands.
        if jobData["steady"]:
            jobData["steady"] = False
            ds.sumo.sendCommand(job, dynamic_cmd)
        else:
            ds.sumo.finish(job)


# Calling test() only when this file is executed and not when imported.
if __name__ == "__main__":
    test()
