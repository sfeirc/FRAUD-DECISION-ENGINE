from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib

from fraud_engine import __version__
from fraud_engine.features import ONLINE_FEATURE_NAMES
from fraud_engine.graph import GRAPH_FEATURE_NAMES
from fraud_engine.service import FraudDecisionService

ARTIFACT_SCHEMA_VERSION = 1
DEFAULT_ARTIFACT_DIR = Path("artifacts/models/v0.3.0")


class ArtifactIntegrityError(RuntimeError):
    """Raised when a model bundle is missing, incompatible, or has been modified."""


def configured_artifact_dir() -> Path:
    return Path(os.environ.get("FRAUD_MODEL_DIR", DEFAULT_ARTIFACT_DIR))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def build_artifact(
    output_dir: Path,
    *,
    seed: int = 7,
    normal_events: int = 2_000,
    fraud_events_per_pattern: int = 25,
) -> dict[str, Any]:
    """Train once and atomically persist the exact runtime model bundle and provenance."""
    service = FraudDecisionService.train_default(
        seed=seed,
        normal_events=normal_events,
        fraud_events_per_pattern=fraud_events_per_pattern,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = output_dir / "bundle.joblib"
    payload = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "engine_version": __version__,
        "champion": service.champion,
        "challenger": service.challenger,
        "decision_engine": service.engine,
        "validation_records": service.validation_records,
    }
    with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".tmp", delete=False) as handle:
        temporary_path = Path(handle.name)
    try:
        joblib.dump(payload, temporary_path, compress=3)
        temporary_path.replace(bundle_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    manifest: dict[str, Any] = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "engine_version": __version__,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": _git_commit(),
        "bundle": {"filename": bundle_path.name, "sha256": _sha256(bundle_path)},
        "feature_contract": {
            "ordered_names": list(ONLINE_FEATURE_NAMES + GRAPH_FEATURE_NAMES),
            "sha256": hashlib.sha256(
                "\n".join(ONLINE_FEATURE_NAMES + GRAPH_FEATURE_NAMES).encode()
            ).hexdigest(),
        },
        "training": {
            "seed": seed,
            "normal_events": normal_events,
            "fraud_events_per_pattern": fraud_events_per_pattern,
            "validation_rows": len(service.validation_records),
        },
        "models": {
            "champion": asdict(service.champion.config),
            "challenger": asdict(service.challenger.config),
        },
        "decision_policy": {
            "assumptions": asdict(service.engine.assumptions),
            "thresholds": asdict(service.engine.thresholds),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {
                name: _package_version(name)
                for name in ("joblib", "numpy", "scikit-learn", "xgboost")
            },
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_artifact(artifact_dir: Path | None = None) -> FraudDecisionService:
    """Load a model bundle only after validating its manifest, checksum, and feature order."""
    selected = artifact_dir or configured_artifact_dir()
    manifest_path = selected / "manifest.json"
    if not manifest_path.is_file():
        raise ArtifactIntegrityError(
            f"model manifest not found at {manifest_path}; run `make artifacts`"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactIntegrityError("unsupported model artifact schema")
    expected_features = list(ONLINE_FEATURE_NAMES + GRAPH_FEATURE_NAMES)
    if manifest.get("feature_contract", {}).get("ordered_names") != expected_features:
        raise ArtifactIntegrityError("model feature contract does not match runtime feature order")
    bundle_path = selected / str(manifest.get("bundle", {}).get("filename", ""))
    if not bundle_path.is_file():
        raise ArtifactIntegrityError(f"model bundle not found at {bundle_path}")
    expected_checksum = manifest.get("bundle", {}).get("sha256")
    if not expected_checksum or _sha256(bundle_path) != expected_checksum:
        raise ArtifactIntegrityError("model bundle checksum mismatch")
    payload = joblib.load(bundle_path)
    if (
        not isinstance(payload, dict)
        or payload.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
    ):
        raise ArtifactIntegrityError("invalid model bundle payload")
    required = {"champion", "challenger", "decision_engine", "validation_records"}
    if not required.issubset(payload):
        raise ArtifactIntegrityError("model bundle is missing required runtime objects")
    return FraudDecisionService(
        payload["champion"],
        payload["challenger"],
        payload["decision_engine"],
        payload["validation_records"],
        artifact_manifest=manifest,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a versioned fraud-model artifact")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--normal-events", type=int, default=2_000)
    parser.add_argument("--fraud-events-per-pattern", type=int, default=25)
    args = parser.parse_args()
    manifest = build_artifact(
        args.output_dir,
        seed=args.seed,
        normal_events=args.normal_events,
        fraud_events_per_pattern=args.fraud_events_per_pattern,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
