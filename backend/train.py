"""Command line entry point for training the evaluator-safe ForecastIQ artifact."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib

from .predict import canonicalize_frame, train_evaluator_model
from .utils import DEFAULT_MODEL_PATH, read_csv_folder


def train_and_save(data_path: str, model_path: str) -> dict:
    """Train the offline evaluator v3 model artifact from a CSV file or folder."""
    path = Path(data_path)
    raw = read_csv_folder(path if path.is_dir() else path.parent)
    if raw.empty:
        raise ValueError(f"No CSV data found at {data_path}")
    cleaned = canonicalize_frame(raw)
    if cleaned.frame.empty:
        raise ValueError("No valid rows after evaluator canonicalization")
    artifact = train_evaluator_model(cleaned.frame)
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)
    return artifact


def main() -> None:
    """Train the evaluator artifact used by run.sh and hidden scoring."""
    parser = argparse.ArgumentParser(description="Train and persist the ForecastIQ evaluator artifact.")
    parser.add_argument("--data-dir", default="data", help="Folder containing training CSV files")
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH), help="Output model pickle path")
    args = parser.parse_args()

    bundle = train_and_save(args.data_dir, args.model)
    print(
        f"Trained evaluator artifact v{bundle['artifact_version']} as {bundle['model_type']} "
        f"on {bundle['training_rows']} rows and {bundle['training_samples']} rolling samples. "
        f"Saved to {args.model}."
    )


if __name__ == "__main__":
    main()
