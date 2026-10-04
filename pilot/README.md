# Pilot figure: does the forecaster respect the power curve?

`pilot_power_curve.py` trains two CNN-GRU models on one turbine's 10-min SCADA
data and plots each test forecast as a (forecast wind, forecast power) point on
the measured power curve.

| Model | Loss | Output |
| --- | --- | --- |
| Plain CNN-GRU | MSE on power + wind | unbounded |
| CNN-GRU + physics loss | MSE + capacity + power-curve band + cut-in/cut-out + wind-power consistency | clamped to [0, rated] |

Markers in the figure:

- **Red cross:** impossible (power below 0 or above rated)
- **Orange circle:** off the curve (power outside the band for the model's own wind forecast)
- **Blue dot:** physically consistent

## Run it

```bash
pip install numpy pandas matplotlib torch

# 1. Test the code without any download (writes a SYNTHETIC figure)
python pilot_power_curve.py --synthetic

# 2. Real data: Kelmarsh wind farm, turbine 1
#    Download the SCADA zip for one year from https://zenodo.org/records/16807551
#    and unzip it next to this script, then:
python pilot_power_curve.py --data "Turbine_Data_Kelmarsh_1_*.csv" --rated 2050
```

Outputs: `pilot_power_curve.png` (300 dpi, for the concept note) and
`pilot_metrics.csv` (RMSE, MAE and violation rates).

If a column is not found, the script prints the available column names. Pass
the right ones with `--wind_col`, `--power_col` and `--dir_col` (any part of the
name is enough). Other options: `--horizon` (steps ahead, 6 = 1 h),
`--lookback`, `--epochs` and the penalty weights `--lam_*`.

`example_synthetic.png` shows the output on synthetic data. It is a code test
only and must not be used as a result.
