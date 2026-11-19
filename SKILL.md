---
name: paper-repro
description: 复现数值物理论文的定量输出（曲线图/表格/文中数值断言）。当任务涉及"复现某篇论文的图或数据"、"从论文写代码并与原文对齐"、"Kwant/紧束缚/DFT/蒙特卡洛复现"、"结果和论文对不上要归因"时使用。有官方代码走 Route A（官方实现作指导教练），无官方代码走 Route B（以论文印刷数值 + 解析极限为预言机）；图像识别统一调 scripts/vision.py（kimi + 12ai OpenAI 兼容端点）。默认自主轮：模型一轮跑到出结果，遇歧义就决策—留痕—继续，只在触发升级条件时停下；收尾交复现报告与人工评审包。v3 起：`next.py` 给下一步，`anchors.json` 首跑前预注册论文侧数值，`budget.json` 管算力，`artifacts.jsonl` 边做边钉；从 `references/index.md` 按需取长文。
---

# 论文定量复现（v3）

目标：对论文发表结果做**高保真独立定量复现**，官方代码只是加速器。
有官方实现 → **Route A**（指导教练，禁抄源码）；无 → **Route B**（印刷数值 + 解析极限作预言机）。
两条路线验收标准相同，只降级可用预言机，不降级执法。

**推进方式**：不要通读本文再自己排步骤。跑 `python3 scripts/next.py <dir> --why`，
它给唯一一行 `NEXT:`；`validate.py` 只在升 stage 前做全量验收。

## 1. 八条红线（每条都有脚本执法，模型无权自行豁免）

1. **唯一实现由自研 Pipeline 产出**（禁复制官方源码；`reproduction_mode=author` 例外且须声明）→ `check_independence.py`
2. **禁代码造假**：观测量必须由数值求解器算出，禁解析拟合函数硬编码 → `check_physics_code.py`
3. **禁盲猜裁图/透明度叠加**：子图须多模态核验；对比必须左右并排 → `check_visual_crop.py`、`check_figure_side_by_side.py`
4. **禁死线与空图**：全 0 或全在画幅外直接拦截 → `check_figure_validity.py`
5. **量级级偏差禁调参**：先查约定与单位。Route A 派 `code-auditor`；Route B 走三步取证（解析极限对表 → 独立第二实现 → 收敛阶）→ `check_route.py`、`check_hypotheses.py`
6. **论文侧数值首跑前预注册**：平台值/峰位/带隙先写进 `spec/anchors.json`；首跑 `manifest.json` 会记录其 sha256，事后修改必须给判别实验 → `check_anchors.py`
7. **算力先估算、ETA 只认 manifest**：`>2 h` 的扫描必须有出路清单、分块与 resume；禁抄超时文案里的秒数（`after 1200 s` 常与实测差 2×）→ `check_budget.py`
8. **全程诚实留痕 + 判定不得手写**：失败/证伪/改动入 `LOG.md` 与 `hypotheses.json`（`[RETRACT:Hn]`）；`REPORT.md` 的数字必须逐字来自 `reports/*.json` → `check_decisions.py`、`check_report.py`

> 图的硬门槛：目标 `paper_figure` 非空 ⇒ 必须有 `figures/mine/<tid>.png` + `figures/compare/<tid>_side_by_side.png`，
> 数值真值来自表格也不能豁免。`paper_figure=null` 是"该计算在论文中无图"的声明，不实即来源造假 → `check_spec.py`、`check_independence.py`

## 2. 路线选择

路线由 `spec/project.json` 的 `official_code` 决定，`spec/provenance.json` 的 `route` 必须一致：

| | Route A | Route B |
|---|---|---|
| 预言机 | 官方实现（只读提炼拓扑/矩阵关系，**不给源码**） | 印刷数值 + 补充材料 + 解析极限 + `vision.py` 读数 |
| 硬要求 | `official_smoke` 冒烟记录 | `code_absence_check` + 至少一个印刷数值锚点 + `calibration.json` 一条 `limit`/`invariant` |
| 建模期 | 派 `code-oracle` 问结线拓扑与电导矩阵组装 | 派 `literature-oracle` 问标准构型与约定 |
| 归因 | 派 `code-auditor` | 解析定位三步（可派 `diagnostician`，禁看代码） |

## 3. 自主轮与唯一人工闸门

