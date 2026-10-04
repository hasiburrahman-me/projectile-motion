"""
Pilot figure for the concept note: does the forecaster respect the power curve?

Trains two CNN-GRU models on one turbine's 10-min SCADA data. Both forecast
wind speed AND power at a single horizon (default 1 h ahead):

  * baseline  - plain MSE loss, unbounded outputs (like a standard CNN-GRU)
  * physics   - same network, power bounded to [0, rated] by a sigmoid, plus
                penalties for leaving the power-curve band, for power below
                cut-in / above cut-out, and for (forecast wind, forecast power)
                pairs that disagree with the power curve

The figure plots every test forecast as a point (forecast wind, forecast power)
on top of the measured power curve. A physically consistent forecaster keeps
its points inside the band. Points above rated power, below zero or outside the
band are drawn as red crosses.

Usage
-----
  # Kelmarsh turbine 1 (download the SCADA zip from Zenodo and unzip it first)
  python pilot_power_curve.py --data "Turbine_Data_Kelmarsh_1_*.csv" --rated 2050

  # quick test without any download
  python pilot_power_curve.py --synthetic

Outputs: pilot_power_curve.png, pilot_metrics.csv
"""

import argparse
import glob

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

# ---------------------------------------------------------------- data loading


def find_col(df, key):
    """Return the first column whose name contains `key` (case-insensitive)."""
    for c in df.columns:
        if key.lower() in c.lower():
            return c
    raise KeyError(f"No column containing '{key}'. Columns: {list(df.columns)[:15]} ...")


def read_kelmarsh(pattern, wind_key, power_key, dir_key):
    """Read Kelmarsh/Penmanshiel SCADA CSVs (header line starts with '# Date and time')."""
    frames = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        header = next(i for i, ln in enumerate(lines) if ln.lstrip("# ").lower().startswith("date and time"))
        df = pd.read_csv(path, skiprows=header, low_memory=False)
        df.columns = [c.lstrip("# ").strip() for c in df.columns]
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No files match {pattern}")
    df = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame({
        "time": pd.to_datetime(df[find_col(df, "date and time")]),
        "wind": pd.to_numeric(df[find_col(df, wind_key)], errors="coerce"),
        "power": pd.to_numeric(df[find_col(df, power_key)], errors="coerce"),
        "dir": pd.to_numeric(df[find_col(df, dir_key)], errors="coerce"),
    })
    out = out.sort_values("time").drop_duplicates("time").set_index("time")
    return out.asfreq("10min")  # keeps gaps visible as NaN


def make_synthetic(n=40000, rated=2050.0, seed=0):
    """AR(1) wind with a diurnal cycle, passed through a cubic power curve + noise."""
    rng = np.random.default_rng(seed)
    v = np.empty(n)
    v[0] = 8.5
    for t in range(1, n):
        v[t] = 8.5 + 0.985 * (v[t - 1] - 8.5) + rng.normal(0, 0.55)
    v = np.clip(v + 1.2 * np.sin(2 * np.pi * np.arange(n) / 144), 0, 30)
    p = rated * np.clip((v**3 - 3**3) / (12.5**3 - 3**3), 0, 1)
    p[(v < 3) | (v >= 25)] = 0
    p = np.clip(p + rng.normal(0, 0.03 * rated, n), 0, rated)
    d = (220 + np.cumsum(rng.normal(0, 3, n))) % 360
    idx = pd.date_range("2020-01-01", periods=n, freq="10min")
    return pd.DataFrame({"wind": v, "power": p, "dir": d}, index=idx)


# ------------------------------------------------------- empirical power curve


