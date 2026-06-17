from __future__ import annotations

import argparse

from .data_preprocessing import validate_records
from .forecasting import train_model_bundle
from .utils import DEFAULT_MODEL_PATH, read_csv_folder


def main() -> None:
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

