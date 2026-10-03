"""Model training: splitting, imbalance handling, and run orchestration."""

from chopcast.training.baseline import BaselineRun, train_baseline
from chopcast.training.class_weights import (
    compute_class_weights,
    describe_imbalance,
    resolve_class_weight,
)
from chopcast.training.dataset import TrainingDataset, latest_dataset, load_dataset
from chopcast.training.split import Split, load_split, make_split, save_split

__all__ = [
    "BaselineRun",
    "Split",
    "TrainingDataset",
    "compute_class_weights",
    "describe_imbalance",
    "latest_dataset",
    "load_dataset",
    "load_split",
    "make_split",
    "resolve_class_weight",
    "save_split",
    "train_baseline",
]
