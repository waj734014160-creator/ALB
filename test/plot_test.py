# -- coding: utf-8 --
import matplotlib.pyplot as plt
import numpy as np

if __name__ == "__main__":
    x = np.linspace(0, 1, 100)

    y = np.sin(x)
    fig, ax = plt.subplots()
    line2 = ax.plot(x[0], y[0], label="123")[0]
    print(line2)
    for i in range(len(x)):
        line2.set_data(x[:i], y[:i])
        plt.pause(0.1)
