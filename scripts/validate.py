#!/usr/bin/env python3
"""Execute applicable checks from project config; checks are evidence, not a scientific verdict."""
import argparse
from pathlib import Path
import subprocess
import sys
from common import finish, project, run


def commands(root):
    """The ordered, stage-applicable check list. Shared with next.py so the two never drift."""
    doc = project(root)
    commands = [("check_spec.py", []), ("check_domain_profile.py", []),
                ("check_profile_anchors.py", [])]
    if doc["stage"] != "planning":
        commands += [("check_official_smoke.py", []), ("check_route.py", []), ("check_physics_code.py", []),
                     ("check_fix_log.py", []), ("check_calibration.py", []), ("check_anchors.py", []),
                     ("check_budget.py", []), ("check_env.py", []), ("check_hypotheses.py", []),
                     ("check_decisions.py", [])]
    if doc["stage"] == "final":
        commands.append(("check_independence.py", []))
    for item in doc["targets"] if doc["stage"] != "planning" else []:
        tid = item["id"]
        if item["checks"]["effect"]["enabled"]:
            commands.append(("check_effect.py", [tid]))
        if doc["stage"] == "final":
            # absolute: check_loss resolves --report against the cwd, not the project
            report = str(Path(root).resolve() / "reports" / f"{tid}.json")
            commands.append(("check_loss.py", [tid, "--report", report]))
            commands.append(("check_feature_resolution.py", [tid]))
            if item["checks"]["visual"]["enabled"]:
                commands.append(("check_figure_validity.py", [tid]))
    if doc["stage"] == "final":
        # generate the human review packet, then check it is fresh; the report
        # must echo every escalated decision, so both run before check_report
        commands.append(("make_review.py", []))
        commands.append(("check_review.py", []))
        # last: the report quotes numbers from the reports/ files written above
        commands.append(("check_report.py", []))
    return doc, commands


def check(root):
    scripts = Path(__file__).resolve().parent
    doc, steps = commands(root)
    codes = []
    for script, args in steps:
        print(f"\n>>> {script} {' '.join(args)}", flush=True)
        try:
            result = subprocess.run([sys.executable, str(scripts / script), str(root), *args], timeout=120)
            codes.append(result.returncode)
        except subprocess.TimeoutExpired:
            codes.append(2)
            print("[INCOMPLETE] check timed out")
    status = "FAIL" if 1 in codes else "INCOMPLETE" if any(c != 0 for c in codes) else "PASS"
    return finish(status, "applicable checks completed; scientific verdict needs per-target review")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
