# HydroGNN-Net RunPod GPU Deployment & Training Guide

This guide provides step-by-step instructions for deploying and training **HydroGNN-Net** on cloud GPU infrastructure (RunPod, Lambda Labs, or AWS EC2).

---

## 1. GPU Instance Recommendations

* **Recommended GPU:** NVIDIA RTX 4090 (24GB VRAM) or NVIDIA A100 (40GB VRAM)
* **Minimum GPU:** NVIDIA RTX 3060 (8GB VRAM)
* **Container Environment:** PyTorch 2.1.0+ / CUDA 12.1 (e.g. `runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04`)
* **Container Disk:** 20 GB+
* **Volume Disk:** 50 GB+

---

## 2. Environment Setup & Cloning

### Step 2.1: Clone Repository with Git LFS
```bash
# Install Git LFS inside the container if needed
apt-get update && apt-get install -y git-lfs
git lfs install

# Clone HydroGNN-Net
git clone https://github.com/gokulkrishnanm804/HydroGNN-Net.git
cd HydroGNN-Net

# Pull Git LFS datasets & tensors (train.pt, val.pt, test.pt)
git lfs pull
```

### Step 2.2: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt

# Verify PyTorch & CUDA Availability
python -c "import torch; print('CUDA Available:', torch.cuda.is_available()); print('GPU Name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

---

## 3. Running Pre-Training Integrity Verification

Before training, run the automated dataset and model readiness verification script:
```bash
python Source_Code/pipeline/build_pytorch_graph_dataset.py
```

---

## 4. Launching Model Training

Run the PyTorch Geometric training script:
```bash
cd Training
python train.py --config Source_Code/configs/config.yaml --epochs 100 --batch-size 128
```

### Mixed Precision & Multi-GPU Training (Optional)
```bash
# Automatic Mixed Precision (AMP) enabled by default
python train.py --config Source_Code/configs/config.yaml --amp --device cuda:0
```

---

## 5. Model Checkpoints & Evaluation

Trained model checkpoints will automatically be saved to:
`Training/checkpoints/` and `Models/Best_Model/best_checkpoint.pt`.

To run post-training evaluation and calculate RMSE, MAE, NSE, and R² metrics:
```bash
python Training/evaluate.py --checkpoint Models/Best_Model/best_checkpoint.pt
```

---

## 6. Troubleshooting & Support

* **Out of Memory (OOM):** Reduce `--batch-size` to `64` or `32` in `config.yaml`.
* **Git LFS Pointer File Error:** Run `git lfs pull` to fetch binary PyTorch `.pt` files.
