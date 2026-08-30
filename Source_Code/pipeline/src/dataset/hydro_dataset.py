"""
HydroGNN-Net PyTorch Geometric Dataset

Works with pre-built .pt files created by: python pipeline/create_dataset.py

Directory structure expected:
    {root}/splits/train.pt
    {root}/splits/val.pt
    {root}/splits/test.pt
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import torch
from torch_geometric.data import Data, InMemoryDataset

from src.utils.logger import get_logger

logger = get_logger(__name__)


class HydroGNNDataset(InMemoryDataset):
    """
    InMemoryDataset wrapper for HydroGNN-Net split files.

    Each split file contains a Python list of torch_geometric.data.Data objects,
    where each Data object represents one sliding-window sample:

        data.x          [N_nodes, T_lookback, F_features]  float32
        data.y          [N_nodes, H_horizons]               float32
        data.edge_index [2, E]                              long
        data.edge_attr  [E, 4]                              float32
        data.time_index scalar Unix timestamp               long
        data.mask       [N_nodes]                           bool (optional)

    Parameters
    ----------
    root  : Directory containing the 'splits/' subdirectory.
    split : One of 'train', 'val', 'test'.
    """

    VALID_SPLITS = ("train", "val", "test")

    def __init__(
        self,
        root:          str,
        split:         str = "train",
        transform=None,
        pre_transform=None,
    ) -> None:
        assert split in self.VALID_SPLITS, (
            f"split must be one of {self.VALID_SPLITS}, got '{split}'"
        )
        self.split = split
        super().__init__(root, transform, pre_transform)

        # Check candidate locations: root/split.pt, root/pytorch/split.pt, root/splits/split.pt
        candidate_paths = [
            Path(root) / f"{split}.pt",
            Path(root) / "pytorch" / f"{split}.pt",
            Path(root) / "splits" / f"{split}.pt",
        ]
        split_path = next((p for p in candidate_paths if p.exists()), candidate_paths[0])
        if not split_path.exists():
            raise FileNotFoundError(
                f"Dataset split file not found: {split_path}\n"
                "\n"
                "Run the dataset creation script first:\n"
                "    python pipeline/create_dataset.py\n"
                "\n"
                "This requires preprocessed data from:\n"
                "    python pipeline/download_all.py\n"
                "    python pipeline/preprocess.py\n"
            )

        logger.info(f"Loading {split} split from {split_path}…")
        data_list = torch.load(split_path, weights_only=False)

        if not isinstance(data_list, list) or len(data_list) == 0:
            raise ValueError(
                f"{split}.pt appears empty or corrupt. "
                "Re-run: python pipeline/create_dataset.py"
            )

        # In-memory conversion from dicts to PyG Data objects with physical validity masking & delta targets
        if isinstance(data_list[0], dict):
            N = len(data_list)
            data_objects = []
            n_orig_valid = 0
            n_phys_valid = 0

            all_y = torch.stack([s["y"] for s in data_list])       # [N, 8, 3]
            all_m = torch.stack([s["y_mask"].bool() for s in data_list]) # [N, 8, 3]

            # In-memory physical validity mask
            ceilings = torch.tensor([15.0, 40.0, 15.0, 15.0, 15.0, 15.0, 15.0, 15.0], dtype=all_y.dtype).unsqueeze(1)
            y_phys_valid = torch.isfinite(all_y) & (all_y >= -2.0) & (all_y <= ceilings)
            combined_mask = all_m & y_phys_valid

            # Compute current stage y(t) from lag -6h (horizon H+6)
            y_curr = torch.zeros((N, 8), dtype=all_y.dtype)
            y_curr_mask = torch.zeros((N, 8), dtype=torch.bool)
            for i in range(N):
                if i >= 6:
                    y_curr[i] = all_y[i-6, :, 0]
                    y_curr_mask[i] = combined_mask[i-6, :, 0]
                else:
                    y_curr[i] = all_y[0, :, 0]
                    y_curr_mask[i] = combined_mask[0, :, 0]

            y_curr_phys = torch.isfinite(y_curr) & (y_curr >= -2.0) & (y_curr <= ceilings.squeeze(1))
            delta_y = all_y - y_curr.unsqueeze(-1)
            delta_mask = combined_mask & y_curr_mask.unsqueeze(-1) & y_curr_phys.unsqueeze(-1)

            n_orig_valid = int(all_m.sum())
            n_phys_valid = int(combined_mask.sum())
            n_delta_valid = int(delta_mask.sum())

            for i, s in enumerate(data_list):
                d = Data(
                    x=s.get("x_seq", s.get("x")),
                    x_curr=s.get("x"),
                    edge_index=s["edge_index"],
                    edge_attr=s["edge_attr"],
                    y=s["y"],
                    mask=combined_mask[i],
                    y_curr=y_curr[i],
                    delta_y=delta_y[i],
                    delta_mask=delta_mask[i],
                    timestamp=s.get("timestamp"),
                    stations=s.get("stations"),
                )
                data_objects.append(d)

            data_list = data_objects
            logger.info(
                f"{split.upper()} mask audit: {n_orig_valid:,} raw valid -> "
                f"{n_phys_valid:,} physically valid -> {n_delta_valid:,} delta valid targets"
            )

        self.data, self.slices = self.collate(data_list)
        logger.info(f"Loaded {len(data_list)} {split} samples")

    def _download(self):
        pass

    def _process(self):
        pass

    @property
    def raw_file_names(self):
        return []

    @property
    def processed_file_names(self):
        return []

    def download(self) -> None:
        pass

    def process(self) -> None:
        pass

    def len(self) -> int:
        if self.slices is None:
            return 0
        # InMemoryDataset: number of graphs = len of any slice tensor - 1
        first_key = next(iter(self.slices))
        return int(self.slices[first_key].numel()) - 1

    # get() is intentionally not overridden — InMemoryDataset.get() is inherited.
    # Overriding with a simple super() call is dead code.

    def __repr__(self) -> str:
        return f"HydroGNNDataset(split={self.split}, n={len(self)})"
