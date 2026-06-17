from __future__ import annotations

import argparse

from .data_preprocessing import validate_records
from .forecasting import aggregate_prediction_rows, load_model_bundle, train_model_bundle
from .utils import DEFAULT_MODEL_PATH, read_csv_folder, write_prediction_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ForecastIQ predictions for the hackathon scorer.")
    parser.add_argument("--data-dir", default="data", help="Folder containing input CSV files")
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH), help="Pickled model bundle path")
    parser.add_argument("--output", default="output/predictions.csv", help="Output predictions CSV path")
    args = parser.parse_args()

    raw = read_csv_folder(args.data_dir)
    frame, validation = validate_records(raw.to_dict(orient="records"))
    if frame.empty:
        raise SystemExit("No valid rows after validation; cannot generate predictions.")

    bundle = load_model_bundle(args.model)
    if bundle is None:
        bundle = train_model_bundle(frame, args.model)

    rows = aggregate_prediction_rows(frame, model_bundle=bundle)
    write_prediction_rows(rows, args.output)
    print(
        f"Wrote {len(rows)} prediction rows to {args.output}. "
        f"Valid rows: {validation.validRows}; validation issues: {len(validation.issues)}."
    )


if __name__ == "__main__":
    main()

