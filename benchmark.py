#!/usr/bin/env python3
"""Reproducible LightGBM benchmark for the Kaggle credit-card fraud dataset."""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split


DEFAULT_DATASET = Path.home() / "ml-benchmark" / "creditcard.csv"
DEFAULT_RESULT = Path(__file__).resolve().with_name("benchmark_result.json")
DEFAULT_REPORT = Path(__file__).resolve().with_name("benchmark_report.md")
SEED = 42


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train and benchmark LightGBM on creditcard.csv."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help=f"Path to creditcard.csv (default: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULT,
        help=f"Result JSON path (default: {DEFAULT_RESULT})",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"Short Markdown report path (default: {DEFAULT_REPORT})",
    )
    return parser.parse_args()


def timed_predict_proba(
    model: lgb.LGBMClassifier, rows: pd.DataFrame, repeats: int
) -> list[float]:
    durations: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        model.predict_proba(rows, num_iteration=model.best_iteration_)
        durations.append(time.perf_counter() - started)
    return durations


def main() -> int:
    args = parse_args()
    dataset_path = args.dataset.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    report_path = args.report.expanduser().resolve()

    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"Dataset not found: {dataset_path}. Download and unzip "
            "mlg-ulb/creditcardfraud first."
        )

    print(f"Dataset: {dataset_path.name}", flush=True)
    print("Loading data...", flush=True)
    load_started = time.perf_counter()
    frame = pd.read_csv(dataset_path)
    load_time_seconds = time.perf_counter() - load_started

    required_columns = {"Class"}
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"Dataset is missing columns: {sorted(missing_columns)}")
    if len(frame) < 1_000:
        raise ValueError("Dataset must contain at least 1,000 rows for throughput testing.")

    features = frame.drop(columns="Class")
    labels = frame["Class"].astype(int)
    class_counts = labels.value_counts().sort_index()
    if labels.nunique() != 2:
        raise ValueError("Class must contain exactly two classes.")

    x_train_full, x_test, y_train_full, y_test = train_test_split(
        features,
        labels,
        test_size=0.20,
        random_state=SEED,
        stratify=labels,
    )
    x_train, x_validation, y_train, y_validation = train_test_split(
        x_train_full,
        y_train_full,
        test_size=0.20,
        random_state=SEED,
        stratify=y_train_full,
    )

    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=1_000,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.80,
        colsample_bytree=0.80,
        class_weight="balanced",
        random_state=SEED,
        n_jobs=-1,
        verbosity=-1,
    )

    print(
        f"Rows: {len(frame):,} | features: {features.shape[1]} | "
        f"fraud rows: {int(class_counts.get(1, 0)):,}",
        flush=True,
    )
    print("Training LightGBM...", flush=True)
    training_started = time.perf_counter()
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="The argument 'eval_set' is deprecated.*"
        )
        model.fit(
            x_train,
            y_train,
            eval_set=[(x_validation, y_validation)],
            eval_metric="auc",
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
    training_time_seconds = time.perf_counter() - training_started

    probabilities = model.predict_proba(
        x_test, num_iteration=model.best_iteration_
    )[:, 1]
    predictions = (probabilities >= 0.5).astype(int)

    # Warm up the prediction path before measuring latency and throughput.
    model.predict_proba(x_test.iloc[:1], num_iteration=model.best_iteration_)
    one_row_durations = timed_predict_proba(model, x_test.iloc[:1], repeats=100)
    batch_rows = features.iloc[:1_000]
    batch_durations = timed_predict_proba(model, batch_rows, repeats=10)
    batch_median_seconds = statistics.median(batch_durations)

    result = {
        "dataset": {
            "file_name": dataset_path.name,
            "rows": int(len(frame)),
            "features": int(features.shape[1]),
            "class_counts": {str(key): int(value) for key, value in class_counts.items()},
            "train_rows": int(len(x_train)),
            "validation_rows": int(len(x_validation)),
            "test_rows": int(len(x_test)),
        },
        "configuration": {
            "seed": SEED,
            "test_fraction": 0.20,
            "validation_fraction_of_training_data": 0.20,
            "classification_threshold": 0.5,
            "model": "lightgbm.LGBMClassifier",
        },
        "timings": {
            "load_time_seconds": round(load_time_seconds, 6),
            "training_time_seconds": round(training_time_seconds, 6),
            "inference_latency_1_row_median_ms": round(
                statistics.median(one_row_durations) * 1_000, 6
            ),
            "inference_latency_1_row_p95_ms": round(
                float(np.percentile(one_row_durations, 95)) * 1_000, 6
            ),
            "inference_batch_1000_rows_median_seconds": round(
                batch_median_seconds, 6
            ),
            "inference_throughput_1000_rows_per_second": round(
                len(batch_rows) / batch_median_seconds, 3
            ),
        },
        "metrics": {
            "auc_roc": round(float(roc_auc_score(y_test, probabilities)), 8),
            "accuracy": round(float(accuracy_score(y_test, predictions)), 8),
            "f1": round(float(f1_score(y_test, predictions, zero_division=0)), 8),
            "precision": round(
                float(precision_score(y_test, predictions, zero_division=0)), 8
            ),
            "recall": round(
                float(recall_score(y_test, predictions, zero_division=0)), 8
            ),
        },
        "model": {
            "best_iteration": int(model.best_iteration_),
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "logical_cpu_count": os.cpu_count(),
            "lightgbm": lgb.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    report_lines = [
        "# Báo cáo benchmark LightGBM trên CPU",
        "",
        f"- Dataset gồm {len(frame):,} dòng, {features.shape[1]} features và "
        f"{int(class_counts.get(1, 0)):,} giao dịch gian lận.",
        f"- Thời gian load dữ liệu là {load_time_seconds:.3f} giây; thời gian "
        f"training là {training_time_seconds:.3f} giây với best iteration "
        f"{int(model.best_iteration_)}.",
        f"- AUC-ROC đạt {result['metrics']['auc_roc']:.6f} và Accuracy đạt "
        f"{result['metrics']['accuracy']:.6f} trên tập test.",
        f"- F1 đạt {result['metrics']['f1']:.6f}, Precision đạt "
        f"{result['metrics']['precision']:.6f} và Recall đạt "
        f"{result['metrics']['recall']:.6f}.",
        f"- Latency dự đoán một dòng (median) là "
        f"{result['timings']['inference_latency_1_row_median_ms']:.3f} ms; "
        f"p95 là {result['timings']['inference_latency_1_row_p95_ms']:.3f} ms.",
        f"- Batch 1.000 dòng mất median "
        f"{result['timings']['inference_batch_1000_rows_median_seconds']:.6f} "
        "giây.",
        f"- Throughput inference đạt "
        f"{result['timings']['inference_throughput_1000_rows_per_second']:.3f} "
        "dòng/giây trên môi trường CPU đã ghi trong JSON.",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("\nBenchmark result", flush=True)
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    print(f"\nSaved: {output_path.name}", flush=True)
    print(f"Saved: {report_path.name}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
