import dynamita.scheduler as ds
import dynamita.tool as dtool
import time
from scipy.optimize import minimize
import matplotlib.pyplot as plt

sumo_project = "Python example.sumo"
model = "sumoproject.dll"

Eff_SNHx_Target = 1.0
err_acc = []
SNHx_acc = []
DOSP_acc = []

def main():
    dtool.extract_dll_from_project(sumo_project, model)
    dtool.extract_parameters_from_project(sumo_project, ".", "init.scs", "")

    ds.sumo.setParallelJobs(1)
    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    # Start from this value.
    x_0 = [1]
    # The 'minimize' function will call 'obj_fun' with various x values, starting
    # from x_0, to try to minimize the error returned by 'obj_fun'.

    # minimize(obj_fun, x_0, method='Nelder-Mead', bounds=[(0.001, 2.0)], tol=1e-4, options={'disp': True})
    # minimize(obj_fun, x_0, method='COBYLA', tol=1e-4, options={'disp': True})
    # minimize(obj_fun, x_0, method='SLSQP', bounds=[(0.001, 2.0)], tol=1e-4, options={'disp': True})
    minimize(obj_fun, x_0, method='Powell', bounds=[(0.001, 2.0)], tol=1e-4, options={'disp': True})

    fig = plt.figure(figsize=(12, 5))
    axs = fig.subplots(nrows=1, ncols=2)
    axs[0].set_xlabel('Objective function evaluations')
    axs[0].set_ylabel('CSTR3__DOSP (g O2/m3)')
    axs[1].set_xlabel('Objective function evaluations')
    axs[1].set_ylabel('Effluent__SNHx (g N/m3)')

    # Draw blue triangles, b^.
    axs[0].plot(range(len(err_acc)), DOSP_acc, 'b^')
    # Draw green circles, go.
    axs[1].plot(range(len(err_acc)), SNHx_acc, 'go')

    fig.suptitle("Optimization of DOSP in CSTR3 to achieve SNHx = 1 in the effluent")
    # Draw x, y grid lines with 50% transparency.
    axs[0].grid(alpha=0.5)
    axs[1].grid(alpha=0.5)
    plt.show()

# The objective function runs a simulation with a value guessed by the
# optimization algorithm and returns an error value.
# 'x' - is an array of parameters which is a one element array in this case.
def obj_fun(x):
    Eff_SNHx = run_sim(x[0])
    print("Trying CSTR3__DOSP: %.8f" % x[0] + " gives Effluent__SNHx: %.8f" % Eff_SNHx)
    err = (Eff_SNHx_Target - Eff_SNHx)**2

    err_acc.append(err)
    SNHx_acc.append(Eff_SNHx)
    DOSP_acc.append(x[0])

    return err


def run_sim(CSTR3__DOSP):
    ds.sumo.schedule(
        model,
        commands  = ["execute init.scs",
                    f"set Sumo__Plant__CSTR3__param__DOSP {CSTR3__DOSP}",
                    "mode steady",
                    "start"
                    ],
        variables = ["Sumo__Time",
                    "Sumo__Plant__Effluent__SNHx"
                    ],
        jobData   = {
            "Eff_SNHx": 0,
            ds.sumo.persistent: True
        }
    )

    # Waiting for the jobs to finish.
    while (ds.sumo.scheduledJobs > 0):
        time.sleep(0.1)

    Eff_SNHx = 0.0
    for jd in ds.sumo.jobData.values():
        Eff_SNHx = jd["Eff_SNHx"]
        break

    ds.sumo.cleanup()
    return Eff_SNHx


def data_callback(job, data):
    jobData = ds.sumo.getJobData(job)
    jobData["Eff_SNHx"] = data["Sumo__Plant__Effluent__SNHx"]


def msg_callback(job, msg):
    # In case of simulation finished sumocore message and end simulation
    if (ds.sumo.isSimFinishedMsg(msg)):
        ds.sumo.finish(job)


main()