def fit_power_curve(v, p, bin_width=0.5, q_lo=0.025, q_hi=0.975, min_count=20):
    """Bin-wise median curve and a quantile band (all in p.u.)."""
    edges = np.arange(0, 30 + bin_width, bin_width)
    centres, med, lo, hi = [], [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (v >= a) & (v < b)
        if m.sum() >= min_count:
            centres.append((a + b) / 2)
            med.append(np.median(p[m]))
            lo.append(np.quantile(p[m], q_lo))
            hi.append(np.quantile(p[m], q_hi))
    return np.array(centres), np.array(med), np.array(lo), np.array(hi)


def clean(df, rated, v_ci):
    """Remove stoppages and curtailment: points far below the bin median at working wind."""
    df = df.dropna().copy()
    df["p"] = df["power"].clip(lower=0) / rated
    c, med, _, _ = fit_power_curve(df["wind"].values, df["p"].values)
    expected = np.interp(df["wind"], c, med)
    stopped = (df["wind"] > v_ci + 1.5) & (df["p"] < 0.02)
    curtailed = (df["p"] < expected - 0.25) & (df["wind"] > v_ci + 1.5)
    return df[~(stopped | curtailed)]


# ------------------------------------------------------------------ sequences


def build_windows(df, lookback, horizon):
    """Past window of [wind, sin dir, cos dir, power]; targets wind and power at t+h."""
    feats = np.stack([
        df["wind"].values / 25.0,
        np.sin(np.deg2rad(df["dir"].values)),
        np.cos(np.deg2rad(df["dir"].values)),
        df["p"].values,
    ], axis=1).astype(np.float32)
    t = df.index.values
    step = np.timedelta64(10, "m")
    X, v_y, p_y = [], [], []
    for i in range(lookback, len(df) - horizon + 1):
        j = i + horizon - 1
        # keep only windows with no time gap (cleaning removes rows)
        if t[j] - t[i - lookback] != (lookback + horizon - 1) * step:
            continue
        X.append(feats[i - lookback:i])
        v_y.append(df["wind"].values[j])
        p_y.append(df["p"].values[j])
    return np.array(X), np.array(v_y, np.float32), np.array(p_y, np.float32)


# ---------------------------------------------------------------------- model


class CNNGRU(nn.Module):
    def __init__(self, n_feat, bounded):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(n_feat, 64, 3, padding=1), nn.ReLU(),
                                  nn.Conv1d(64, 64, 3, padding=1), nn.ReLU())
        self.gru = nn.GRU(64, 64, num_layers=2, batch_first=True, dropout=0.1)
        self.wind_head = nn.Linear(64, 1)
        self.power_head = nn.Linear(64, 1)
        self.bounded = bounded

    def forward(self, x):
        h = self.conv(x.transpose(1, 2)).transpose(1, 2)
        _, h = self.gru(h)
        h = h[-1]
        v_hat = 25.0 * self.wind_head(h).squeeze(-1)  # m/s
        p_hat = self.power_head(h).squeeze(-1)  # p.u., unbounded while training
        if self.bounded and not self.training:
            p_hat = p_hat.clamp(0.0, 1.0)  # physics-aware output layer: feasible by construction
        return v_hat, p_hat


