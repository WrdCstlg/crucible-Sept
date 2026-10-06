"""verify_all step 7 must catch tampering with the published study, not just pass on the untouched record.

Each check runs verify_study on a copy of the recorded study (never the original) in a fresh interpreter, so the
experiment/grade.py vs experiment/bizsla/grade.py module-name collision cannot leak in from other test modules.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "experiment" / "runs"
STUDIES = sorted(p for p in RUNS.glob("study_*") if (p / "summary.json").exists()
                 and not json.loads((p / "config.json").read_text(encoding="utf-8")).get("mock"))

pytestmark = pytest.mark.skipif(not STUDIES, reason="no published live study in experiment/runs")

PROBE = """
import sys
from pathlib import Path
sys.path.insert(0, r"{exp}")
import verify_all
sys.exit(0 if verify_all.verify_study(Path(r"{study}"), None, regrade=False) else 1)
"""


def _copy(tmp_path):
    src = STUDIES[-1]
    dst = tmp_path / src.name
    dst.mkdir()
    for name in ("config.json", "summary.json"):
        shutil.copy2(src / name, dst / name)
    for g in src.glob("*/grade.json"):
        (dst / g.parent.name).mkdir()
        shutil.copy2(g, dst / g.parent.name / "grade.json")
    return dst


def _verify(study):
    r = subprocess.run([sys.executable, "-c", PROBE.format(exp=ROOT / "experiment", study=study)],
                       capture_output=True, text=True, cwd=ROOT, timeout=300)
    return r.returncode, r.stdout + r.stderr


def _edit(path, fn):
    d = json.loads(path.read_text(encoding="utf-8"))
    fn(d)
    path.write_text(json.dumps(d), encoding="utf-8")


def test_untouched_record_verifies(tmp_path):
    code, out = _verify(_copy(tmp_path))
    assert code == 0, out
    assert out.count("[pass]") == 4 and "[FAIL]" not in out


def test_flipping_one_run_to_pass_is_caught(tmp_path):
    study = _copy(tmp_path)

    def flip(d):
        row = next(r for r in d["runs"] if not r["strict_pass"] and (study / r["run"] / "grade.json").exists())
        row["strict_pass"], row["cases_passed"] = True, 225
    _edit(study / "summary.json", flip)
    code, out = _verify(study)
    assert code == 1 and "summary rows match their grade.json" in out and "[FAIL]" in out


def test_editing_a_grade_file_is_caught(tmp_path):
    study = _copy(tmp_path)
    g = next(study.glob("*/grade.json"))
    _edit(g, lambda d: d.update(passed=d["passed"] - 1, strict_pass=False))
    code, out = _verify(study)
    assert code == 1, out


def test_editing_a_reported_p_value_is_caught(tmp_path):
    study = _copy(tmp_path)
    _edit(study / "summary.json", lambda d: d["analysis"]["H1_B_vs_C"].update(p_two_sided=0.01))
    code, out = _verify(study)
    assert code == 1 and "reproduces every recorded tally" in out


def test_a_different_preregistration_is_caught(tmp_path):
    study = _copy(tmp_path)
    _edit(study / "config.json", lambda d: d["prereg"].update(sha256="0" * 64))
    code, out = _verify(study)
    assert code == 1 and "pre-registration sha256" in out
