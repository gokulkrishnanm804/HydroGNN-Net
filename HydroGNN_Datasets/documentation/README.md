# HydroGNN-Net Standalone Dataset Repository

This standalone dataset repository contains all historical observations, meteorological reanalysis, terrain rasters, river network topology, processed Parquet features, PyTorch Geometric tensors, and live API sample payloads for **HydroGNN-Net**.

## Repository Structure

```
HydroGNN_Datasets/
├── raw/                      # Raw historical CSV, NetCDF, GeoTIFF, and Shapefiles
│   ├── cwc/                  # CWC gauge telemetry (1991–2025)
│   ├── era5/                 # ERA5-Land reanalysis
│   ├── rainfall/             # IMD gridded daily rainfall NetCDF (2018–2023)
│   ├── reservoir/            # CWC reservoir telemetry
│   ├── srtm/                 # NASA SRTM elevation & slope GeoTIFFs
│   └── hydrorivers/          # HydroRIVERS Cauvery mainstem vector shapefiles
├── processed/                # Resampled and aligned Parquet feature files
│   ├── cwc/                  # 30-min resampled station water level targets
│   └── era5/                 # 105,096 hourly timestep meteorology per node
├── graph/                    # Graph topology files (nodes.csv, edges.csv, edge_attr)
├── pytorch/                  # PyTorch Geometric tensors (train.pt, val.pt, test.pt, scaler.pkl)
├── sqlite/                   # Active HydroGNN SQLite database (hydrognn.db)
├── live_api_examples/        # Sample JSON payloads for OpenWeather, Open-Meteo, Copernicus STAC
└── documentation/            # Dataset inventory and complete documentation
```

## Dataset Summary Statistics
- **Total Storage:** `2.091 GB` (2141.09 MB)
- **Files Extracted:** `52`
- **Integrity Status:** 🟢 SHA-256 Checksum Verified (100% Identical to Source Project)
