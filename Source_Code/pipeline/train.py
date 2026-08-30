"""
HydroGNN-Net Model Training Script
====================================
Trains the HydroGNN-Net Spatio-Temporal GNN for multi-horizon flood forecasting.

Prerequisites
-------------
1. Run: python pipeline/download_all.py
2. Run: python pipeline/preprocess.py
3. Run: python pipeline/create_dataset.py

Usage
-----
    python pipeline/train.py
    python pipeline/train.py --config pipeline/config.yaml
    python pipeline/train.py --epochs 100
    python pipeline/train.py --resume  # Resume from last checkpoint
    python pipeline/train.py --device cuda
    python pipeline/train.py --batch-size 8

Outputs
-------
    dataset/models/best_model.pt           Best model (lowest val NSE loss)
    dataset/models/last_checkpoint.pt      Last epoch checkpoint
    dataset/logs/training_log.csv          Per-epoch metrics
    dataset/logs/training_curves.png       Loss curves visualization
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import numpy as np
import torch
import yaml
from torch_geometric.loader import DataLoader

from src.dataset.hydro_dataset import HydroGNNDataset
from src.dataset.splitter import ChronologicalSplitter
from src.model.hydrognn_net import HydroGNNNet, HydroGNNLoss
from src.utils.logger import get_logger, log_separator
from src.utils.metrics import nash_sutcliffe, kling_gupta, rmse, mae, pbias

logger = get_logger("train")


# ─────────────────────────────────────────────────────────────────────────────
# Training loop
# ─────────────────────────────────────────────────────────────────────────────

def train_epoch(
    model: HydroGNNNet,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: HydroGNNLoss,
    device: torch.device,
    grad_clip: float,
) -> float:
    """Run one training epoch. Returns mean batch loss."""
    model.train()
    total_loss = 0.0
    n_batches  = 0

    for batch in loader:
        batch = batch.to(device)
        optimizer.zero_grad()

        y_curr = getattr(batch, "y_curr", None)
        pred_delta, log_var = model(batch.x, batch.edge_index, batch.edge_attr, y_curr=y_curr)

        # Delta target & mask: train on delta_y = y(t+h) - y(t)
        target = batch.delta_y if hasattr(batch, "delta_y") else batch.y
        mask = batch.delta_mask if hasattr(batch, "delta_mask") else getattr(batch, "mask", None)
        loss = criterion(pred_delta, target, log_var=log_var, mask=mask)

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        optimizer.step()

        total_loss += loss.item()
        n_batches  += 1

    return total_loss / max(n_batches, 1)


@torch.no_grad()
def evaluate(
    model: HydroGNNNet,
    loader: DataLoader,
    criterion: HydroGNNLoss,
    device: torch.device,
    normalizer=None,
    target_col: str = "water_level_m",
) -> dict:
    """Evaluate model on a DataLoader. Returns metric dict."""
    model.eval()
    all_pred, all_true, all_mask = [], [], []
    total_loss = 0.0
    n_batches  = 0

    for batch in loader:
        batch = batch.to(device)
        y_curr = getattr(batch, "y_curr", None)
        pred_delta, log_var = model(batch.x, batch.edge_index, batch.edge_attr, y_curr=y_curr)

        target = batch.delta_y if hasattr(batch, "delta_y") else batch.y
        mask = batch.delta_mask if hasattr(batch, "delta_mask") else getattr(batch, "mask", None)
        loss = criterion(pred_delta, target, log_var=log_var, mask=mask)
        total_loss += loss.item()
        n_batches  += 1

        # Reconstruct physical future stage: y_pred = y_curr + pred_delta
        if y_curr is not None:
            y_curr_exp = y_curr.unsqueeze(-1) if y_curr.ndim == 1 else y_curr
            pred_stage = y_curr_exp + pred_delta
        else:
            pred_stage = pred_delta

        # Collect all horizons [N, 3]
        p = pred_stage.cpu().numpy()
        t = batch.y.cpu().numpy()
        if mask is not None:
            if mask.ndim == 1:
                m = np.repeat(mask.cpu().numpy().astype(bool)[:, None], 3, axis=1)
            else:
                m = mask.cpu().numpy().astype(bool)
        else:
            m = np.ones_like(t, dtype=bool)

        all_pred.append(p)
        all_true.append(t)
        all_mask.append(m)

    pred_arr = np.concatenate(all_pred, axis=0) # [Total_nodes, 3]
    true_arr = np.concatenate(all_true, axis=0) # [Total_nodes, 3]
    mask_arr = np.concatenate(all_mask, axis=0) # [Total_nodes, 3]

    # Inverse-normalise if scaler available
    if normalizer is not None:
        pred_arr = normalizer.inverse_transform_column(target_col, pred_arr)
        true_arr = normalizer.inverse_transform_column(target_col, true_arr)

    # Filter NaN and apply effective mask
    valid = np.isfinite(pred_arr) & np.isfinite(true_arr) & mask_arr
    p_flat, t_flat = pred_arr[valid], true_arr[valid]

    # Per-horizon NSEs
    h_nses = []
    for h_i in range(min(3, pred_arr.shape[1])):
        v_h = valid[:, h_i]
        if v_h.sum() > 1:
            h_nses.append(float(nash_sutcliffe(true_arr[v_h, h_i], pred_arr[v_h, h_i])))
        else:
            h_nses.append(float("nan"))

    return {
        "loss":     total_loss / max(n_batches, 1),
        "NSE":      nash_sutcliffe(t_flat, p_flat) if len(t_flat) > 1 else float("nan"),
        "KGE":      kling_gupta(t_flat, p_flat) if len(t_flat) > 1 else float("nan"),
        "RMSE":     rmse(t_flat, p_flat) if len(t_flat) > 0 else float("nan"),
        "MAE":      mae(t_flat, p_flat) if len(t_flat) > 0 else float("nan"),
        "PBIAS":    pbias(t_flat, p_flat) if len(t_flat) > 0 else float("nan"),
        "NSE_H6":   h_nses[0] if len(h_nses) > 0 else float("nan"),
        "NSE_H12":  h_nses[1] if len(h_nses) > 1 else float("nan"),
        "NSE_H24":  h_nses[2] if len(h_nses) > 2 else float("nan"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint utilities
# ─────────────────────────────────────────────────────────────────────────────

def save_checkpoint(
    model: HydroGNNNet,
    optimizer: torch.optim.Optimizer,
    scheduler,
    epoch: int,
    val_metrics: dict,
    cfg: dict,
    path: Path,
) -> None:
    torch.save(
        {
            "epoch":       epoch,
            "model_state": model.state_dict(),
            "optim_state": optimizer.state_dict(),
            "sched_state": scheduler.state_dict() if scheduler else None,
            "val_metrics": val_metrics,
            "model_config": cfg,
        },
        path,
    )


def load_checkpoint(path: Path, model: HydroGNNNet, optimizer, scheduler) -> int:
    """Load checkpoint. Returns the epoch number."""
    ckpt  = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["model_state"])
    optimizer.load_state_dict(ckpt["optim_state"])
    if scheduler and ckpt.get("sched_state"):
        scheduler.load_state_dict(ckpt["sched_state"])
    epoch = ckpt.get("epoch", 0)
    logger.info(f"Resumed from checkpoint (epoch {epoch}): {path}")
    return epoch


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGNN-Net Training")
    parser.add_argument("--config",     default="Source_Code/pipeline/config.yaml")
    parser.add_argument("--epochs",     type=int,   default=None)
    parser.add_argument("--batch-size", type=int,   default=None)
    parser.add_argument("--lr",         type=float, default=None)
    parser.add_argument("--device",     choices=["auto", "cuda", "cpu"], default=None)
    parser.add_argument("--resume",     action="store_true",
                        help="Resume training from last checkpoint")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        if (REPO_ROOT / config_path).exists():
            config_path = REPO_ROOT / config_path
        elif (PIPELINE_DIR / config_path.name).exists():
            config_path = PIPELINE_DIR / config_path.name
        else:
            config_path = REPO_ROOT / config_path
    with open(config_path) as fh:
        config = yaml.safe_load(fh)

    # Resolve paths against REPO_ROOT
    for key in config.get("paths", {}):
        p = Path(config["paths"][key])
        if not p.is_absolute():
            config["paths"][key] = str(REPO_ROOT / p)

    # CLI overrides
    train_cfg = config["training"]
    if args.epochs:     train_cfg["epochs"]     = args.epochs
    if args.batch_size: train_cfg["batch_size"] = args.batch_size
    if args.lr:         train_cfg["lr"]          = args.lr
    if args.device:     train_cfg["device"]      = args.device

    # ── Device ────────────────────────────────────────────────────────────
    dev_str = train_cfg.get("device", "auto")
    if dev_str == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(dev_str)
    logger.info(f"Device: {device}")

    # ── Reproducibility ───────────────────────────────────────────────────
    seed = int(train_cfg.get("seed", 42))
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    # Full determinism for reproducibility (slight performance cost)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark     = False
    os.environ["PYTHONHASHSEED"]        = str(seed)

    def _worker_init(worker_id: int) -> None:
        np.random.seed(seed + worker_id)
        import random; random.seed(seed + worker_id)

    # ── Dataset ───────────────────────────────────────────────────────────
    splits_dir = Path(config["paths"]["splits_dir"])

    log_separator(logger, "Loading Datasets")
    try:
        train_ds = HydroGNNDataset(str(splits_dir), split="train")
        val_ds   = HydroGNNDataset(str(splits_dir), split="val")
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    bs = int(train_cfg["batch_size"])
    train_loader = DataLoader(
        train_ds, batch_size=bs, shuffle=True,
        num_workers=0, pin_memory=(device.type == "cuda"),
        worker_init_fn=_worker_init,
    )
    val_loader = DataLoader(
        val_ds, batch_size=bs, shuffle=False,
        num_workers=0, pin_memory=(device.type == "cuda"),
    )

    # ── Model ─────────────────────────────────────────────────────────────
    log_separator(logger, "Building HydroGNN-Net")
    if len(train_ds) > 0:
        s0 = train_ds[0]
        ds_n_feat = int(s0.x.shape[-1])
        ds_e_dim  = int(s0.edge_attr.shape[-1])
        cfg_n_feat = int(config["model"]["node_features"])
        cfg_e_dim  = int(config["model"]["edge_dim"])
        if ds_n_feat != cfg_n_feat:
            raise ValueError(
                f"Dataset node feature dimension ({ds_n_feat}) does not match "
                f"config.yaml model.node_features ({cfg_n_feat})."
            )
        if ds_e_dim != cfg_e_dim:
            raise ValueError(
                f"Dataset edge attribute dimension ({ds_e_dim}) does not match "
                f"config.yaml model.edge_dim ({cfg_e_dim})."
            )
    model = HydroGNNNet.from_config(config["model"]).to(device)
    logger.info(f"Parameters: {model.count_parameters():,}")

    # ── Optimiser & Scheduler ─────────────────────────────────────────────
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(train_cfg["lr"]),
        weight_decay=float(train_cfg["weight_decay"]),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=int(train_cfg.get("scheduler_T_max", 100)),
        eta_min=float(train_cfg["lr"]) * 0.01,
    )

    # ── Loss ──────────────────────────────────────────────────────────────
    criterion = HydroGNNLoss(
        mse_weight=float(train_cfg.get("mse_weight", 1.0)),
        mae_weight=float(train_cfg.get("mae_weight", 0.5)),
        nse_weight=float(train_cfg.get("nse_weight", 0.3)),
        physics_weight=float(train_cfg.get("physics_weight", 0.1)),
        delta_reg_weight=float(train_cfg.get("delta_reg_weight", 0.25)),
    )

    # ── Resume ────────────────────────────────────────────────────────────
    models_dir    = Path(config["paths"]["models_dir"])
    models_dir.mkdir(parents=True, exist_ok=True)
    ckpt_dir      = Path(config["paths"]["checkpoints_dir"])
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    last_ckpt     = models_dir / "last_checkpoint.pt"
    best_ckpt     = models_dir / "best_model.pt"

    start_epoch  = 0
    best_val_mae = float("inf")   # Exp 5: optimise toward lower MAE (persistence = 0.170 m)
    patience_ctr = 0

    if args.resume and last_ckpt.exists():
        start_epoch = load_checkpoint(last_ckpt, model, optimizer, scheduler)

    # ── Training log ──────────────────────────────────────────────────────
    logs_dir  = Path(config["paths"]["logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path  = logs_dir / "training_log.csv"
    LOG_COLS  = ["epoch", "train_loss", "val_loss", "val_NSE", "val_KGE",
                 "val_RMSE", "val_MAE", "val_PBIAS", "lr", "duration_s",
                 "ckpt_saved"]   # 1 = new best_model.pt saved this epoch
    if not log_path.exists():
        with open(log_path, "w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=LOG_COLS).writeheader()

    # ── Main training loop ────────────────────────────────────────────────
    n_epochs  = int(train_cfg["epochs"])
    patience  = int(train_cfg.get("patience", 15))
    min_delta = float(train_cfg.get("min_delta", 0.001))
    grad_clip = float(train_cfg.get("grad_clip", 1.0))

    log_separator(logger, f"Training HydroGNN-Net ({device})")

    for epoch in range(start_epoch + 1, n_epochs + 1):
        t_start = time.monotonic()

        train_loss = train_epoch(model, train_loader, optimizer, criterion,
                                  device, grad_clip)
        val_metrics = evaluate(model, val_loader, criterion, device)
        scheduler.step()

        elapsed = time.monotonic() - t_start
        cur_lr  = optimizer.param_groups[0]["lr"]
        val_nse = val_metrics["NSE"]
        val_mae = val_metrics["MAE"]   # primary criterion (Exp 5)
        ckpt_saved = 0

        # Logging
        logger.info(
            f"Epoch {epoch:03d}/{n_epochs} | "
            f"Train: {train_loss:.4f} | "
            f"Val: {val_metrics['loss']:.4f} | "
            f"NSE: {val_nse:.4f} (H+6:{val_metrics['NSE_H6']:.4f}, H+12:{val_metrics['NSE_H12']:.4f}, H+24:{val_metrics['NSE_H24']:.4f}) | "
            f"RMSE: {val_metrics['RMSE']:.3f}m | "
            f"MAE: {val_mae:.4f}m | "
            f"KGE: {val_metrics['KGE']:.4f} | "
            f"PBIAS: {val_metrics['PBIAS']:.2f}% | "
            f"LR: {cur_lr:.2e} | "
            f"{elapsed:.1f}s"
        )

        # ── Early stopping (MAE-based) ─────────────────────────────────────
        if np.isfinite(val_mae) and val_mae < best_val_mae - min_delta:
            best_val_mae = val_mae
            patience_ctr = 0
            save_checkpoint(model, optimizer, scheduler, epoch, val_metrics,
                            config["model"], best_ckpt)
            ckpt_saved = 1
            logger.info(
                f"  -> New best MAE: {best_val_mae:.4f} m  "
                f"(persistence gap: {best_val_mae - 0.170:.4f} m)  "
                f"(saved to {best_ckpt.name})"
            )
        else:
            patience_ctr += 1
            if patience_ctr >= patience:
                logger.info(
                    f"Early stopping triggered at epoch {epoch}. "
                    f"Best val MAE = {best_val_mae:.4f} m"
                )
                break

        row = {
            "epoch":      epoch,
            "train_loss": round(train_loss, 6),
            "val_loss":   round(val_metrics["loss"], 6),
            "val_NSE":    round(val_nse, 6) if np.isfinite(val_nse) else "",
            "val_KGE":    round(val_metrics["KGE"], 6),
            "val_RMSE":   round(val_metrics["RMSE"], 4),
            "val_MAE":    round(val_mae, 4),
            "val_PBIAS":  round(val_metrics["PBIAS"], 4),
            "lr":         cur_lr,
            "duration_s": round(elapsed, 2),
            "ckpt_saved": ckpt_saved,
        }
        with open(log_path, "a", newline="") as fh:
            csv.DictWriter(fh, fieldnames=LOG_COLS).writerow(row)

        # ── Save last checkpoint (always) ────────────────────────────────
        save_checkpoint(model, optimizer, scheduler, epoch, val_metrics,
                        config["model"], last_ckpt)

        # Periodic epoch checkpoints
        if epoch % 10 == 0:
            ep_ckpt = ckpt_dir / f"epoch_{epoch:04d}.pt"
            save_checkpoint(model, optimizer, scheduler, epoch, val_metrics,
                            config["model"], ep_ckpt)

    # ── Final report ──────────────────────────────────────────────────────
    log_separator(logger, "Training Complete")
    logger.info(f"Best validation MAE : {best_val_mae:.4f} m  "
                f"(persistence gap: {best_val_mae - 0.170:+.4f} m)")
    logger.info(f"Best model saved    : {best_ckpt}")
    logger.info(f"Training log        : {log_path}")
    logger.info("")
    logger.info("Next steps:")
    logger.info("  python pipeline/evaluate.py   — Evaluate on test set")
    logger.info("  python pipeline/export_model.py — Export to ONNX for inference")


if __name__ == "__main__":
    main()
