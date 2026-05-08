# -- coding: utf-8 --
import matplotlib.pyplot as plt
import numpy as np
import plotly.offline
import ross as rs
import scipy.fft

from ALB.base import TimeIter
from ALB.rotor import RossRotor, UnbalancedExcitation

if __name__ == "__main__":
    start = 0
    end = 5
    time_steps = 50000

    lt = TimeIter(start, end, time_steps)
    speed = 3000 / 60
    steel = rs.Material(name="Steel", rho=7, E=1.99948e11, G_s=7.69041e10)
    Ls = [0.02, 0.03, 0.03, 0.02]
    iD = [0, 0, 0, 0]
    oD = [0.02, 0.03, 0.03, 0.02]
    shaft_elem = [
        rs.ShaftElement(
            L=L,
            idl=i,
            odl=o,
            material=steel,
            shear_effects=True,
            rotary_inertia=True,
            gyroscopic=True,
        )
        for L, i, o in zip(Ls, iD, oD)
    ]

    bearing0 = rs.BearingElement(0, kxx=7e8, kyy=7e8, kxy=0, kyx=0, cxx=7e6, cyy=7e6)
    bearing1 = rs.BearingElement(4, kxx=7e8, kyy=7e8, kxy=0, kyx=0, cxx=7e6, cyy=7e6)

    bearings = [bearing0, bearing1]

    disk0 = rs.DiskElement(n=2, m=0.12641, Id=3.33628e-05 / 2, Ip=3.33628e-05)
    pointmass = []
    disks = []

    rotor1 = rs.Rotor(shaft_elem, disks, bearings, pointmass)
    rotor1.plot_rotor()
    plotly.offline.plot(rotor1.plot_rotor())
    dt = lt.dt
    rr = RossRotor(rotor1, speed, dt, discrete=False)
    forces = []
    add_node = 2
    rr_output = []
    for time in lt():
        # force = ubf.__call__(time, 0.1, speed * 60, 0.1, no_step=False)
        force = [
            3000 * np.cos(time * speed * 2 * np.pi),
            3000 * np.sin(time * speed * 2 * np.pi),
        ]
        rr.input_force2node(time, force, add_node)
        rr_output.append(rr.output(node=add_node))
        forces.append(force)
    rrp = rr.results()
    yout = rrp.yout[:, 0:2]
    plotly.offline.plot(rrp.plot_3d())
    forces = np.array(forces)

    F = np.zeros((len(lt.t_list), rotor1.ndof))
    F[:, 4 * add_node + 0] = forces[:, 0]
    F[:, 4 * add_node + 1] = forces[:, 1]
    rp = rotor1.run_time_response(speed, F, lt.t_list)
    plotly.offline.plot(rp.plot_3d())
    yout1 = rp.yout[:, 0:2]

    sys = rr._sys
    import scipy.signal as ss

    t, yout2, xout2 = ss.dlsim(sys.to_discrete(dt), F, lt.t_list)
    yout2 = yout2[:, 0:2]
    ps = 0.5
    pe = 0.51
    ps = int(ps * time_steps)
    pe = int(pe * time_steps)

    plt.plot(yout[ps:pe, 0])
    plt.plot(yout1[ps:pe, 0])
    plt.plot(yout2[ps:pe, 0])
    plt.show()

    plt.plot(yout[:, 0], yout[:, 1])
    plt.plot(yout1[:, 0], yout1[:, 1])
    plt.plot(yout2[:, 0], yout2[:, 1])
    plt.show()

    fft_slice = [0.3, 0.9]
    fft_slice = np.round(np.array(fft_slice) * time_steps)
    fft_slice = fft_slice.astype(int)
    fft0 = (
        scipy.fft.rfft(forces[fft_slice[0] : fft_slice[1], 0])
        / (fft_slice[1] - fft_slice[0])
        * 2
    )
    fft0 = np.abs(fft0)

    freq0 = scipy.fft.rfftfreq(fft_slice[1] - fft_slice[0], d=lt.dt)
    max_amp = max(np.abs(fft0))
    print("max_amp: ", max_amp)
    plt.plot(freq0, fft0)
    plt.show()

    xout = rrp.xout
    plt.plot(xout[400:500, 17])
