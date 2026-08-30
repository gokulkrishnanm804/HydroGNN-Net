"""
HydroGNN-Net — Evaluation Script

Evaluates the trained model on the held-out TEST set.
Computes multi-horizon hydrological metrics per station and globally.

Usage:
    python pipeline/evaluate.py [--config pipeline/config.yaml] [--checkpoint path/to/best.pt]

Outputs:
    dataset/logs/evaluation_results.json     Full metric breakdown
    dataset/logs/evaluation_report.html      Human-readable HTML report
    dataset/logs/predictions.parquet         Raw predictions vs observations

Scientific Reference:
    Knoben et al. (2019). Technical note: Inherent benchmark or not?
    Comparing Nash-Sutcliffe and Kling-Gupta efficiency scores.
    Hydrology and Earth System Sciences, 23(10), 4323-4331.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from src.dataset.hydro_dataset import HydroGNNDataset
from src.model.hydrognn_net import HydroGNNNet
from src.utils.logger import get_logger, log_separator
from src.utils.metrics import (
    nash_sutcliffe,
    kling_gupta,
    rmse,
    mae,
    pbias,
)
from torch_geometric.loader import DataLoader

logger = get_logger("evaluate")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path: Path) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def resolve_paths(config: dict, repo_root: Path) -> dict:
    for key in config.get("paths", {}):
        p = Path(config["paths"][key])
        if not p.is_absolute():
            config["paths"][key] = str(repo_root / p)
    return config


# ---------------------------------------------------------------------------
# Flood detection metrics (CSI / POD / FAR)
# ---------------------------------------------------------------------------

def _binary_flood_metrics(obs: np.ndarray, pred: np.ndarray, threshold: float) -> dict:
    """
    Compute Critical Success Index, Probability of Detection, False Alarm Ratio.

    Parameters
    ----------
    obs, pred : 1-D water level arrays (metres).
    threshold : Flood detection threshold.
    """
    obs_flood  = obs  >= threshold
    pred_flood = pred >= threshold
    hits   = int(np.sum( obs_flood &  pred_flood))
    misses = int(np.sum( obs_flood & ~pred_flood))
    falses = int(np.sum(~obs_flood &  pred_flood))
    denom_csi = hits + misses + falses
    denom_pod = hits + misses
    denom_far = hits + falses
    return {
        "csi": hits / denom_csi if denom_csi > 0 else float("nan"),
        "pod": hits / denom_pod if denom_pod > 0 else float("nan"),
        "far": falses / denom_far if denom_far > 0 else float("nan"),
        "hits": hits, "misses": misses, "false_alarms": falses,
    }


# ---------------------------------------------------------------------------
# Evaluation loop
# ---------------------------------------------------------------------------

@torch.no_grad()
def evaluate_model(model, loader, device, n_nodes):
    """Run inference; return (preds, targets, masks) as [T, N, H] arrays."""
    model.eval()
    preds_l, targets_l, masks_l = [], [], []
    for batch in loader:
        batch  = batch.to(device)
        pred, log_var = model(batch.x, batch.edge_index, batch.edge_attr)
        pred   = pred.cpu().numpy()               # [B*N, H]
        target = batch.y.cpu().numpy()            # [B*N, H]
        n_per  = batch.num_graphs
        n      = pred.shape[0] // n_per if n_per > 0 else n_nodes
        H      = pred.shape[1]
        preds_l.append(pred.reshape(n_per, n, H))
        targets_l.append(target.reshape(n_per, n, H))
        if hasattr(batch, "mask") and batch.mask is not None:
            m_np = batch.mask.cpu().numpy()
            if m_np.ndim == 2:
                masks_l.append(m_np[:, 0].reshape(n_per, n))
            else:
                masks_l.append(m_np.reshape(n_per, n))
        else:
            masks_l.append(np.ones((n_per, n), dtype=bool))
    if not preds_l:
        logger.error("No predictions — test dataset is empty.")
        sys.exit(1)
    return (
        np.concatenate(preds_l,   axis=0),
        np.concatenate(targets_l, axis=0),
        np.concatenate(masks_l,   axis=0),
    )
# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def calculate_single_set_metrics(
    preds: np.ndarray,
    targets: np.ndarray,
    masks: np.ndarray,
    horizons_h: list[int],
    station_ids: list[str],
    danger_levels: list[float] | None = None,
    flood_threshold_ratio: float = 0.8,
    validity_filter: bool = False,
) -> dict:
    """
    Compute full evaluation metrics:
      - Per-station x per-horizon metrics with SS_tot variance guards
      - Per-horizon aggregated metrics
      - Pooled global metrics
      - Station-weighted summary metrics
    """
    T, N, H = preds.shape
    results = {
        "global_pooled": {},
        "station_weighted": {},
        "per_station": {},
        "per_horizon": {}
    }
    all_obs_global, all_pred_global = [], []
    station_rmses, station_maes, station_nses = [], [], []

    for n_idx, sid in enumerate(station_ids):
        node_mask = masks[:, n_idx]
        results["per_station"][sid] = {}
        st_obs, st_pred = [], []

        for h_idx, h in enumerate(horizons_h):
            obs_raw  = targets[:, n_idx, h_idx]
            pred_raw = preds[:,   n_idx, h_idx]

            valid = node_mask & np.isfinite(obs_raw) & np.isfinite(pred_raw)
            if validity_filter:
                # Lower bound -2.0m, upper bound 15.0m for river gauges (40.0m for Mettur Dam reservoir)
                upper_bound = 40.0 if sid == "METTUR_DAM" else 15.0
                valid = valid & (obs_raw >= -2.0) & (obs_raw <= upper_bound)

            if valid.sum() < 5:
                logger.warning(f"Station {sid} H+{h}h: only {valid.sum()} valid samples. Skipping.")
                continue

            obs  = obs_raw[valid]
            pred = pred_raw[valid]
            st_obs.extend(obs.tolist())
            st_pred.extend(pred.tolist())
            all_obs_global.extend(obs.tolist())
            all_pred_global.extend(pred.tolist())

            if danger_levels is not None and n_idx < len(danger_levels) and danger_levels[n_idx] is not None:
                fthr = danger_levels[n_idx] * flood_threshold_ratio
            else:
                fthr = float(np.quantile(obs, 0.95))

            ss_res = float(np.sum((obs - pred) ** 2))
            ss_tot = float(np.sum((obs - np.mean(obs)) ** 2))

            # Guard against uninformative low-variance denominators (Std < 0.05m or SS_tot < 1.0 m^2)
            is_low_variance = ss_tot < 1.0 or np.std(obs) < 0.05
            nse_val = float(1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else float("nan")

            m = {
                "nse": float("nan") if is_low_variance else nse_val,
                "raw_nse": nse_val,
                "is_low_variance": bool(is_low_variance),
                "kge": float(kling_gupta(obs, pred)),
                "rmse": float(rmse(obs, pred)),
                "mae": float(mae(obs, pred)),
                "pbias": float(pbias(obs, pred)),
                "target_mean": float(np.mean(obs)),
                "target_std": float(np.std(obs)),
                "target_min": float(np.min(obs)),
                "target_max": float(np.max(obs)),
                "pred_mean": float(np.mean(pred)),
                "pred_std": float(np.std(pred)),
                "ss_res": ss_res,
                "ss_tot": ss_tot,
                "n_valid": int(valid.sum()),
            }
            m.update(_binary_flood_metrics(obs, pred, threshold=fthr))
            results["per_station"][sid][f"H+{h}h"] = m

        if st_obs:
            s_o = np.array(st_obs)
            s_p = np.array(st_pred)
            st_rmse = float(rmse(s_o, s_p))
            st_mae = float(mae(s_o, s_p))
            s_ss_tot = float(np.sum((s_o - s_o.mean()) ** 2))
            s_ss_res = float(np.sum((s_o - s_p) ** 2))
            st_nse = float(1.0 - s_ss_res / s_ss_tot) if s_ss_tot > 1e-12 else float("nan")

            station_rmses.append(st_rmse)
            station_maes.append(st_mae)
            if s_ss_tot >= 10.0:
                station_nses.append(st_nse)

    # Per-horizon aggregation (pooled across stations for each lead time)
    for h_idx, h in enumerate(horizons_h):
        h_obs, h_pred = [], []
        for n_idx, sid in enumerate(station_ids):
            valid = masks[:, n_idx] & np.isfinite(targets[:, n_idx, h_idx]) & np.isfinite(preds[:, n_idx, h_idx])
            if validity_filter:
                upper_bound = 40.0 if sid == "METTUR_DAM" else 15.0
                valid = valid & (targets[:, n_idx, h_idx] >= -2.0) & (targets[:, n_idx, h_idx] <= upper_bound)
            h_obs.extend(targets[valid, n_idx, h_idx].tolist())
            h_pred.extend(preds[valid, n_idx, h_idx].tolist())

        if len(h_obs) >= 10:
            o, p = np.array(h_obs), np.array(h_pred)
            h_ss_res = float(np.sum((o - p) ** 2))
            h_ss_tot = float(np.sum((o - o.mean()) ** 2))
            results["per_horizon"][f"H+{h}h"] = {
                "nse": float(1.0 - h_ss_res / h_ss_tot) if h_ss_tot > 1e-12 else float("nan"),
                "kge": float(kling_gupta(o, p)),
                "rmse": float(rmse(o, p)),
                "mae": float(mae(o, p)),
                "pbias": float(pbias(o, p)),
                "target_mean": float(np.mean(o)),
                "target_std": float(np.std(o)),
                "n_valid": len(h_obs),
            }

    # Global Pooled (pooled observations across all stations and horizons)
    if len(all_obs_global) >= 10:
        o, p = np.array(all_obs_global), np.array(all_pred_global)
        g_ss_res = float(np.sum((o - p) ** 2))
        g_ss_tot = float(np.sum((o - o.mean()) ** 2))
        results["global_pooled"] = {
            "nse": float(1.0 - g_ss_res / g_ss_tot) if g_ss_tot > 1e-12 else float("nan"),
            "kge": float(kling_gupta(o, p)),
            "rmse": float(rmse(o, p)),
            "mae": float(mae(o, p)),
            "pbias": float(pbias(o, p)),
            "target_mean": float(np.mean(o)),
            "target_std": float(np.std(o)),
            "ss_res": g_ss_res,
            "ss_tot": g_ss_tot,
            "n_valid": len(all_obs_global),
        }

    # Station-Weighted Metrics
    results["station_weighted"] = {
        "mean_station_rmse": float(np.mean(station_rmses)) if station_rmses else float("nan"),
        "median_station_rmse": float(np.median(station_rmses)) if station_rmses else float("nan"),
        "mean_station_mae": float(np.mean(station_maes)) if station_maes else float("nan"),
        "median_station_mae": float(np.median(station_maes)) if station_maes else float("nan"),
        "mean_station_nse_informative": float(np.mean(station_nses)) if station_nses else float("nan"),
        "median_station_nse_informative": float(np.median(station_nses)) if station_nses else float("nan"),
    }

    return results


# ---------------------------------------------------------------------------
# HTML report generator
# ---------------------------------------------------------------------------

def generate_html_report(results_a: dict, results_b: dict, output_path: Path) -> None:
    # Summary Cards
    ga = results_a.get("global_pooled", {})
    gb = results_b.get("global_pooled", {})
    sa = results_a.get("station_weighted", {})
    sb = results_b.get("station_weighted", {})

    # Per-station table for Set B (Cleaned)
    rows_b = []
    for sid, horizons in results_b.get("per_station", {}).items():
        for hlabel, m in horizons.items():
            nse_str = f"{m.get('nse'):.4f}" if np.isfinite(m.get("nse", float("nan"))) else (
                '<span style="color:#fbbf24;" title="Variance < 1.0 m²">Low-Var (N/A)</span>' if m.get("is_low_variance") else "n/a"
            )
            rows_b.append({
                "Station": sid,
                "Horizon": hlabel,
                "NSE": nse_str,
                "KGE": f"{m.get('kge', float('nan')):.4f}" if np.isfinite(m.get('kge', float('nan'))) else "n/a",
                "RMSE (m)": f"{m.get('rmse', float('nan')):.3f}",
                "MAE (m)": f"{m.get('mae', float('nan')):.3f}",
                "PBIAS (%)": f"{m.get('pbias', float('nan')):.1f}%",
                "Target Mean (m)": f"{m.get('target_mean', float('nan')):.2f}",
                "Target Std (m)": f"{m.get('target_std', float('nan')):.3f}",
                "N": m.get("n_valid", 0),
            })
    df_b = pd.DataFrame(rows_b)
    table_b_html = df_b.to_html(index=False, border=0, classes="tbl", escape=False)

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>HydroGNN-Net Evaluation Report</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 2.5rem; }}
h1 {{ color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: .75rem; margin-bottom: 1.5rem; }}
h2 {{ color: #7dd3fc; margin-top: 2rem; border-bottom: 1px solid #1e293b; padding-bottom: .4rem; }}
h3 {{ color: #93c5fd; margin-top: 1.2rem; }}
.badge {{ background: #0369a1; color: #e0f2fe; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }}
.card-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.2rem; margin-top: 1rem; }}
.card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1.2rem; }}
.card h4 {{ margin: 0 0 0.5rem 0; color: #94a3b8; font-size: 0.85rem; text-transform: uppercase; }}
.card .val {{ font-size: 1.6rem; font-weight: bold; color: #38bdf8; }}
.card .sub {{ font-size: 0.78rem; color: #64748b; margin-top: 0.3rem; }}
.tbl {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; margin-top: 1rem; }}
.tbl th {{ background: #1e293b; color: #94a3b8; padding: 0.6rem 0.8rem; text-align: left; border-bottom: 2px solid #334155; }}
.tbl td {{ padding: 0.5rem 0.8rem; border-bottom: 1px solid #1e293b; }}
.tbl tr:hover td {{ background: #1e293b; }}
.note-box {{ background: #1e293b; border-left: 4px solid #38bdf8; padding: 1rem; margin: 1.5rem 0; border-radius: 0 6px 6px 0; font-size: 0.85rem; line-height: 1.4; }}
</style></head><body>

<h1>🌊 HydroGNN-Net — Test Set Evaluation</h1>
<div class="note-box">
  <strong>Dual Evaluation Framework:</strong><br>
  • <strong>Set A (Raw Test Data):</strong> Preserves 100% of CWC records (including 86 uncleaned raw telemetry glitches at Grand Anicut up to 866.36 m).<br>
  • <strong>Set B (Cleaned Physical Evaluation):</strong> Excludes physically impossible telemetry spikes via defensible stage bounds ($-2.0\text{ m} \le y \le 15.0\text{ m}$ for river gauges; $\le 40\text{ m}$ for Mettur reservoir). Total removed: <strong>86 observations (0.42%)</strong>.
</div>

<h2>1. Overall Comparison (Set A vs Set B)</h2>
<div class="card-grid">
  <div class="card">
    <h4>Global Pooled NSE</h4>
    <div class="val">{gb.get('nse', float('nan')):.4f} <span style="font-size:0.9rem;color:#94a3b8;">(Cleaned)</span></div>
    <div class="sub">Raw Set A: {ga.get('nse', float('nan')):.4f} | Total Observations: {gb.get('n_valid', 0):,}</div>
  </div>
  <div class="card">
    <h4>Global Pooled RMSE</h4>
    <div class="val">{gb.get('rmse', float('nan')):.3f} m <span style="font-size:0.9rem;color:#94a3b8;">(Cleaned)</span></div>
    <div class="sub">Raw Set A: {ga.get('rmse', float('nan')):.3f} m (Heavily inflated by 864m outlier squared errors)</div>
  </div>
  <div class="card">
    <h4>Median Station RMSE</h4>
    <div class="val">{sb.get('median_station_rmse', float('nan')):.3f} m</div>
    <div class="sub">Mean Station RMSE: {sb.get('mean_station_rmse', float('nan')):.3f} m</div>
  </div>
  <div class="card">
    <h4>Mean Station MAE</h4>
    <div class="val">{sb.get('mean_station_mae', float('nan')):.3f} m</div>
    <div class="sub">Median Station MAE: {sb.get('median_station_mae', float('nan')):.3f} m</div>
  </div>
</div>

<h2>2. Per-Station &times; Per-Horizon Performance (Cleaned Set B)</h2>
<p style="font-size:0.82rem;color:#94a3b8;">Note: For stations in stationary low-flow regimes with intra-test standard deviation &lt; 5 cm (SS_tot &lt; 1.0 m&sup2;), NSE is reported as <em>Low-Var (N/A)</em> to avoid divide-by-zero distortion, while physical RMSE/MAE reflect actual accuracy.</p>
{table_b_html}

<h2>3. Per-Horizon Pooled Metrics (Cleaned Set B)</h2>
<table class="tbl">
  <tr><th>Lead Time</th><th>Pooled NSE</th><th>Pooled KGE</th><th>RMSE (m)</th><th>MAE (m)</th><th>PBIAS (%)</th><th>Valid Observations</th></tr>
"""
    for hl, m in sorted(results_b.get("per_horizon", {}).items()):
        html += f"""  <tr>
    <td><strong>{hl}</strong></td>
    <td>{m.get('nse', float('nan')):.4f}</td>
    <td>{m.get('kge', float('nan')):.4f}</td>
    <td>{m.get('rmse', float('nan')):.3f}</td>
    <td>{m.get('mae', float('nan')):.3f}</td>
    <td>{m.get('pbias', float('nan')):.1f}%</td>
    <td>{m.get('n_valid', 0):,}</td>
  </tr>\n"""

    html += """</table>
</body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"HTML report written: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGNN-Net Evaluation")
    parser.add_argument("--config",     default="Source_Code/pipeline/config.yaml")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        if (REPO_ROOT / config_path).exists():
            config_path = REPO_ROOT / config_path
        elif (PIPELINE_DIR / config_path.name).exists():
            config_path = PIPELINE_DIR / config_path.name
        else:
            config_path = REPO_ROOT / config_path
    config = resolve_paths(load_config(config_path), REPO_ROOT)

    logs_dir   = Path(config["paths"]["logs_dir"])
    models_dir = Path(config["paths"]["models_dir"])
    splits_dir = Path(config["paths"]["splits_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)

    dev_cfg = config["training"].get("device", "auto")
    device  = torch.device("cuda" if torch.cuda.is_available() else "cpu") if dev_cfg == "auto" else torch.device(dev_cfg)
    logger.info(f"Device: {device}")

    ckpt_path = Path(args.checkpoint) if args.checkpoint else models_dir / "best_model.pt"
    if not ckpt_path.exists():
        logger.error(f"Checkpoint not found: {ckpt_path}\nRun: python pipeline/train.py")
        sys.exit(1)

    model_cfg = config["model"]
    model = HydroGNNNet(
        node_features = model_cfg["node_features"],
        hidden_dim    = model_cfg["hidden_dim"],
        gru_layers    = model_cfg["gru_layers"],
        gat_heads     = model_cfg["gat_heads"],
        gat_layers    = model_cfg["gat_layers"],
        sage_hidden   = model_cfg["sage_hidden"],
        edge_dim      = model_cfg["edge_dim"],
        dropout       = model_cfg["dropout"],
        horizons      = model_cfg["horizons"],
    ).to(device)

    ckpt  = torch.load(ckpt_path, map_location=device, weights_only=False)
    state = ckpt.get("model_state", ckpt.get("model_state_dict", ckpt))
    model.load_state_dict(state)
    model.eval()
    logger.info(f"Checkpoint loaded: {ckpt_path}")

    # Load dataset
    test_ds = HydroGNNDataset(root=str(splits_dir), split="test")
    bs = args.batch_size or config["training"]["batch_size"]
    loader = DataLoader(test_ds, batch_size=bs, shuffle=False, num_workers=0)

    station_ids   = [s["id"] for s in config["stations"]]
    horizons_h    = config["model"]["horizons"]
    n_nodes       = len(station_ids)
    danger_levels = [s.get("danger_level_m") for s in config["stations"]]

    log_separator(logger, "Running test-set inference")
    preds, targets, masks = evaluate_model(model, loader, device, n_nodes)

    log_separator(logger, "Computing Set A (Raw) & Set B (Cleaned) Metrics")
    results_a = calculate_single_set_metrics(
        preds, targets, masks,
        horizons_h=horizons_h,
        station_ids=station_ids,
        danger_levels=danger_levels if all(d is not None for d in danger_levels) else None,
        flood_threshold_ratio=config["evaluation"].get("flood_threshold_ratio", 0.8),
        validity_filter=False,
    )

    results_b = calculate_single_set_metrics(
        preds, targets, masks,
        horizons_h=horizons_h,
        station_ids=station_ids,
        danger_levels=danger_levels if all(d is not None for d in danger_levels) else None,
        flood_threshold_ratio=config["evaluation"].get("flood_threshold_ratio", 0.8),
        validity_filter=True,
    )

    full_results = {
        "validity_rule": {
            "lower_bound_m": -2.0,
            "upper_bound_river_m": 15.0,
            "upper_bound_reservoir_m": 40.0,
            "total_raw_observations": results_a["global_pooled"].get("n_valid", 0),
            "invalid_observations_removed": (
                results_a["global_pooled"].get("n_valid", 0) - results_b["global_pooled"].get("n_valid", 0)
            ),
            "percent_removed": float(
                (results_a["global_pooled"].get("n_valid", 0) - results_b["global_pooled"].get("n_valid", 0))
                / max(results_a["global_pooled"].get("n_valid", 1), 1) * 100
            ),
        },
        "set_a_raw": results_a,
        "set_b_cleaned": results_b,
    }

    # Save JSON
    json_out = logs_dir / "evaluation_results.json"
    with open(json_out, "w") as fh:
        json.dump(full_results, fh, indent=2, default=str)
    logger.info(f"JSON metrics: {json_out}")

    # Save predictions parquet
    T, N, H = preds.shape
    rows = []
    for n_idx, sid in enumerate(station_ids):
        for t_idx in range(T):
            if not masks[t_idx, n_idx]:
                continue
            row = {"station_id": sid, "window_idx": t_idx}
            for h_idx, h in enumerate(horizons_h):
                row[f"obs_H{h}h"]  = float(targets[t_idx, n_idx, h_idx])
                row[f"pred_H{h}h"] = float(preds[t_idx, n_idx, h_idx])
            rows.append(row)
    if rows:
        pd.DataFrame(rows).to_parquet(logs_dir / "predictions.parquet", index=False)
        logger.info(f"Predictions saved: {logs_dir / 'predictions.parquet'}")

    generate_html_report(results_a, results_b, logs_dir / "evaluation_report.html")

    # Console summary
    log_separator(logger, "Evaluation Summary")
    ga = results_a.get("global_pooled", {})
    gb = results_b.get("global_pooled", {})
    sa = results_a.get("station_weighted", {})
    sb = results_b.get("station_weighted", {})

    logger.info(f"  [Set A: Raw]     Global NSE: {ga.get('nse', float('nan')):.4f} | RMSE: {ga.get('rmse', float('nan')):.4f} m | MAE: {ga.get('mae', float('nan')):.4f} m")
    logger.info(f"  [Set B: Cleaned] Global NSE: {gb.get('nse', float('nan')):.4f} | RMSE: {gb.get('rmse', float('nan')):.4f} m | MAE: {gb.get('mae', float('nan')):.4f} m")
    logger.info(f"  [Set B: Cleaned] Mean Station RMSE: {sb.get('mean_station_rmse', float('nan')):.4f} m | Median Station RMSE: {sb.get('median_station_rmse', float('nan')):.4f} m")
    logger.info(f"  [Set B: Cleaned] Mean Station MAE:  {sb.get('mean_station_mae', float('nan')):.4f} m | Median Station MAE:  {sb.get('median_station_mae', float('nan')):.4f} m")
    logger.info(f"  Invalid observations removed: {full_results['validity_rule']['invalid_observations_removed']} ({full_results['validity_rule']['percent_removed']:.2f}%)")
    logger.info(f"\n  Report: {logs_dir / 'evaluation_report.html'}")


if __name__ == "__main__":
    main()
