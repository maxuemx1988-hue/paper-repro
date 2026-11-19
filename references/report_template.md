# 复现报告

> 复制到项目根 `REPORT.md` 后填写。检查脚本：`scripts/check_report.py`（仅 `stage=final`）。
> 本报告是**交付物**，不是验收替代品：脚本只校验结构与证据绑定（判定必须引用真实评分报告里的数字），
> 科学结论必须由人复核。数值一律来自 `reports/*.json`，不得手写。

## 0. 结论摘要

⟪一句话结论：哪个/哪些观测量被定量复现到什么程度，哪些没有。点名验证对象（paper_result / author_implementation / benchmark）与复现模式。⟫

## 1. 逐目标结果

判定取值只能是 `定量符合`／`定性一致`／`未达标`／`未完成`。`定量符合`／`定性一致` 的指标列必须写出
与证据列评分报告里一致的数值（检查器会逐字比对，容差 1e-6），判定为 PASS 的目标其评分报告状态必须是 PASS。
不在本表出现的声明一律视为未申报。

| 目标 | 判定 | 指标 | 说明 | 证据 |
|---|---|---|---|---|
| ⟪fig1⟫ | ⟪定量符合⟫ | ⟪rms_norm=0.0⟫ | ⟪一句话解释该目标的物理含义与残差来源⟫ | ⟪reports/fig1.json⟫ |

## 2. 门禁与证据

逐项列出实际运行过的检查脚本与结果（不是"应当通过"，而是本次运行的结论）。至少三个 `check_*.py`。

| 检查 | 命令 | 结果 | 备注 |
|---|---|---|---|
| ⟪check_spec.py⟫ | ⟪python3 scripts/check_spec.py .⟫ | ⟪PASS⟫ | ⟪...⟫ |

记录绑定运行：⟪`runs/<ID>/manifest.json` 及其哈希；说明该运行产生哪些证据文件⟫。
若存在 `paper_figure` 非空的目标（数值计算在论文中有图），本节必须记录 `figures/compare/*_side_by_side.png` 左右并排对比产物及其复核；
若用过 `vision.py`，同时列出 `figures/compare/*.vision_judge.json` 与 `*.visual_audit.json` 的模型与哈希。

## 3. 局限与未完成项

必须逐条写清楚，不允许留空、不允许把待办写成进展。

- **复现路线**：本次走 Route A（有官方代码）还是 Route B（无官方代码、以论文真值为预言机），依据是什么（`provenance.route`）。
- ⟪未留出验证的参考、被调参影响的约定、采样密度不足、被移除的目标及其原因、阶段状态⟫
- ⟪若跑过 `vision.py judge`：哪些目标视觉判定为 partial/disagree、具体差异是什么⟫

若 `spec/decisions.json` 存在 `status=escalated` 的决策，本条必须逐条点名其 id（例如 `D2`），
写明选择题与影响——自主流程不得把待人工裁决的问题埋在交付物里。待裁决清单另见 `REVIEW.md`。

## 4. 复现方法

给出可重跑的最小步骤（含命令），以及环境钉住项与关键数值旋钮。

```bash
⟪python3 code/run_xxx.py --config spec/xxx.json⟫
```

## 5. 参考来源与调参披露

写明 `reproduction_mode`（paper / independent / author），逐条列出参考的 `kind`（paper / supplement /
published_data / author_material / analytic / database / digitized / official_comparison）、定位与不确定度。
若存在 `used_for_tuning=true` 的参考，必须在此声明"非留出验证"及其影响范围。
若参考为 `digitized`，必须说明为何没有可用数值来源（回退理由）与数字化误差估计。
