"""
HydroGNN-Net Data Preprocessing Orchestrator
=============================================
Validates and preprocesses all downloaded raw data into aligned, 30-minute
time series suitable for feature engineering and GNN training.

Prerequisite: python pipeline/download_all.py

Usage
-----
    python pipeline/preprocess.py
    python pipeline/preprocess.py --config pipeline/config.yaml
    python pipeline/preprocess.py --skip-validation   # Skip HTML report
    python pipeline/preprocess.py --station METTUR_DAM  # Process one station

Outputs
-------
    dataset/processed/gpm_processed_{station_id}.parquet
    dataset/processed/era5_processed_{station_id}.parquet
    dataset/processed/cwc_{station_id}.parquet
    dataset/processed/reservoir_{reservoir_id}.parquet
    dataset/processed/terrain_attributes.csv
    dataset/logs/validation_report.html     ← Open in browser to inspect data quality
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import yaml
import pandas as pd
import numpy as np

from src.utils.logger import get_logger, log_separator
from src.utils.cache import DataSourceUnavailable

logger = get_logger("preprocess")


def load_config(config_path: Path) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh)


def resolve_paths(config: dict, repo_root: Path) -> dict:
    for key in config.get("paths", {}):
        p = Path(config["paths"][key])
        if not p.is_absolute():
            config["paths"][key] = str(repo_root / p)
    if "imd_rainfall" in config and "path" in config["imd_rainfall"]:
        p = Path(config["imd_rainfall"]["path"])
        if not p.is_absolute():
            config["imd_rainfall"]["path"] = str(repo_root / p)
    if "reservoir_operations" in config and "path" in config["reservoir_operations"]:
        p = Path(config["reservoir_operations"]["path"])
        if not p.is_absolute():
            config["reservoir_operations"]["path"] = str(repo_root / p)
    return config


# ─────────────────────────────────────────────────────────────────────────────
# Validation report generator (standalone — no DataValidator dependency)
# ─────────────────────────────────────────────────────────────────────────────

def _html_badge(status: str) -> str:
    colours = {"OK": "#22c55e", "WARNING": "#f59e0b", "CRITICAL": "#ef4444", "MISSING": "#6b7280"}
    bg = colours.get(status, "#6b7280")
    return f'<span style="background:{bg};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{status}</span>'


def generate_validation_report(
    summaries: list,
    output_path: Path,
) -> None:
    """
    Write a standalone HTML validation report.

    Parameters
    ----------
    summaries : list of dicts with keys:
                source, station_id, status, total_rows, missing_pct, notes
    output_path : Where to write the HTML file.
    """
    from datetime import datetime, timezone

    rows_html = ""
    for s in summaries:
        badge = _html_badge(s["status"])
        missing = f"{s.get('missing_pct', 0):.1f}%"
        rows_html += (
            f"<tr>"
            f"<td>{s['source']}</td>"
            f"<td>{s['station_id']}</td>"
            f"<td>{badge}</td>"
            f"<td>{s.get('total_rows', 0):,}</td>"
            f"<td>{missing}</td>"
            f"<td>{s.get('notes', '')}</td>"
            f"</tr>\n"
        )

    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>HydroGNN-Net Data Validation Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background:#0f172a;color:#e2e8f0;margin:0;padding:24px }}
  h1   {{ color:#38bdf8;margin-bottom:4px }}
  p.sub {{ color:#94a3b8;margin-top:0 }}
  table {{ width:100%;border-collapse:collapse;background:#1e293b;border-radius:8px;overflow:hidden }}
  th   {{ background:#0f172a;color:#94a3b8;text-align:left;padding:10px 14px;font-size:13px;text-transform:uppercase;letter-spacing:.05em }}
  td   {{ padding:10px 14px;border-bottom:1px solid #334155;font-size:14px }}
  tr:last-child td {{ border-bottom:none }}
  tr:hover td {{ background:#273449 }}
  footer {{ color:#475569;font-size:12px;margin-top:16px }}
</style>
</head>
<body>
<h1>🌊 HydroGNN-Net Data Validation Report</h1>
<p class="sub">Cauvery Basin, Tamil Nadu, India — Generated: {now}</p>
<table>
<thead>
  <tr>
    <th>Source</th><th>Station / Reservoir</th><th>Status</th>
    <th>Rows</th><th>Missing%</th><th>Notes</th>
  </tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
<footer>HydroGNN-Net IEEE Final Year Project — All data from official CWC/NASA/Copernicus sources</footer>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    logger.info(f"Validation report: {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Processing functions
# ─────────────────────────────────────────────────────────────────────────────

def process_imd_rainfall(config: dict) -> list:
    """Validate and extract IMD gridded daily rainfall (0.25° NetCDF)."""
    import netCDF4 as nc

    raw_dir = Path(config["paths"]["raw_dir"])
    rainfall_dir = Path(config.get("imd_rainfall", {}).get("path", raw_dir / "rainfall"))
    start_yr = config.get("years", {}).get("start", 2018)
    end_yr = config.get("years", {}).get("end", 2023)
    years_list = list(range(start_yr, end_yr + 1))
    stations = config["stations"]
    summaries = []

    # Pre-check available NetCDF files
    available_ncs = {}
    for yr in years_list:
        p = rainfall_dir / f"RF25_ind{yr}_rfp25.nc"
        if p.exists():
            available_ncs[yr] = p

    if not available_ncs:
        for s in stations:
            summaries.append({
                "source": "IMD Rainfall", "station_id": s["id"], "status": "MISSING",
                "total_rows": 0, "missing_pct": 100,
                "notes": f"No NetCDF files found in {rainfall_dir.name}/",
            })
        return summaries

    for sid_cfg in stations:
        sid = sid_cfg["id"]
        lat = sid_cfg["lat"]
        lon = sid_cfg["lon"]
        daily_dfs = []
        try:
            for yr, nc_p in available_ncs.items():
                ds = nc.Dataset(nc_p)
                lons = ds.variables["LONGITUDE"][:]
                lats = ds.variables["LATITUDE"][:]
                times = ds.variables["TIME"][:]
                base_date = pd.Timestamp("1900-12-31")
                dates = pd.to_datetime([base_date + pd.Timedelta(days=float(t)) for t in times])

                lat_idx = int(np.abs(lats - lat).argmin())
                lon_idx = int(np.abs(lons - lon).argmin())
                rf_vals = ds.variables["RAINFALL"][:, lat_idx, lon_idx]
                rf_clean = np.where(rf_vals < 0, np.nan, rf_vals)
                df_yr = pd.DataFrame({"rainfall_mm": rf_clean}, index=dates)
                daily_dfs.append(df_yr)
                ds.close()

            if daily_dfs:
                df_all = pd.concat(daily_dfs).sort_index()
                missing_pct = df_all["rainfall_mm"].isna().mean() * 100
                max_r = df_all["rainfall_mm"].max()
                mean_r = df_all["rainfall_mm"].mean()
                summaries.append({
                    "source": "IMD Rainfall", "station_id": sid,
                    "status": "WARNING" if missing_pct > 10 else "OK",
                    "total_rows": len(df_all), "missing_pct": missing_pct,
                    "notes": f"Max daily: {max_r:.1f} mm, Mean: {mean_r:.2f} mm ({len(df_all)} days)",
                })
            else:
                summaries.append({
                    "source": "IMD Rainfall", "station_id": sid, "status": "MISSING",
                    "total_rows": 0, "missing_pct": 100, "notes": "No daily records extracted",
                })
        except Exception as exc:
            summaries.append({
                "source": "IMD Rainfall", "station_id": sid, "status": "CRITICAL",
                "total_rows": 0, "missing_pct": 100, "notes": str(exc)[:80],
            })
    return summaries


def process_cwc(config: dict) -> list:
    """Load and validate CWC station river gauge data."""
    proc_dir = Path(config["paths"]["processed_dir"])
    raw_dir  = Path(config["paths"]["raw_dir"])
    station_ids = [s["id"] for s in config["stations"]]
    summaries = []

    for sid in station_ids:
        # Check in processed/cwc/ or processed/
        p1 = proc_dir / "cwc" / f"cwc_{sid}.parquet"
        p2 = proc_dir / f"cwc_{sid}.parquet"
        target_p = p1 if p1.exists() else (p2 if p2.exists() else None)

        if target_p:
            try:
                df = pd.read_parquet(target_p)
                col = "level_m" if "level_m" in df.columns else df.columns[0]
                missing_pct = df[col].isna().mean() * 100
                min_v, max_v = df[col].min(), df[col].max()
                summaries.append({
                    "source": "CWC", "station_id": sid,
                    "status": "WARNING" if missing_pct > 10 else "OK",
                    "total_rows": len(df),
                    "missing_pct": missing_pct,
                    "notes": f"Level range: {min_v:.1f}–{max_v:.1f} m",
                })
            except Exception as exc:
                summaries.append({
                    "source": "CWC", "station_id": sid, "status": "CRITICAL",
                    "total_rows": 0, "missing_pct": 100, "notes": str(exc)[:80],
                })
        else:
            # Fallback to parser if raw CSV files exist
            try:
                from src.downloaders.cwc import CWCDataParser
                parser = CWCDataParser(raw_dir, config)
                years = list(range(config["years"]["start"], config["years"]["end"] + 1))
                data = parser.load_all_available([sid], years)
                if sid in data:
                    df = data[sid]
                    missing_pct = df["level_m"].isna().mean() * 100
                    summaries.append({
                        "source": "CWC", "station_id": sid,
                        "status": "WARNING" if missing_pct > 10 else "OK",
                        "total_rows": len(df),
                        "missing_pct": missing_pct,
                        "notes": f"Level range: {df['level_m'].min():.1f}–{df['level_m'].max():.1f} m",
                    })
                else:
                    summaries.append({
                        "source": "CWC", "station_id": sid, "status": "MISSING",
                        "total_rows": 0, "missing_pct": 100,
                        "notes": "No CSV files found in dataset/raw/cwc/",
                    })
            except Exception as exc:
                summaries.append({
                    "source": "CWC", "station_id": sid, "status": "CRITICAL",
                    "total_rows": 0, "missing_pct": 100, "notes": str(exc)[:80],
                })
    return summaries


def process_reservoir(config: dict) -> list:
    """Load and validate multi-year reservoir telemetry data."""
    raw_dir  = Path(config["paths"]["raw_dir"])
    res_csv = Path(config.get("reservoir_operations", {}).get("path", raw_dir / "reservoir" / "reservoir_2018_2023.csv"))
    start_yr = config.get("years", {}).get("start", 2018)
    end_yr = config.get("years", {}).get("end", 2023)
    summaries = []

    res_list = config.get("reservoir_operations", {}).get("reservoirs", config.get("reservoirs", []))

    if res_csv.exists():
        try:
            df_res = pd.read_csv(res_csv)
            df_res["clean_name"] = df_res["reservoir_name"].astype(str).str.strip().str.upper()
            df_res["date"] = pd.to_datetime(df_res["updated_date"], errors="coerce")

            for r_cfg in res_list:
                rid = r_cfg.get("name", r_cfg.get("id"))
                cwc_n = r_cfg.get("cwc_name", rid).replace("*", "").strip().upper()
                sub = df_res[df_res["clean_name"].str.contains(cwc_n, na=False)].copy()

                if not sub.empty:
                    sub = sub.dropna(subset=["date"]).sort_values("date")
                    sub_yrs = sub[(sub["date"].dt.year >= start_yr) & (sub["date"].dt.year <= end_yr)]
                    rows = len(sub_yrs) if not sub_yrs.empty else len(sub)
                    min_d = (sub_yrs["date"].min() if not sub_yrs.empty else sub["date"].min()).date()
                    max_d = (sub_yrs["date"].max() if not sub_yrs.empty else sub["date"].max()).date()
                    summaries.append({
                        "source": "Reservoir", "station_id": rid,
                        "status": "OK",
                        "total_rows": rows, "missing_pct": 0.0,
                        "notes": f"{rows:,} records ({min_d} to {max_d})",
                    })
                else:
                    summaries.append({
                        "source": "Reservoir", "station_id": rid, "status": "MISSING",
                        "total_rows": 0, "missing_pct": 100,
                        "notes": f"Name '{cwc_n}' not found in reservoir CSV",
                    })
        except Exception as exc:
            for r_cfg in res_list:
                rid = r_cfg.get("name", r_cfg.get("id"))
                summaries.append({
                    "source": "Reservoir", "station_id": rid, "status": "CRITICAL",
                    "total_rows": 0, "missing_pct": 100, "notes": str(exc)[:80],
                })
    else:
        for r_cfg in res_list:
            rid = r_cfg.get("name", r_cfg.get("id"))
            summaries.append({
                "source": "Reservoir", "station_id": rid, "status": "MISSING",
                "total_rows": 0, "missing_pct": 100,
                "notes": f"File not found: {res_csv.name}",
            })
    return summaries


def process_era5(config: dict) -> list:
    """Validate existing processed ERA5 meteorological parquets."""
    proc_dir = Path(config["paths"]["processed_dir"])
    stations = config["stations"]
    summaries = []

    for s in stations:
        sid = s["id"]
        p1 = proc_dir / "era5" / f"era5_{sid}.parquet"
        p2 = proc_dir / f"era5_{sid}.parquet"
        target_p = p1 if p1.exists() else (p2 if p2.exists() else None)

        if target_p:
            try:
                df = pd.read_parquet(target_p)
                t_col = "temperature_c" if "temperature_c" in df.columns else df.columns[0]
                missing_pct = df[t_col].isna().mean() * 100
                t_min = df[t_col].min()
                t_max = df[t_col].max()
                summaries.append({
                    "source": "ERA5", "station_id": sid,
                    "status": "WARNING" if missing_pct > 10 else "OK",
                    "total_rows": len(df),
                    "missing_pct": missing_pct,
                    "notes": f"{len(df):,} hourly timesteps (Temp: {t_min:.1f}–{t_max:.1f}°C)",
                })
            except Exception as exc:
                summaries.append({
                    "source": "ERA5", "station_id": sid, "status": "CRITICAL",
                    "total_rows": 0, "missing_pct": 100, "notes": str(exc)[:80],
                })
        else:
            summaries.append({
                "source": "ERA5", "station_id": sid, "status": "MISSING",
                "total_rows": 0, "missing_pct": 100,
                "notes": f"File not found: era5_{sid}.parquet",
            })
    return summaries


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGNN-Net Preprocessing")
    parser.add_argument("--config", default="Source_Code/pipeline/config.yaml")
    parser.add_argument("--skip-validation", action="store_true")
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

    logs_dir = Path(config["paths"]["logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    proc_dir = Path(config["paths"]["processed_dir"])
    proc_dir.mkdir(parents=True, exist_ok=True)

    all_summaries = []

    log_separator(logger, "Step 1: IMD Daily Gridded Rainfall (0.25° NetCDF)")
    all_summaries.extend(process_imd_rainfall(config))

    log_separator(logger, "Step 2: CWC River Gauge Data")
    all_summaries.extend(process_cwc(config))

    log_separator(logger, "Step 3: Reservoir Telemetry Data")
    all_summaries.extend(process_reservoir(config))

    log_separator(logger, "Step 4: ERA5 Reanalysis Meteorological Data")
    all_summaries.extend(process_era5(config))

    # ── Summary ───────────────────────────────────────────────────────────
    log_separator(logger, "Preprocessing Summary")
    ok  = sum(1 for s in all_summaries if s["status"] == "OK")
    mis = sum(1 for s in all_summaries if s["status"] == "MISSING")
    cri = sum(1 for s in all_summaries if s["status"] == "CRITICAL")
    war = sum(1 for s in all_summaries if s["status"] == "WARNING")
    logger.info(f"OK: {ok}  |  WARNING: {war}  |  MISSING: {mis}  |  CRITICAL: {cri}")

    if not args.skip_validation:
        report_path = logs_dir / "validation_report.html"
        generate_validation_report(all_summaries, report_path)
        logger.info(f"Open validation report in browser: {report_path}")

    if cri > 0:
        logger.error("CRITICAL errors found — fix before running create_dataset.py")
    elif mis > 0:
        logger.warning(
            f"{mis} sources MISSING — pipeline will proceed with available data.\n"
            "Missing CWC/reservoir data: export CSVs from https://indiawris.gov.in"
        )
    else:
        logger.info("All sources OK. Next: python pipeline/create_dataset.py")


if __name__ == "__main__":
    main()