默认**一轮跑到出结果**：歧义就「决策—留痕—继续」（`spec/decisions.json` + `LOG.md` 的 `[DECISION:Dn]`），
不得用「要我继续吗」代替决策。能自己跑/查/算的事一律不请示。

- 决策三态：`auto`（高置信且可逆）/ `rule=discriminator`（做实验判别）/ `escalated`（命中升级条件）
- 升级条件只有：**E1** 只能靠造假通过；**E2** 两种读法分别导致定/否且做不出判别实验；**E3** 冻结后改目标集合；
  **E4** 不可逆且影响判定且置信非高；**E5** 所有参考不可得。违反 E1 直接停。
- 收尾只交两份：`REPORT.md`（六节固定）+ `REVIEW.md`（`make_review.py` 生成，**禁手改**）。
  人的介入点只有 `REVIEW.md` 签署与 E1–E5。

## 4. 预注册锚点（v3 新增，防事后调参）

```jsonc
// spec/anchors.json —— 首跑前登记，之后改它要留判别实验
{"items":[{"id":"A1","quantity":"plateau_Mz0.4","expected":0.390,"unit":"e2/h","tolerance":0.01,
  "source":{"kind":"paper","locator":"Fig.3(b) 平台段"},
  "status":"untested"}]}
```
`status ∈ {untested,held,violated}`；`held`/`violated` 需绑定 `reports/*.json` 的 sha256 证据；
`violated` 必须写 `resolution`（为什么偏低/偏高），并在 `REPORT.md` §3 披露。
**与 `calibration.json` 的分工**：calibration 答"我的代码自洽吗"，anchors 答"我的物理对得上论文吗"。

## 5. 算力预算与产物流水（v3 新增）

- `spec/budget.json`：`estimate{cpu_hours,basis}`（写算式不写结论）、`>2 h` 必须 `paths_considered` ≥2 条、
  `chosen{configs,chunk_size,resume}`、`measured[{done,seconds,run:{file,sha256}}]`（只认 manifest）。
  砍规模/改 ETA 必须有 `decisions.json` 的 `{budget_amendment:true, impact:"numeric"}` 条目，报告披露 `churn_count`。
- `artifacts.jsonl`：`python3 scripts/record_artifact.py <dir> <path> --kind figure --target fig3 --note "..."`，
  按 **sha256** 去重（不按文件名），支持 `--supersede`；`make_review.py` 据此渲染过程时间线。
- `python3 scripts/audit_self.py <dir> --json`：只读统计（盲重跑、决策 churn、未钉产物的目标），
  用来决定下一个优化该做什么，**不进 `validate.py`**。

## 6. 长文按需取（不要全文载入上下文）

| 想查 | 打开 |
|---|---|
| 路线细则、资格闸门、子代理提问范式 | `references/protocol.md#复现路线` |
| 数值/图像/标定/环境协议、loss 指标定义 | `references/protocol.md#数值协议` |
| 报告六节写法与判定词表 | `references/report_template.md` |
| 领域包与 L2 实例档案 | `references/domains/` + `references/protocol.md#领域包` |
| 踩过的坑（复用污染、单位差、crop 伪影…） | `references/pitfalls.md` |
| 路由索引（按症状找文档） | `references/index.md` |

## 7. 命令速查（完整链见 `references/protocol.md`）

```bash
python3 scripts/scaffold.py <dir> --title "<title>" [--official-code]   # 建骨架
python3 scripts/next.py <dir> --why                # ← 每轮从这里开始：唯一 NEXT
python3 scripts/vision.py probe                    # 视觉端点可用性
python3 scripts/check_anchors.py <dir>             # 预注册锚点是否哈希绑定
python3 scripts/check_budget.py <dir>              # 算力估算 + 实测吞吐
python3 scripts/record_artifact.py <dir> <path> --kind figure --target <tid>
python3 scripts/record_run.py <dir> --input ... --output ... --command ...
python3 scripts/make_review.py <dir> && python3 scripts/check_review.py <dir>
python3 scripts/validate.py <dir>                  # 阶段验收（升 stage 前）
```

## 8. 版本

发布以 git tag 为准：`VERSION` 写当前发布标签（今天 `v2`），`CHANGELOG.md` 顶部对照表把 tag 映射到开发线
（`v2` = 开发线 v3.0）。每个条目标题写「发布标签 X / 开发线 Y」。每次改动必须同步 CHANGELOG 并跑
`python3 scripts/selfcheck.py`（它核对 `VERSION` 与标题一致）。
