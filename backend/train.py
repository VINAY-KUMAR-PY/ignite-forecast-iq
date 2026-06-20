"""Command line entry point for training the ForecastIQ model bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib

from .data_preprocessing import validate_records
from .forecasting import train_model_bundle
from .predict import canonicalize_frame, train_evaluator_model
from .utils import DEFAULT_MODEL_PATH, read_csv_folder


def train_and_save(csv_path: str, model_path: str) -> dict:
    """Train the offline evaluator v3 model artifact from one CSV file."""
    raw = read_csv_folder(Path(csv_path).parent)
    if raw.empty:
        raise ValueError(f"No CSV data found at {csv_path}")
    cleaned = canonicalize_frame(raw)
    if cleaned.frame.empty:
        raise ValueError("No valid rows after evaluator canonicalization")
    artifact = train_evaluator_model(cleaned.frame)
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)
    return artifact


def main() -> None:
    """Train revenue and ROAS models from CSV input."""
    parser = argparse.ArgumentParser(description="Train and persist the ForecastIQ model bundle.")
    parser.add_argument("--data-dir", default="data", help="Folder containing training CSV files")
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH), help="Output model pickle path")
    args = parser.parse_args()

    raw = read_csv_folder(args.data_dir)
    frame, validation = validate_records(raw.to_dict(orient="records"))
    if frame.empty:
        raise SystemExit("No valid rows after validation; cannot train model.")

    bundle = train_model_bundle(frame, args.model)
    print(
        f"Trained {bundle['model_type']} model on {validation.validRows} valid rows "
        f"({len(validation.issues)} validation issues). Saved to {args.model}."
    )


if __name__ == "__main__":
    main()