def torch_interp(x, xp, fp):
    """Differentiable 1-D linear interpolation (clamped at the ends)."""
    x = x.clamp(xp[0], xp[-1])
    i = torch.bucketize(x, xp).clamp(1, len(xp) - 1)
    x0, x1, y0, y1 = xp[i - 1], xp[i], fp[i - 1], fp[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def physics_loss(v_true, v_hat, p_hat, curve, v_ci, v_co):
    c, med, lo, hi = curve
    # capacity: 0 <= p <= rated (soft during training, as in the constraint-aware CNN-GRU)
    cap = torch.relu(p_hat - 1.0) ** 2 + torch.relu(-p_hat) ** 2
    # band around the curve at the MEASURED future wind (Option A, training only)
    band = torch.relu(p_hat - torch_interp(v_true, c, hi)) ** 2 + \
           torch.relu(torch_interp(v_true, c, lo) - p_hat) ** 2
    # zero power below cut-in / above cut-out
    cut = ((v_true < v_ci) | (v_true >= v_co)).float() * p_hat ** 2
    # forecast power must match the power curve of FORECAST wind (Option B)
    consist = (p_hat - torch_interp(v_hat, c, med)) ** 2
    return cap.mean(), band.mean(), cut.mean(), consist.mean()


def train(model, data, curve, args, physics):
    X, v, p = data
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    n = len(X)
    for epoch in range(args.epochs):
        model.train()
        perm = torch.randperm(n)
        total = 0.0
        for k in range(0, n, args.batch):
            b = perm[k:k + args.batch]
            v_hat, p_hat = model(X[b])
            loss = nn.functional.mse_loss(p_hat, p[b]) + \
                0.01 * nn.functional.mse_loss(v_hat, v[b])  # wind in m/s, so scale down
            if physics:
                cap, band, cut, consist = physics_loss(v[b], v_hat, p_hat, curve, args.v_ci, args.v_co)
                loss = loss + args.lam_cap * cap + args.lam_band * band + args.lam_cut * cut + args.lam_consist * consist
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        print(f"  {'physics ' if physics else 'baseline'} epoch {epoch + 1:2d}  loss {total / n:.5f}")
    return model


# ----------------------------------------------------------------- evaluation


def evaluate(name, v_hat, p_hat, v_true, p_true, curve_np, tol):
    c, _, lo, hi = curve_np
    above = p_hat > 1.0 + tol
    below = p_hat < -tol
    impossible = above | below  # can never happen physically
    off_curve = ~impossible & ((p_hat > np.interp(v_hat, c, hi) + tol) |
                               (p_hat < np.interp(v_hat, c, lo) - tol))  # inconsistent with own wind forecast
    row = {
        "model": name,
        "RMSE (% rated)": 100 * np.sqrt(np.mean((p_hat - p_true) ** 2)),
        "MAE (% rated)": 100 * np.mean(np.abs(p_hat - p_true)),
        "wind RMSE (m/s)": np.sqrt(np.mean((v_hat - v_true) ** 2)),
        "above rated (%)": 100 * above.mean(),
        "below zero (%)": 100 * below.mean(),
        "impossible (%)": 100 * impossible.mean(),
        "off the curve (%)": 100 * off_curve.mean(),
    }
    return row, impossible, off_curve


def plot(curve_np, v_meas, p_meas, results, title_note, out):
    c, med, lo, hi = curve_np
    ink, muted, band_fill = "#1a1a19", "#8a8983", "#cde2fb"
    ok_col, off_col, bad_col = "#2a78d6", "#eb6834", "#d03b3b"
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharex=True, sharey=True)
    for ax, (name, v_hat, p_hat, bad, off, row) in zip(axes, results):
        ax.scatter(v_meas, p_meas, s=2, color=muted, alpha=0.15, linewidths=0, label="measured (test)")
        ax.fill_between(c, lo, hi, color=band_fill, alpha=0.8, linewidth=0, label="power-curve band")
        ax.plot(c, med, color=ink, lw=1.5, label="fitted power curve")
        ax.axhline(1.0, color=ink, lw=1, ls="--")
        ax.text(0.3, 1.02, "rated power", color=ink, fontsize=8)
        good = ~bad & ~off
        ax.scatter(v_hat[good], p_hat[good], s=6, color=ok_col, alpha=0.5, linewidths=0,
                   label="forecast inside band")
        ax.scatter(v_hat[off], p_hat[off], s=12, facecolors="none", edgecolors=off_col, linewidths=0.7,
                   label="forecast off the curve")
        ax.scatter(v_hat[bad], p_hat[bad], s=16, color=bad_col, marker="x", linewidths=0.9,
                   label="impossible (< 0 or > rated)")
        ax.set_title(f"{name}\nimpossible {row['impossible (%)']:.1f}%, off curve {row['off the curve (%)']:.1f}%, "
                     f"RMSE {row['RMSE (% rated)']:.1f}% of rated", fontsize=9.5, color=ink, loc="left")
        ax.set_xlabel("Wind speed (m/s): measured for grey points, forecast for coloured", color=ink, fontsize=9)
        ax.grid(color="#e6e5e0", lw=0.6)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlim(0, max(20, float(np.nanpercentile(v_meas, 99.9)) + 1))
        ax.set_ylim(-0.15, 1.2)
    axes[0].set_ylabel("Power (per unit of rated)", color=ink)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=6, frameon=False, fontsize=8, markerscale=2)
    fig.suptitle("Forecast (wind, power) pairs on the measured power curve" + title_note,
                 x=0.01, ha="left", fontsize=12, color=ink)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    fig.savefig(out, dpi=300)
    print(f"saved {out}")


