import json
from pathlib import Path

import pytest

from fraud_engine.artifacts import ArtifactIntegrityError, build_artifact, load_artifact


@pytest.fixture(scope="module")
def artifact_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    selected = tmp_path_factory.mktemp("model-artifact")
    build_artifact(
        selected,
        seed=31,
        normal_events=180,
        fraud_events_per_pattern=4,
    )
    return selected


def test_artifact_round_trip_preserves_policy_and_models(artifact_dir: Path) -> None:
    service = load_artifact(artifact_dir)
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert service.champion.config.version == manifest["models"]["champion"]["version"]
    assert service.challenger.config.version == manifest["models"]["challenger"]["version"]
    assert service.engine.thresholds.review == manifest["decision_policy"]["thresholds"]["review"]
    assert service.health()["artifact"]["source_commit"] == manifest["source_commit"]  # type: ignore[index]


def test_artifact_tampering_is_rejected(artifact_dir: Path, tmp_path: Path) -> None:
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["bundle"]["sha256"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "bundle.joblib").write_bytes((artifact_dir / "bundle.joblib").read_bytes())
    with pytest.raises(ArtifactIntegrityError, match="checksum"):
        load_artifact(tmp_path)


def test_missing_artifact_has_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(ArtifactIntegrityError, match="make artifacts"):
        load_artifact(tmp_path)
