# 路由索引（按症状找文档）

> 这是 v3 的常驻入口。`SKILL.md` 只留红线与推进方式（8 条），长文一律按需取：
> **目录进上下文（便宜），正文按需拉（贵）**。在 Mira 的逆向样本里，每次会话开头读一份
> 3 KB 的索引就把 7 个技能的触发条件装进了上下文，正文（几十 KB）只在真要动手时读一次。
>
> 与 Mira 的差别：Mira 把 `list_skills` 写成硬约束（"skipping it is a critical failure"），
> 而实测两次读 `playbook_index.md` 是 2 KB 开销换 0 收益。所以本索引**不是硬约束**，
> 硬约束只有 `SKILL.md` §1 的八条红线与其执法脚本。

## 格式约定

每项三字段（照抄 Mira `playbook_index.md` 的形状，`description` 写触发条件 + 分流 + 排除）：

```text
- topic: <短名>
- description: <何时该读；触发词；不要用于什么>
- path: references/<file>#<anchor>
```

## 索引

- topic: route-and-oracle
- description: 该走 Route A 还是 B、`code_absence_check` 记什么、资格闸门 G1/G2 怎么判、官方发布数据的最小可对拍量（`check_official_smoke.py`）。触发：`check_route.py` / `check_official_smoke.py` 报错、论文既有代码又没代码。排除：具体数值指标定义。
- path: references/protocol.md#复现路线

- topic: numeric-protocol
- description: `loss` 配置的全部字段、`rms_norm`/`scale`/`max_gap`/`peak` 语义、NPZ/CSV 的 units 与 roles、digitize 的 excluded_x。触发：`check_loss.py`/`check_feature_resolution.py` 报错、写新的目标配置。排除：图面审美。
- path: references/protocol.md#数值协议

- topic: calibration-and-effect
- description: 解析极限/守恒关系/论文标定值的断言写法，`not_applicable` 的正当理由，效应量先验。触发：`check_calibration.py`、`check_effect.py` 报错。排除：论文侧锚点预注册（见 anchors）。
- path: references/protocol.md#标定与效应

- topic: anchors-preregistration
- description: 首跑前把论文侧数值（平台值、峰位、带隙）登记成可判定锚点，哈希绑定与修正流程。触发：scaffold 之后、任何 `record_run.py` 之前；`check_anchors.py` 报 sha256 mismatch。排除：代码自洽性断言。
- path: references/protocol.md#预注册锚点

- topic: compute-budget
- description: 算力估算、出路清单、分块与 resume、ETA 只能来自 `runs/*/manifest.json` 的实测。触发：扫描 >30 min、`check_budget.py` 报错、工具超时文案与实测不符。排除：环境版本钉住。
- path: references/protocol.md#算力预算

- topic: artifacts-ledger
- description: `record_artifact.py` 与 `artifacts.jsonl` 的用法（sha256 去重、supersede 边、评审包时间线）。触发：产出中间图/表/日志、要交评审包。排除：跑批元数据（用 `record_run.py`）。
- path: references/protocol.md#产物台账

- topic: image-protocol
- description: `vision.py` 的 describe/audit/judge/critique、裁剪哈希绑定、模型读数为何不是真值、左右并排而非叠加、裁切锚点（`check_crop_anchors.py`）与整图叠置（`check_figure_overlay.py`）的分工。触发：从 PDF 取子图、`check_visual_crop.py` / `check_crop_anchors.py` / `check_figure_overlay.py` 报错、图面对不上。排除：数值对齐。
- path: references/protocol.md#图像协议

- topic: environment-and-runs
- description: `environment.json` 的 expected/runtime/run 三元绑定，`record_run.py` 的输入声明与失败记录，runtime.json 缺口自助产出。触发：`check_env.py`、`check_fix_log.py` 报错。排除：算力预算。
- path: references/protocol.md#环境与运行

- topic: provenance-and-uncertainty
- description: reference 的 kind 取值、uncertainty_basis、`used_for_tuning` 的非留出披露、official_comparison 的绑定要求。触发：`check_independence.py`、`check_route.py` 报错。排除：决策台账。
- path: references/protocol.md#来源和归因

- topic: autonomous-round
- description: 一轮到底的推进纪律、决策台账字段与取值、升级条件 E1–E5、评审包与报告的生成顺序。触发：每轮开始、遇到歧义、`check_decisions.py` 报错。排除：论文物理。
- path: references/protocol.md#自主复现轮与决策台账

- topic: report-template
- description: `REPORT.md` 六节固定标题、判定词表、数字必须逐字取自 `reports/*.json`。触发：stage=final、`check_report.py` 报错。
- path: references/report_template.md

- topic: pitfalls
- description: 真实跑过的坑：复用 `sys_builder` 污染状态、`/R_K` 与阈值单位、crop 伪影被当成真缺陷、超时文案与实测 2× 差异。触发：结果"看起来对但差 5%"、准备调参之前。
- path: references/pitfalls.md

- topic: domain-packs
- description: L1 通用包（`references/domains/*.md`）与 L2 实例档案（`spec/domain_profile.md`）的分工、包哈希钉住、锚点行必填定位（`check_profile_anchors.py`）、晋升候选。触发：选 domain、`check_domain_profile.py` / `check_profile_anchors.py` 报错。
- path: references/protocol.md#领域包与实例化层l1-通用--l2-个性化

- topic: legacy-skill-v2.8
- description: v2.8 的完整 SKILL 正文（354 行，含逐节说明与历史理由）。触发：本索引查不到、要追溯 v3 之前的措辞。排除：日常执行（用 `SKILL.md` + `next.py`）。
- path: references/archive/skill-v2.8.md