# ----------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", help="glob for SCADA CSV files of ONE turbine")
    ap.add_argument("--synthetic", action="store_true", help="use generated data (code test only)")
    ap.add_argument("--rated", type=float, default=2050.0, help="rated power in kW (Senvion MM92: 2050)")
    ap.add_argument("--v_ci", type=float, default=3.0, help="cut-in wind speed, m/s")
    ap.add_argument("--v_co", type=float, default=25.0, help="cut-out wind speed, m/s")
    ap.add_argument("--wind_col", default="Wind speed (m/s)")
    ap.add_argument("--power_col", default="Power (kW)")
    ap.add_argument("--dir_col", default="Wind direction")
    ap.add_argument("--lookback", type=int, default=36, help="past steps (36 = 6 h)")
    ap.add_argument("--horizon", type=int, default=6, help="steps ahead (6 = 1 h)")
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lam_cap", type=float, default=10.0)
    ap.add_argument("--lam_band", type=float, default=5.0)
    ap.add_argument("--lam_cut", type=float, default=5.0)
    ap.add_argument("--lam_consist", type=float, default=1.0)
    ap.add_argument("--tol", type=float, default=0.02, help="tolerance before counting a violation (p.u.)")
    ap.add_argument("--out", default="pilot_power_curve.png")
    args = ap.parse_args()

    torch.manual_seed(0)
    np.random.seed(0)

    if args.synthetic:
        raw, note = make_synthetic(rated=args.rated), " (SYNTHETIC DATA, code test only)"
    elif args.data:
        raw, note = read_kelmarsh(args.data, args.wind_col, args.power_col, args.dir_col), ""
    else:
        ap.error("give --data or --synthetic")

    df = clean(raw, args.rated, args.v_ci)
    print(f"{len(raw)} rows, {len(df)} after cleaning")

    # chronological split 70 / 15 / 15; the power curve is fitted on training data only
    n = len(df)
    tr, va = df.iloc[: int(0.7 * n)], df.iloc[int(0.7 * n): int(0.85 * n)]
    te = df.iloc[int(0.85 * n):]
    curve_np = fit_power_curve(tr["wind"].values, tr["p"].values)
    curve_t = tuple(torch.tensor(a, dtype=torch.float32) for a in curve_np)

    to_t = lambda arrs: tuple(torch.tensor(a) for a in arrs)
    train_set = to_t(build_windows(tr, args.lookback, args.horizon))
    X_te, v_te, p_te = build_windows(te, args.lookback, args.horizon)
    print(f"{len(train_set[0])} training windows, {len(X_te)} test windows")
    # (validation split `va` is kept for tuning the lambdas in the full study)

    results, rows = [], []
    for name, physics in [("Plain CNN-GRU", False), ("CNN-GRU + physics loss", True)]:
        torch.manual_seed(0)
        model = train(CNNGRU(X_te.shape[2], bounded=physics), train_set, curve_t, args, physics)
        model.eval()
        with torch.no_grad():
            v_hat, p_hat = (a.numpy() for a in model(torch.tensor(X_te)))
        row, bad, off = evaluate(name, v_hat, p_hat, v_te, p_te, curve_np, args.tol)
        rows.append(row)
        results.append((name, v_hat, p_hat, bad, off, row))

    table = pd.DataFrame(rows).round(2)
    print(table.to_string(index=False))
    table.to_csv("pilot_metrics.csv", index=False)
    plot(curve_np, te["wind"].values, te["p"].values, results, note, args.out)


if __name__ == "__main__":
    main()
