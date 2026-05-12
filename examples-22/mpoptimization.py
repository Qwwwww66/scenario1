import time
import dynamita.scheduler as ds
import dynamita.tool as dtool
import mpsim as sim
from scipy.optimize import minimize


# The effluent ammonia value we want to optimize for.
Eff_SNHx_Target = 2.0

def main():
    dtool.extract_dll_from_project(sim.sumo_project, sim.model)
    dtool.extract_parameters_from_project(sim.sumo_project, ".", "init.scs", "")

    # Start from these values: muNITO=0.9, KNHx_NITO_AS=0.7
    x_0 = [0.9, 0.7]
    # The 'minimize' function will call 'obj_fun' with various x values, starting
    # from x_0, to try to minimize the error returned by 'obj_fun'.
    minimize(obj_fun, x_0, method='nelder-mead', options={'xtol': 1e-4, 'disp': True})


# The objective function runs a simulation with values guessed by the
# optimization algorithm and returns an error value.
# 'x' - is an array of parameters.
def obj_fun(x):
    # Passing the x[0] which is the muNITO guess and x[1], which is the KNHx_NITO_AS guess.
    Eff_SNHx = sim.run(x[0], x[1])
    print(f"Trying muNITO: {x[0]:.9f} and KNHx_NITO_AS: {x[1]:.9f} gives Effluent__SNHx: {Eff_SNHx:.9f}")
    err = (Eff_SNHx_Target - Eff_SNHx)**2

    return err

main()
