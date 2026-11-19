#!/usr/bin/env python3
"""Tell the agent the single next thing to do, instead of a wall of PASS/FAIL.

`validate.py` answers "is this workspace acceptable yet?".  That is the wrong
question during an autonomous run: the model then has to re-read prose to work out
which of thirty gates it should attack next, and re-derives the order differently
every turn (the churn Mira's session log shows as 3-5 revisions of the same size
decision).

`next.py` runs the same stage-applicable pipeline as validate.py, stops at the
first gate that is not satisfied, and prints exactly two things:

    BLOCKED_BY: check_calibration.py
    NEXT: python3 scripts/check_calibration.py /path/to/paper

`--why` adds the protocol anchor that explains the gate (so the long-form prose
stays in references/ and is pulled on demand, not carried in context).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from common import finish, project, run
from validate import commands
from common import Incomplete

WHY = {
    "check_spec.py": "拓扑/能量对齐/缺陷要素必须先冻结：references/protocol.md#spec",
    "check_domain_profile.py": "领域包实例化（L1 包哈希 + §0–§7）：references/protocol.md#领域包",
    "check_profile_anchors.py": "领域锚点行必须有定位或理由：references/protocol.md#领域包",
    "check_official_smoke.py": "有官方发布数据就先冒烟（最小可对拍量）：references/protocol.md#复现路线",
    "check_route.py": "路线声明与证据一致（A/B、code_absence_check、替代预言机）：references/protocol.md#复现路线",
    "check_physics_code.py": "AST 诚信审计：禁止解析拟合冒客观测量：SKILL.md 红线 2",
    "check_fix_log.py": "纠错台账必须真实：references/protocol.md#来源和归因",
    "check_calibration.py": "解析极限/守恒关系标定：references/protocol.md#标定与效应",
    "check_anchors.py": "论文侧数值必须首跑前预注册且哈希绑定：references/protocol.md#预注册锚点",
    "check_budget.py": "算力估算 + 实测吞吐闭环，ETA 只能来自 manifest：references/protocol.md#算力预算",
    "check_env.py": "环境钉住与运行绑定：references/protocol.md#环境与运行",
    "check_hypotheses.py": "偏差必须绑定可证伪假设：references/protocol.md#来源和归因",
    "check_decisions.py": "自主决策台账（选项/规则/可逆/置信）：references/protocol.md#自主复现轮与决策台账",
    "check_independence.py": "独立性与来源审计：references/protocol.md#来源和归因",
    "check_effect.py": "效应量先验：references/protocol.md#标定与效应",
    "check_loss.py": "数值对齐双指标：references/protocol.md#数值协议",
    "check_feature_resolution.py": "采样密度足以解析目标特征：references/protocol.md#数值协议",
    "check_figure_validity.py": "非空/非死线/可见比例：SKILL.md 红线 4",
    "make_review.py": "生成人工评审包：references/protocol.md#自主复现轮与决策台账",
    "check_review.py": "评审包不陈旧、不漏待裁决项",
    "check_report.py": "报告逐目标判定必须引用已落盘评分：references/report_template.md",
}


def step(root, script, args, timeout):
    """Run one gate; return (ok, status, detail)."""
    path = Path(__file__).resolve().parent / script
    try:
        result = subprocess.run([sys.executable, str(path), str(root), *args],
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT", f"{script} timed out"
    print(result.stdout, end="")
    return result.returncode == 0, ("OK" if result.returncode == 0 else "BLOCKED"), result.stdout.strip()


def check(root, why=False, as_json=False):
    try:
        doc, steps = commands(root)
    except Incomplete as exc:
        # spec/project.json itself is the first gate; say so instead of dying with a traceback
        print(f"[BLOCKED] {exc}")
        print("\nBLOCKED_BY: spec/project.json")
        print(f"NEXT: python3 scripts/check_spec.py {root}")
        if why:
            print("WHY: 项目拓扑未冻结（title/source/domain/targets）：references/protocol.md#spec")
        return finish("INCOMPLETE", str(exc))
    blocked = None
    for script, args in steps:
        ok, status, detail = step(root, script, args, timeout=120)
        step_doc = {"check": script, "args": args, "status": status, "detail": detail[-400:]}
        if not ok:
            blocked = (script, args)
            print(f"\nBLOCKED_BY: {script}")
            print(f"NEXT: python3 scripts/{script} {root} {' '.join(args)}".replace("  ", " "))
            if why:
                print(f"WHY: {WHY.get(script, '见 references/protocol.md')}")
            break
    if blocked is None:
        if doc["stage"] == "final":
            print("\nDONE: all applicable gates pass and stage=final; hand REVIEW.md to the human.")
        else:
            print(f"\nDONE for stage={doc['stage']}. To raise the bar, set stage to "
                  f"{'calibrated' if doc['stage'] == 'planning' else 'final'} in spec/project.json, "
                  "then re-run next.py.")
            print("NEXT: edit spec/project.json -> stage, then: python3 scripts/next.py " + str(root))
    if as_json:
        out = Path(root) / "reports/next.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"stage": doc["stage"],
                                   "blocked_by": blocked[0] if blocked else None,
                                   "steps": [s for s in steps]}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"[next] {out}")
    return finish("PASS" if blocked is None else "INCOMPLETE",
                  f"next step: {blocked[0]}" if blocked else "no blocking gate")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root")
    parser.add_argument("--why", action="store_true", help="打印该门禁对应的协议锚点")
    parser.add_argument("--json", action="store_true", help="把步骤清单写到 reports/next.json")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root, args.why, args.json)))
