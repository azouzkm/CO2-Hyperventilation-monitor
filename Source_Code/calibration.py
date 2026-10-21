"""
Calibration + response-time measurement (the core data for the D7 verification report).

Two uses:
1. Calibration: known CO2 concentration -> raw sensor reading, fit m*x+b, compute the RMS residual.
2. Response time: apply a CO2 step, measure the 10%->90% rise time; repeat for different line lengths
   to show that "response time degrades as the line lengthens", supporting your honest declaration.
"""

import numpy as np
import matplotlib.pyplot as plt


def linear_fit(x, y):
    """Return (slope, intercept, rms_residual). x=raw readings, y=true values (percent)."""
    m, b = np.polyfit(x, y, 1)
    fitted = m * np.asarray(x) + b
    rms = float(np.sqrt(np.mean((np.asarray(y) - fitted) ** 2)))
    return m, b, rms


def response_time_10_90(t, signal):
    """
    Given the time series (t, signal) of a step response, return the 10%->90% rise time (seconds).
    Finds the time difference between crossing 10% and 90% of steady state.
    """
    s = np.asarray(signal, dtype=float)
    lo = np.min(s)
    hi = np.max(s)
    t10 = t[np.argmax(s >= lo + 0.10 * (hi - lo))]
    t90 = t[np.argmax(s >= lo + 0.90 * (hi - lo))]
    return float(t90 - t10)


def plot_calibration(x, y, m, b, out="Evidence/Calibration_Data/calibration.png"):
    """Plot the calibration scatter + fitted line + residuals, saved as an evidence image."""
    plt.scatter(x, y, label="data")
    plt.plot(x, m * np.asarray(x) + b, label="fit", color="tab:orange")
    plt.xlabel("sensor raw")
    plt.ylabel("CO2 (percent)")
    plt.legend()
    plt.savefig(out, dpi=150)
    plt.close()


if __name__ == "__main__":
    # TODO: replace the placeholder below with real calibration data
    x = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]   # raw readings
    y = [0.0, 0.9, 2.1, 3.0, 4.2, 5.1]   # true values (percent)
    m, b, rms = linear_fit(x, y)
    print(f"slope={m:.3f} intercept={b:.3f} rms_residual={rms:.3f}")
    plot_calibration(x, y, m, b)
