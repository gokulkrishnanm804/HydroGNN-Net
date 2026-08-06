# HydroGNN-Net: A Spatio-Temporal Graph Neural Network for Real-Time Multi-Scale Flood Routing

[![PyTorch](https://img.shields.io/badge/PyTorch-2.0%2B-ee4c2c.svg)](https://pytorch.org/)
[![PyG](https://img.shields.io/badge/PyTorch_Geometric-2.3%2B-3C2179.svg)](https://pytorch-geometric.readthedocs.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14.0-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 🌊 Executive Summary & Research Motivation

**HydroGNN-Net** is an academic and production-grade spatio-temporal Graph Neural Network framework designed for real-time hydrological forecasting, multi-horizon river level prediction, and hydraulic reservoir routing across major river basins.

By unifying physics-informed hydraulics (Level-Pool Mass Balance Continuity & CWC Standard Operating Policy rule curves) with deep graph representations (GRU + GATv2 + GraphSAGE), HydroGNN-Net models complex upstream-to-downstream water propagation across Cauvery River basin gauging stations.

---

## 🏗️ System Architecture

```
                               LIVE TELEMETRY INGESTION
          ┌───────────────────────────────┬───────────────────────────────┐
          ▼                               ▼                               ▼
  OpenWeather API              Open-Meteo Flood API             Copernicus STAC S2
  (Meteorology)                (Upstream Inflow)                (Reservoir Area)
          │                               │                               │
          └───────────────────────────────┼───────────────────────────────┘
                                          ▼
                             HydroGNN Ingestion Pipeline
                                          │
                                          ▼
                      Level-Pool Reservoir Routing Engine
                                          │
                                          ▼
                 ┌─────────────────────────────────────────────────┐
                 │ PyTorch Geometric Spatio-Temporal Graph Model   │
                 │                                                 │
                 │   x_seq [N=8, T=24, F=7]                        │
                 │              │                                  │
                 │              ▼                                  │
                 │      Temporal GRU Encoder  [N=8, 128]           │
                 │              │                                  │
                 │              ▼                                  │
                 │     GATv2 Spatial Attention [N=8, 128]          │
                 │              │                                  │
                 │              ▼                                  │
                 │    GraphSAGE Neighborhood Refinement            │
                 │              │                                  │
                 │     ┌────────┴────────┐                         │
                 │     ▼                 ▼                         │
                 │ MultiHorizon      Uncertainty                   │
                 │ Head [N=8, 3]    Head [N=8, 3]                  │
                 └─────────────────────────────────────────────────┘
                                          │
                                          ▼
                             FastAPI Backend REST Endpoints
                                          │
                                          ▼
                            Next.js 14 Web Dashboard UI
```

---

## 📁 Repository Structure

```
HydroGNN_Project/
├── Source_Code/           # FastAPI Backend Server, Next.js React UI, Pipeline Builders
├── HydroGNN_Datasets/     # Standalone Dataset Repo (Raw CSV, NetCDF, GeoTIFF, PyTorch .pt)
├── Documentation/         # Architecture Specs, API Guides, RunPod Deployment Guide
├── IEEE_Paper/            # Academic Manuscript Draft, LaTeX Bibliography, Figures
├── PPT/                   # Presentation Slides, System Flowcharts, GNN Schematics
├── Reports/               # Comprehensive Suite of 12 Audit & Readiness Reports
├── Training/              # PyTorch Training, Evaluation, and Export Scripts
├── Models/                # Saved Model Checkpoints (`Checkpoints/`, `Best_Model/`)
├── Experiments/           # TensorBoard Logs, CSV Logs, Plots, and Results
├── README.md              # Master Documentation
├── requirements.txt       # Python Dependencies
├── LICENSE                # MIT License
└── .gitignore             # Git & Git LFS Configurations
```

---

## ⚡ Quick Start & Running Locally

### 1. Backend Server (FastAPI)
```bash
cd Source_Code/backend
python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000
```

### 2. Frontend Application (Next.js 14)
```bash
cd Source_Code/frontend
npm run dev
```
Open [http://localhost:3000](http://localhost:3000). Credentials: `admin@hydrognn.in` / `hydrognn2026`.

---

## 🚀 RunPod GPU Training Setup

Refer to [Documentation/RunPod_Deployment_Guide.md](Documentation/RunPod_Deployment_Guide.md) for full cloud GPU deployment instructions.

```bash
# Clone & Fetch LFS Datasets
git clone https://github.com/gokulkrishnanm804/HydroGNN-Net.git
cd HydroGNN-Net
git lfs pull

# Install & Train
pip install -r requirements.txt
cd Training
python train.py --config Source_Code/configs/config.yaml
```

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
