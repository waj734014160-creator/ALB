# -- coding: utf-8 --
import ross as rs

from ALB.core import TimeIter
from ALB.physics.bearing import HydrostaticBearing
from ALB.couple import RsRotorBearingCouple
from ALB.rotor import RossRotor, ShaftElement

if __name__ == "__main__":
    ls = [0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08]
    ids = [0, 0, 0, 0, 0, 0, 0, 0]
    ods = [0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08]

    ps = 10e6

    w_hz = 50
    w_rpm = w_hz * 60
    t = TimeIter(0, 10, 50000)
    dt = t.dt

    al = 0.25
    onx = 4
    onz = 3
    ops = [
        [1 / onx * i, al + j * (1 - 2 * al) / (onz - 1)]
        for i in range(onx)
        for j in range(onz)
    ]
    cq = 0.1

    steel = rs.Material(name="Steel", rho=7850, E=2.1e11, G_s=8.08e10)
    steel.save_material()

    r_elems = [
        ShaftElement(
            L=l,
            idl=ind,
            odl=od,
            material=steel,
            shear_effects=True,
            rotary_inertia=True,
            gyroscopic=True,
        )
        for l, ind, od in zip(ls, ids, ods)
    ]
    # ㄤ ＄ ㄧ ぇ
    bearing0 = [rs.BearingElement(n=0, kxx=6e7, kyy=6e7, cxx=6e3, cyy=6e3, n_link=8)]
    bearing1 = [rs.BearingElement(n=7, kxx=6e7, kyy=6e7, cxx=6e3, cyy=6e3)]
    bearings = bearing0 + bearing1

    disk0 = rs.DiskElement(n=4, m=150, Id=2.407, Ip=4.814)
    disks = [disk0]

    rr = rs.Rotor(
        shaft_elements=r_elems, disk_elements=disks, bearing_elements=bearings
    )
    rr = RossRotor(rr, w_hz, dt)

    # bearing = HydrostaticBearing(e=0.0, angel=0, nx=60, nz=60, w=w_rpm, vib=False, vf=1, c=120E-6)
    # # bearing.add_orifices_by_cq([0.5, 0.25, 0.5, 0.5, 0.5, 0.75], pressure=ps, cq=cq)
    # bearing1 = HydrostaticBearing(e=0.0, angel=0, nx=60, nz=60, w=w_rpm, vib=False, vf=1, c=120E-6)
    # bearing.node_link = 7
    # bearing1.node_link = 1

    rbc = RsRotorBearingCouple(rr, t)
    rbc.add_gravity()
    rbc.add_unbalance(node_link=4, phase=0, t_max=1, m=0.01, rpm=w_rpm, e=0.2)
    rbc.add_unbalance(node_link=5, phase=0, t_max=1, m=0.01, rpm=w_rpm, e=0.2)
    rbc.solve()
    res = rr.results()
    import plotly

    plotly.offline.plot(res.plot_3d())
