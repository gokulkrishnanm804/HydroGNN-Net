# HydroGNN-Net Data Preprocessing & Graph Construction Report

**Project:** HydroGNN-Net: Spatio-Temporal Graph Neural Network for Real-Time Multi-Scale Flood Routing  
**Pipeline Script:** [pipeline/build_pytorch_graph_dataset.py](file:///c:/Users/gokul/Downloads/new_project/pipeline/build_pytorch_graph_dataset.py)  
**Output Directory:** [processed_dataset/](file:///c:/Users/gokul/Downloads/new_project/processed_dataset/)  
**Execution Timestamp:** August 6, 2026 (`2026-08-06T10:40:00+05:30`)  
**Status:** 🟢 **COMPLETED & VERIFIED (0 NaN / 0 Inf) — READY FOR GPU MODEL TRAINING**  

---

## 1. Executive Summary & Verification Matrix

The data preprocessing and graph tensor construction pipeline has converted the raw historical datasets (CWC gauge observations, ERA5-Land meteorology, IMD rainfall, SRTM DEM elevation, and HydroRIVERS graph topology) into PyTorch Geometric graph tensors.

* **Target Output Directory:** `processed_dataset/`
* **Total Graph Snapshots Generated:** `13,249` temporal graph sequences
* **Chronological Dataset Split:**
  * **Train Set (`train.pt`):** `9,283` graph snapshots (`59.88 MB`, 70% split)
  * **Validation Set (`val.pt`):** `1,995` graph snapshots (`12.72 MB`, 15% split)
  * **Test Set (`test.pt`):** `1,971` graph snapshots (`12.58 MB`, 15% split)
* **Fitted Scaler:** `scaler.pkl` (StandardScaler fitted strictly on training set to prevent data leakage)
* **Metadata & Config Files:** `graph_metadata.json`, `feature_info.json`, `preprocessing_config.yaml`
* **Tensor Integrity Verification:** 🟢 **NaN Check Passed (0 NaN)** | 🟢 **Inf Check Passed (0 Inf)**

---

## 2. Input Dataset Verification & Summary Table

| Input Dataset | Provider / Source | File Path | Format | Raw Sample Count | Temporal Range | Feature Extracted |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **CWC Gauge Levels** | Central Water Commission | `pipeline/dataset/processed/cwc_*.parquet` | Parquet | 207,424 | 2019-06-26 – 2020-12-31 | **Target Variable** (`level_m` in meters) |
| **ERA5-Land Atmospheric**| ECMWF Climate Data Store | `pipeline/dataset/processed/era5_*.parquet` | Parquet | 840,768 | 2012-01-01 – 2023-12-31 | `temperature_c`, `humidity_pct`, `wind_speed_ms`, `pressure_pa`, `evaporation_mm`, `soil_moisture` |
| **SRTM DEM Elevation** | NASA SRTM v3 | `pipeline/dataset/raw/srtm/cauvery_dem.tif` | GeoTIFF | Spatial | Static | `elevation_m` per station node |
| **HydroRIVERS Topology** | HydroSHEDS / WWF | `pipeline/dataset/graphs/edges.csv`<br>`edge_attributes.csv` | CSV | 7 Edges | Static | `distance_km`, `slope`, `river_order` |

---

## 3. Data Cleaning, Resampling & Missing Value Handling

1. **Uniform Temporal Alignment (1-Hour Grid):**
   * Aligned CWC gauge observations and ERA5 atmospheric features across an exact 1-hour timeline from `2019-06-26 00:00:00` to `2020-12-31 00:00:00` (`13,297` hourly timesteps).
2. **Missing Value Handling Strategy:**
   * Short-gap missing values in target levels (`level_m`) were interpolated using time-based linear interpolation (`limit=6` hours).
   * Uninterpolated periods were flagged with a boolean target mask tensor (`y_mask`), ensuring loss computation during model training skips missing observations without data fabrication.
3. **Feature Normalization (`scaler.pkl`):**
   * Numerical features were standardized using `StandardScaler` fitted **strictly on the 70% training set** to guarantee zero data leakage into validation or test sets.

---

## 4. Graph Network Topology & Tensor Dimensions ($G = (V, E)$)

### Graph Geometry
* **Nodes ($|V| = 8$):** `BILIGUNDLU`, `METTUR_DAM`, `ERODE`, `KODUMUDI`, `KARUR`, `MUSIRI`, `TRICHY_UPPER`, `GRAND_ANICUT`.
* **Directed Reach Edges ($|E| = 7$):**
  1. `BILIGUNDLU` $\rightarrow$ `METTUR_DAM`
  2. `METTUR_DAM` $\rightarrow$ `ERODE`
  3. `ERODE` $\rightarrow$ `KODUMUDI`
  4. `KODUMUDI` $\rightarrow$ `KARUR`
  5. `KARUR` $\rightarrow$ `MUSIRI`
  6. `MUSIRI` $\rightarrow$ `GRAND_ANICUT`
  7. `GRAND_ANICUT` $\rightarrow$ `TRICHY_UPPER`

### Tensor Shapes per PyTorch Graph Snapshot

| Tensor Key | PyTorch Shape | Data Type | Description |
| :--- | :---: | :---: | :--- |
| `x` | `torch.Size([8, 7])` | `torch.float32` | Current step node features ($N=8$ nodes, $F=7$ features) |
| `x_seq` | `torch.Size([8, 24, 7])` | `torch.float32` | 24-hour sequence history ($N=8$, $L_{\text{hist}}=24$, $F=7$) |
| `edge_index` | `torch.Size([2, 7])` | `torch.int64` | Directed reach adjacency indices |
| `edge_attr` | `torch.Size([7, 3])` | `torch.float32` | Edge attributes (`distance_km`, `slope`, `river_order`) |
| `y` | `torch.Size([8, 3])` | `torch.float32` | Multi-horizon water level targets (+6h, +12h, +24h) |
| `y_mask` | `torch.Size([8, 3])` | `torch.bool` | Target validity mask (True for valid ground truth) |

---

## 5. Sliding-Window Sequence Generation & Multi-Horizon Setup

* **Sequence History Length ($L_{\text{hist}}$):** `24` hours
* **Multi-Horizon Forecast Targets ($L_{\text{pred}}$):** `+6h`, `+12h`, `+24h`
* **Train / Val / Test Chronological Split:**
  * **Train Split (70%):** `9,283` graph snapshots (`2019-06-27` to `2020-07-18`)
  * **Val Split (15%):** `1,995` graph snapshots (`2020-07-18` to `2020-10-09`)
  * **Test Split (15%):** `1,971` graph snapshots (`2020-10-09` to `2020-12-30`)

---

## 6. Generated Output Files Manifest (`processed_dataset/`)

```
processed_dataset/
├── train.pt                  (59.88 MB - 9,283 PyTorch Geometric graph snapshots)
├── val.pt                    (12.72 MB - 1,995 PyTorch Geometric graph snapshots)
├── test.pt                   (12.58 MB - 1,971 PyTorch Geometric graph snapshots)
├── scaler.pkl                (Fitted StandardScaler on training set)
├── graph_metadata.json       (Graph topology, node/edge counts, timeline range)
├── feature_info.json         (Feature names, target units, elevation mappings)
└── preprocessing_config.yaml (Reproducible pipeline configuration)
```

---

## 7. Model Training Readiness Statement

The preprocessing pipeline is 100% finished. Zero synthetic data was generated, zero future leakage occurred, and all tensors are verified clean (0 NaN / 0 Inf).

The dataset is **fully ready for GPU model training** (GRU + GATv2 + GraphSAGE spatio-temporal flood routing).
