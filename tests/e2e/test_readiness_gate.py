"""E2E for the submission readiness gate (``scripts/readiness.py``).

The gate is machine-checkable evidence of submission completeness, so it must
itself be tested. This drives the gate *as CI drives it* — a **subprocess**
(`python scripts/readiness.py`) — for two reasons:

  * it exercises the real CLI/exit-code contract the ``readiness`` CI job depends
    on (offline automatable-% must be >= 95 → exit 0);
  * the gate reloads ``cinemory.api`` under ``CINEMORY_MODE=live`` to prove the
    never-500 degrade path; running it out-of-process guarantees that module
    reload can never leak degraded wiring into the rest of the test session.

The gate writes ``readiness.json`` to a tmp path here (never the repo tree), and
we assert the schema, the four criteria, per-criterion truth, and the user-gated
list so a regression in the report shape is caught.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "readiness.py"

_EXPECTED_CRITERIA = {
    "utility": "Real-World Utility",
    "production": "Production Readiness",
    "b2": "B2 Storage & Orchestration",
    "genblaze": "Use of Genblaze",
}


@pytest.fixture(scope="module")
def gate_run(tmp_path_factory):
    """Run the gate once (subprocess) and return (returncode, report dict)."""
    out = tmp_path_factory.mktemp("readiness") / "readiness.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--json", str(out), "--min", "95"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=300,
    )
    assert out.is_file(), f"gate did not emit readiness.json\nstderr:\n{proc.stderr}"
    report = json.loads(out.read_text(encoding="utf-8"))
    return proc.returncode, report


def test_gate_passes_offline_at_or_above_threshold(gate_run):
    returncode, report = gate_run
    # Offline, every automatable check must pass → gate exits 0.
    assert report["automatable_pct"] >= 95.0, report
    assert returncode == 0, f"gate exited {returncode} at {report['automatable_pct']}%"


def test_report_schema_and_all_four_criteria(gate_run):
    _, report = gate_run
    assert report["schema"] == "cinemory/readiness/v1"
    assert report["target_pct"] == 90
    assert "generated_at" in report and report["challenge"]
    got = {c["id"]: c["label"] for c in report["criteria"]}
    assert got == _EXPECTED_CRITERIA


def test_every_automatable_check_passed(gate_run):
    _, report = gate_run
    failing = [
        c["id"]
        for crit in report["criteria"]
        for c in crit["checks"]
        if c["automatable"] and c["status"] != "pass"
    ]
    assert not failing, f"automatable checks not passing: {failing}"


def test_each_criterion_reports_automatable_full_true(gate_run):
    _, report = gate_run
    for crit in report["criteria"]:
        # Offline: automatable fraction is fully satisfied for every criterion.
        assert crit["automatable_pct"] == 100.0, crit
        # The keystone evidence checks are present and real (not file-existence).
        assert any(c["status"] == "pass" for c in crit["checks"]), crit


def test_user_gated_items_are_the_three_live_credential_lifts(gate_run):
    _, report = gate_run
    gated = {g["id"] for g in report["user_gated"]}
    assert gated == {
        "production.live_redeploy",
        "b2.live_objects_written",
        "genblaze.live_reel_generated",
    }, gated
    # Every user-gated item states a concrete, credential-bound action.
    for g in report["user_gated"]:
        assert g["action"] and ("key" in g["action"].lower() or "creds" in g["action"].lower())
    # Full completeness discounts the still-pending user-gated lifts.
    assert report["full_pct_user_gated_pending"] < report["automatable_pct"]


def test_utility_check_covers_the_multipart_pipeline_provenance_path(gate_run):
    _, report = gate_run
    utility = next(c for c in report["criteria"] if c["id"] == "utility")
    ids = {c["id"] for c in utility["checks"]}
    assert "utility.upload_multipart_e2e" in ids
