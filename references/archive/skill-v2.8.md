---
name: paper-repro
description: 复现数值物理论文的定量输出（曲线图/表格/文中数值断言）。当任务涉及"复现某篇论文的图或数据"、"从论文写代码并与原文对齐"、"Kwant/紧束缚/DFT/蒙特卡洛复现"、"结果和论文对不上要归因"时使用。有官方代码走 Route A（官方实现作指导教练），无官方代码走 Route B（以论文印刷数值 + 解析极限为预言机）；图像识别统一调 scripts/vision.py（kimi + 12ai OpenAI 兼容端点）。默认自主轮：模型一轮跑到出结果，遇歧义就决策—留痕—继续，只在触发升级条件时停下；收尾交复现报告与人工评审包。
---

# 论文定量复现

> **核心宗旨**：目标是**对论文发表结果做高保真独立定量复现**，官方代码只是加速器不是必需品。
> 论文有官方实现时走 **Route A**：以官方代码为指导教练，提炼物理拓扑、测量协议与解题思路，
> 指导自研 Pipeline 独立跑通（严禁直接抄袭复制代码）。
> 论文**没有**官方实现时走 **Route B**：以论文正文/表格/补充数据里的**印刷数值**为主真值，
> 以解析极限与守恒关系替代官方实现充当预言机，用视觉模型 + 多模态核验补齐图上的量。
> 两条路线都必须战胜“死线/空图/假拟合”，都不得用拟合论文图代替物理求解。

---

## 0. 官方代码指导（Route A）与论文真值路线（Route B）架构闭环

```
Route A（有官方代码）
                    ┌─────────────────────────┐
                    │ 官方实现 (paper/refcode) │
                    └────────────┬────────────┘
                                 │ 只读/提炼（禁止主 Agent 直读源码）
                                 ▼
                    ┌─────────────────────────┐
                    │  code-auditor / oracle  │ 提炼：测量拓扑、引线角色、
                    │     (思路指导教练)      │       势能形态、电导矩阵数学映射
                    └────────────┬────────────┘
                                 │ 高阶解题思路指导（严禁代码片段）
                                 ▼
┌──────────────────┐  思路指导  ┌─────────────────────────┐  独立物理求解  ┌──────────────────┐
│  论文公式/文本    │ --------> │ 主 Agent (自研 Pipeline) │ -----------> │ 左右并排比对验收  │
└──────────────────┘            └─────────────────────────┘              └──────────────────┘

Route B（无官方代码）：把上图最上面的“官方实现”整块替换为
  「论文印刷数值 + 补充材料 + 解析极限/守恒关系 + vision.py 图读数」四个并联预言机；
  量级级偏差的定位手段相应换成：解析极限对表 → 独立第二实现交叉 → 网格/截断收敛。
```

路线由 `project.json` 的 `official_code` 决定，并在 `spec/provenance.json` 的 `route` 声明；
`scripts/check_route.py` 校验声明与证据一致（Route B 不得偷用官方输出，且必须留有代码检索记录）。

---

## 1. 核心红线（全论文通用）

1. **唯一实现由自研 Pipeline 独立产出**：
   - 官方代码作为**指导题解思路的导师**，主 Agent 不得直接将官方代码复制进 `code/`，实现细节与变量名必须由自研 Pipeline 独立推导实现。
   - **Route B（论文无官方代码）**：不存在官方实现可供抄袭，但红线不变——实现必须由论文公式/算法描述独立推导，
     严禁把论文图的数字化点云当输入去拟合观测量（数字化值只能进 `data/ground_truth/` 作验收参考）。
   - **例外**：`reproduction_mode=author`（作者代码复运行/修复）允许直接运行官方代码，但该模式下目标必须声明 `validation_subject=author_implementation`，且不得声称为独立复现。
2. **严禁代码造假（AST 语法树自动审计）**：
   - 严禁在 `simulate_*.py` 中使用高斯、多项式等解析拟合函数硬编码生成观测量；物理量必须由数值求解器（`kwant.smatrix`, `scipy.linalg`, `solve`, `eigh` 等）计算得出（由 `check_physics_code.py` 严格审计）。
3. **严禁盲猜裁切与透明度叠加作弊**：
   - 子图截取必须使用 `read` 多模态工具亲眼查看，并输出核验凭证（由 `check_visual_crop.py` 审计）；
   - **对比图必须采用左右并排对比，严禁透明度叠加**（由 `check_figure_side_by_side.py` 强校验）。
4. **严禁死线与空图**：
   - 观测量全为 0（死线）或数据全在画幅外（空图）直接拦截，禁止进入对比（由 `check_figure_validity.py` 审计）。
5. **量级级偏差禁止调参**：出现"通道数 ×2/×3、$\Sigma$ 量级错、透射被倍乘、量子化值非整数、结果相差 ≥2 倍"等**量级级**偏差时，
   - **Route A**：第一个动作必须是派 `code-auditor`，禁止先扫参数、改阈值、换求解器或改缺陷实现类型。
   - **Route B**：没有官方实现可查，按固定三步取证，仍禁止先扫参数：
     ①**解析极限对表**（单模匹配 T=1、隔离极限 T→0、已知守恒关系、论文给的近似式）；
     ②**独立第二实现交叉**（换离散化/换求解器/换等价公式，例如 Landauer 与 Kubo 各写一次）；
     ③**收敛阶检查**（网格/截断/展宽加密后偏差是否按预期收敛，还是停在常数比例）。
     三步都指向“结构约定错”（简并因子、单位换算、切片键、自旋/谷计重）时，先改约定再谈数值精度。
   - 量级级错误几乎不可能是数值精度问题（那会是 $10^{-6}$ 级），必然是**结构约定错**；Route A 只存在于官方实现里，Route B 只存在于论文公式与单位表里。
6. **官方发布数据先冒烟**：若 `paper/refcode/` 下有官方发布的输出数据，**开工即用最小可对拍量做冒烟**（如 6 个端子电压），结果登记到 `spec/provenance.json` 的 `official_smoke`；`check_official_smoke.py` 在 stage≥calibrated 时强制该记录存在；无官方数据时该检查返回 `NOT_APPLICABLE`（Route B 常态）。
7. **全过程诚实留痕**：所有的失败尝试、假设证伪与改动轨迹必须如实记录在 `LOG.md` 与 `hypotheses.md`，证伪项标记 `[RETRACT]`，严禁篡改日志制造虚假 PASS。
8. **复现成功必须有报告，且判定不得手写**：`stage=final` 时根目录必须有 `REPORT.md`。逐目标判定（`定量符合`／`定性一致`／`未达标`／`未完成`）引用的指标数字必须与 `reports/*.json` 里评分报告的数字逐字一致，`check_report.py` 会比对；禁止把未经评分的估计写进报告。未达标与未完成项必须如实列出，不得省略。
9. **自主轮不得静默吞掉歧义**：全程默认不向人提问，遇歧义就**决策—留痕—继续**（见 §2.5）。每个非平凡决策写入 `spec/decisions.json`（选项、选择、规则、依据、可逆性、置信、影响），并在 `LOG.md` 记 `[DECISION:Dn]`。只有触发**升级条件**才停下来问人；升级项必须出现在 `REVIEW.md` 且被 `REPORT.md` §3 点名。改目标集合（`impact=scope`）永远不得自动决定。

**硬性要求：论文有图的复现对象必须复现该图并做左右并排对比。**
- 只要某复现对象的**数值计算在论文中以图（Figure）呈现**（曲线、谱、收敛图、parity 散点、热图等），
  无论其真值来自正文/表格/作者发布数据（`paper`/`published_data`/`analytic`），都必须：
  1. 用自研数值计算画出一张复现图 `figures/mine/<tid>.png`（附 `*.plot.json` 元数据）；
  2. 与论文原图生成左右并排对比图 `figures/compare/<tid>_side_by_side.png`；
  3. 在 `spec/project.json` 的该目标声明 `paper_figure`（论文图 id 列表，如 `["Fig3(b)"]`）；
  4. 在 `REPORT.md` §2 公开记录该对比产物。
- **不同于“图像提取仅为后备”**：这里不是从图里取真值，而是**把算出来的量画成图去和论文图并排核对**，
  因此它不因真值为数值来源而豁免，是验收硬门槛。
- 该目标**必须** `checks.visual.enabled=true`；否则 `check_independence.py` 直接判不通过。
- 该目标确无数值图时才可 `paper_figure=null`，此声明由 `check_spec.py` 强制；若声明不实属来源造假。
- 标量/表格目标若其量确实只在表格出现、无图，可 `paper_figure=null`，并在 `REPORT.md` §3 说明。

---

## 2. Subagent 协同规范（两条路线各有一套预言机）

**Route A（有官方代码）**：主 Agent 不要在黑暗中盲猜，按节点 1/2 向 Subagent 要解题思路；
**Route B（无官方代码）**：节点 1/2 的输入换成论文 + 经典文献 + 解析极限，派 `literature-oracle`。

### 节点 1：建模期——物理拓扑与测量协议指导
- **Route A → `code-oracle`**：
  - 何时调用：在编写 `spec/README.md` 与搭设系统骨架前；
  - 提问范式：“官方实现里一共有几个 Lead/接触端子？各自承担什么物理功能（源漏偏置、接地、电压悬浮探测）？”
    “目标观测量（如 $R_{xx}$, $G$）是通过什么数学关系组装出来的（电导矩阵求逆、还是透射相除）？”
  - 回答：给出测量几何拓扑与矩阵关系公式（如 $V = G^{-1} I$），**绝不输出源码实现**。
- **Route B → `literature-oracle`**：
  - 何时调用：无官方代码，但论文的测量拓扑/单位/哈密顿量写得不够自洽时；
  - 提问范式：“按论文 §II 的描述，这是几端测量？电压探针在哪？与 Datta/Büttiker 的哪个标准构型等价？”
    “文献里同类体系的简并因子/单位约定通常怎么取，本论文的图注能否决定唯一一种读法？”
  - 回答：给出**标准构型 + 可判别的约定选项**，以及能区分它们的解析极限（**不输出代码**）。

### 节点 2：标定与调试期——物理机制与差异定位
- **Route A → `code-auditor`**：结果出现死线（全为 0）、全透射、或目标谐振峰缺失时调用；
  提问要附自研几何/势能摘要，回答给出 400 字以内差异定位 + 判别实验。
- **Route B → 解析定位三步**（可派 `diagnostician` 从数据侧归因；但都不得看代码有/无）：
  ①与论文给出的近似式/极限对表；②另写一个等价实现交叉验证；③加密网格/截断看残差是否收敛。
  三步结论指向约定错时，把候选约定写成 `spec/decisions.json` 的 `rule=discriminator` 条目并做判别实验。

> 可用 Subagent：`code-oracle`/`code-auditor`（仅 Route A，需读官方实现）、`literature-oracle`（Route B 拓扑与约定）、
> `diagnostician`（只看数值与日志做偏差归因，两路线通用）、`digitizer`（图像取数，必配合 `vision.py`）。

### 节点 3：图像识别与审计 (`vision.py` + 原生 `read`)
- **调用 `scripts/vision.py`（默认模型 `kimi-k2.6`，endpoint `https://api.12ai.org/v1`，不可用时自动回退 `kimi-k3` 并记录原因）：**
  - `probe` 先确认分组下哪些模型可用；
  - `describe` 读单图得到结构化轴信息（子图标号、轴标/单位/量程/scale、曲线数/颜色/图例、面板内印刷数值）；
  - `audit` 直接从 PDF 子图生成 `*.visual_audit.json`（`review.method=model` + `vision.raw` 哈希绑定）；
  - `judge` 做论文原图 vs 复现图的**视觉对照证据**（`figures/compare/<tid>.vision_judge.json`）。
- **模型读数只是证据不是真值**：坐标、量程、单位必须再用原生多模态 `read` 亲自查看图附件复核；
  与模型读数不一致时在 `review.notes`/`LOG.md` 写明并以人工复核为准。`check_visual_crop.py` 对
  `method=model` 强制要求 `vision.model_used` 与 `vision.raw` 哈希，手写“model”不算复核。
- 数字化取数用 `digitize.py`（像素标定 + 颜色阈值），**不得用模型生成的数值代替像素提取**。

---

## 2.5 自主复现轮与升级策略（默认工作方式）

**默认不是逐步汇报、逐步等人拍板，而是模型自己跑完一整轮到出结果，人只在最后评审一次。**
把「每步报告 + 决策项」改成「**决策—留痕—继续**」：把遇到的歧义写进台账并选一个默认值，向下跑，
让后面的实验或拟合反过来证伪或验证它；直到这一轮产出了可评分的完整结果，再把人工需要的
东西一次性交出去。

### 推进纪律（默认连跑，禁止逐步请示）

- **不得在管道步骤之间停下问“是否继续/要不要往下”**；逐步汇报不是默认工作方式。完成一步立刻进入下一步。
- 只有命中升级条件 **E1–E5**、或抵达 `stage=final` 收尾时，才把控制权交回人工；其余一律「决策—留痕—继续」。
- 一轮尽可能跑到产出可评分结果，再一次交付 `REPORT.md` + `REVIEW.md`；人工只在 `REVIEW.md` 评审一次。
- 禁止用「要我继续吗？」式追问代替决策；能算的算、能判的判、能留痕的留痕。
- 长任务要分段执行时，**在同一个自主轮内连续调用工具推进**，不要以“下一步做 X，继续？”收尾。

### 唯一的人工闸门：`REVIEW.md` 签署

人的介入点只有两处：**`REVIEW.md` 签署**（`decisions.json` 里 `escalated` 项的裁决）与 **E1–E5 级事故**。
其余一律是模型自己的工作，**不得打包成问题丢回给用户**：

| 看起来像"要问人"的事 | 自主轮处置 |
|---|---|
| 迁移器报 `[EVIDENCE]`（缺 `paper_figure`、缺 `code_absence_check`） | 自己去查：读已审计 crop / 检索 arXiv+GitHub+作者主页，再回填参数 |
| 缺 `data/mine/runtime.json` | 自己用 `record_run.py` 跑真实计算产出（见 `check_env.py`） |
| `check_fix_log` 要 `[FIX:Fn]` | 登记**自己真实发生过的**纠错迭代；`runs/` 全成功且无迭代时才用 `[FIX:NONE] <理由>` |
| 数字化参考缺视觉审计 | 自己跑 `vision.py audit` |
| 论文没写某个取值 | 按 `least-commitment`/`discriminator` 自定并留痕，不请示 |
| 跑不动/缺凭据/参考不可得 | 这是 **E5**（唯一允许求助的技术阻塞），且其余产物照常交付 |

判断标准：**「这件事我自己能跑、能查、能算吗？」能，就别问。** 把"拒绝编造"和"请示用户"分开——
前者是不写假数据，后者是不做本该自己做的取证。

### 决策三种处置

| 处置 | 何时 | 留痕要求 |
|---|---|---|
| **自动决定**（`status=auto`） | 选项在本文能自洽、且**高置信**、且**可逆** | 写 `spec/decisions.json`，`LOG.md` 记 `[DECISION:Dn]` |
| **判别实验**（`rule=discriminator`） | 两个读法导致不同结论，但能做实验区分 | 做实验→拿证据→再定；证据绑定到条目 |
| **升级待人**（`status=escalated`） | 命中升级条件，模型无权自定 | `escalation_reason`；进 `REVIEW.md`，并被 `REPORT.md` §3 点名 |

### 目标资格：真值闸门 + 实现闸门（自主，先于冻结）

定义目标集合**之前**先跑一次资格过滤。路线由 `project.json` 的 `official_code` 决定，
并必须在 `spec/provenance.json` 声明：

```json
"route": {"mode": "B", "basis": "arXiv 与作者主页均无代码",
          "code_absence_check": ["arXiv source", "GitHub 搜索", "作者主页", "补充材料"]}
```

- **G1 真值闸（两条路线都必需）**：至少一个可定位、可哈希的真值来源——论文正文/表格数值、补充材料数值、
  作者发布数据（`published_data`）、解析或基准值（`analytic`/`benchmark`）、外部数据库，
  或无数值来源时按 `digitized` 回退的论文图（需视觉审计）。**无任何真值者剔除**。
- **G2 实现闸（有则必用，无则降级而非剔除）**：
  - **Route A**（`paper/refcode/` 或声明的官方码路径覆盖该对象）：官方实现作建模期指导教练，保留该目标。
  - **Route B**（检索确认无可用官方代码）：**不剔除**，但必须同时满足：
    ① 至少一个**印刷数值**锚点（`paper`/`supplement`/`published_data`/`analytic`/`database`/`author_material`），
      不能只靠 `digitized` 图当唯一真值；
    ② `spec/calibration.json` 至少一条 `limit` 或 `invariant` 断言（解析极限/守恒关系是官方实现缺席时的**替代预言机**）；
    ③ `provenance.route.code_absence_check` 记录查过哪些位置（arXiv/作者主页/GitHub/补充材料）。
  - **两条都套不住才剔除**（既无代码、又只有数字化图、还给不出任何退化极限/守恒关系）。
- **留痕**：两侧排查结果写 `spec/decisions.json`（`impact=eligibility`、`status=auto`、
  `rule=least-commitment`，`basis` 逐条列出查过的真值来源与官方代码），并在 `REPORT.md` §3
  写明本次走的路线、被剔除对象及原因。
- 这是**冻结前的机械资格过滤**；`impact=scope`（目标冻结后的增删改）仍永远不得自动决定（E3）。
- 闸门由 `scripts/check_route.py` 机械校验（route 一致性、Route B 禁用官方输出、数字化必须有视觉审计与哈希）。

### 升级条件（仅这几种才允许打断自主轮）

- **E1 无法伪造**：唯一能“通过”的方式是编数据、硬编码解析解、或回头改目标凑 PASS。
- **E2 判定级歧义**：两种读法分别导致 `定量符合` 与 `未达标`，且**做不出**判别实验（或实验本身依赖该歧义）。
- **E3 改目标集合**：冻结后删/改/降级 `project.json` 的目标（`impact=scope`，永远不得自动决定）。
  注意：冻结前按“真值 + 实现闸门”做的资格过滤（`impact=eligibility`）是自主的，不属 E3。
- **E4 不可逆且影响判定**：`reversibility=one-way` 且 `impact=verdict`，且置信非高。
- **E5 来源不可得**：所有参考都拿不到（付费/缺失/法律限制），无法定义任何可验收目标。

违反 E1 直接停：任何“造假式通过”都不是可选项，与是否自主无关。

### 交付两份东西

一轮自主复现跑完（`stage=final`）后，根目录应有：

- `REPORT.md`：复现报告（做了什么、到什么程度、局限）；
- `REVIEW.md`：**人工评审包**，由 `scripts/make_review.py` 从 `spec/decisions.json` 与评分报告生成，
  必要时**只在这里**等人工签署；禁止手改。

评审人只需：改 `spec/decisions.json` 中待裁决项的 `human_review{by,date,note}` 与 `status`，
重跑 `python3 scripts/validate.py .`。若裁决改变结论，再改 `REPORT.md` §1/§3。

---

## 3. 路线对比与阶段表

| 步 | 做什么 | 出口 | Route A (官方指导路线) | Route B (无官方代码独立路线) |
|---|---|---|---|---|
| 1 读原文与拓扑指导 | 读论文；有代码问 `code-oracle`，无代码问 `literature-oracle`，先做代码检索并登记 `route.code_absence_check` | `paper/` + 复现对象清单 | 清单里标明测量协议与验证对象 | 清单标明测量拓扑 + 印刷数值锚点 + 解析极限 |
| 1.5 领域实例化 | 选 L1 通用包；写 L2 `spec/domain_profile.md`（钉住包哈希 + §0–§7 状态 + 约定表） | `spec/domain_profile.md` | `check_domain_profile.py` 过 | 同左 |
| 1.6 图像审计与论文图复现（按需+硬性） | 仅图像参考需从 PDF 提取子图，用 `vision.py audit` + 原生 `read` 核验生成 `*.visual_audit.json`；**但若数值计算在论文中有图，必须复现该图并生成左右并排对比（硬性，不因数值真值而豁免）** | `data/ground_truth/<fig>_crop.png` `figures/mine/` `figures/compare/` | `check_visual_crop.py`（仅图像参考）；论文图目标的 visual 由 `check_independence.py`+`check_figure_validity.py` 强制 | 同左；`digitized` 参考必须有 `vision.raw` 哈希绑定的视觉审计 |
| 2 产 Spec | 按 `references/spec_template.md` 填 ①~⑦（**必填测量拓扑与能量对齐表**） | `spec/README.md` | `check_spec.py` 过 | `check_spec.py` 过 |
| 3 独立建模与代码审计 | 基于指导思路编写独立 Pipeline，严禁直接复制，严禁硬编码解析函数拟合观测量 | `code/` | `check_physics_code.py` 静态 AST 审计 | `check_physics_code.py` 静态 AST 审计 |
| 4 标定与响应防呆 | 跑标定；运行 1D 剖面对齐；**若出死线/空图则派 `code-auditor`（Route A）或做解析定位三步（Route B）** | `code/` `data/mine/` | `check_calibration` + `check_figure_validity` 过 | 同左；`check_route.py` 强制至少有 `limit`/`invariant` 断言 |
| 5 验证与左右对比 | 全参数扫描 + 双指标计算 + **生成左右并排对比图（严禁透明度叠加）** + `vision.py judge` 视觉对照证据；**有论文图的目标必做**（`paper_figure` 非空） | `data/ground_truth/` `figures/compare/` | `check_loss.py` + `check_figure_side_by_side.py` + 论文图目标的 `check_figure_validity.py` | 同左
| 6 产出与全过程诚实留痕 | 结论三档、README、LOG 真实完整全记录（含失败、差异与撤回） | 根 `README.md` `LOG.md` | 独立性与全量留痕审计通过 | 简易 README 与全量留痕 |
| 7 产出与交付（自主轮收尾） | 单轮自主跑到出结果：决策全部入台账，生成 `REPORT.md` 与人工待裁决的 `REVIEW.md` | 根 `README.md` `LOG.md` `REPORT.md` `REVIEW.md` | `check_route` + `check_decisions` + `check_review` + `check_report` 过（stage=final） | 同左；REPORT 必须点名 Route B |

> 两条路线的**产出物与验收标准完全一样**：不让 Route B 降级验收，只降级它可用的预言机。

---

## 4. 图表对比规范（左右并排，严禁透明度叠加）

- **对比采用左右并排对比，严禁透明度叠加（Alpha Blend）**：
  - 透明度叠加极易导致坐标轴、刻度线与图例混淆，甚至掩盖两图量纲不一致的致命缺陷；
  - 必须生成 `figures/compare/<fig>_side_by_side.png`：
    - **左栏**：论文原图精确裁切块（带清晰子图标号、坐标轴与原图刻度）；
    - **右栏**：自主物理计算图（严格相同的物理量纲、相同的数据范围与清晰标注）；
  - 执行 `python3 scripts/check_figure_side_by_side.py <论文目录> <fig_id>`，两图高度自动对齐，标明 `[Paper Original]` 与 `[Reproduced]`。

- **论文有图即强制对比**：目标 `paper_figure` 非空 ⇒ 必须产出 `figures/mine/<tid>.png` + `figures/compare/<tid>_side_by_side.png`，
  并由 `check_independence.py`（强制 visual 启用与配置字段）和 `check_figure_validity.py`（在 `stage=final` 要求对比产物真实存在、非空、非死线）机械把关。
  图与真值的来源可以不同（真值取表格/发布数值，图用于形状与量级核对），两者都要登记。
- **视觉对照证据（推荐，两条路线都适用）**：
  ```bash
  python3 scripts/vision.py judge <dir> <tid> --paper data/ground_truth/<fig>_crop.png --mine figures/mine/<tid>.png
  ```
  产出 `figures/compare/<tid>.vision_judge.json`（量纲/量程/形状/量级四项判定 + 差异清单）。
  它能在量级级偏差上给出“×2 幅度/简并因子”这种具体线索，是 Route B 定位失败原因的第一手证据；
  但**它不是验收闸门**，判定为 `disagree` 时不得因此调参，先查约定与单位，并在 `REPORT.md` §3 记录该判定。

---

## 5. 通用关卡脚本执行链

```bash
python3 scripts/vision.py probe                                       # 0. 视觉端点/模型可用性（默认 kimi-k3，回退 kimi-k2.6）
python3 scripts/upgrade_project.py <dir> [--apply]                    # 0.5 旧工作区迁移（只补机械可推导项，拒绝编造）
python3 scripts/scaffold.py <dir> --title "<title>" [--official-code] --reproduction-mode paper  # 1. 建骨架（不传 --official-code 即 Route B）
python3 scripts/vision.py audit <dir> <crop> --pdf paper/<pdf> --page N --bbox "x0,y0,x1,y1" --subfigure "Fig3(b)"  # 2. 子图视觉审计（替代手填）
python3 scripts/check_visual_crop.py <dir> <crop_img>              # 2b. 截图审计（image/pdf 哈希 + review 字段）
python3 scripts/check_spec.py <dir>                                # 3. Spec 准入（拓扑/能量对齐/缺陷要素）
python3 scripts/check_domain_profile.py <dir>                      # 3.5 领域实例化（包哈希/§0–§7/约定表）
python3 scripts/check_physics_code.py <dir>                        # 4. 物理代码 AST 诚信审计
python3 scripts/check_route.py <dir>                               # 4.5 路线一致性（A/B + code_absence_check + 替代预言机）
python3 scripts/check_calibration.py <dir>                         # 5. 标定闸门
python3 scripts/check_figure_validity.py <dir> <fig_id>            # 6. 图表非空非平线防呆
python3 scripts/check_loss.py <dir> <fig_id> --report <dir>/reports/<fig_id>.json  # 7. 数值对齐双指标
python3 scripts/check_figure_side_by_side.py <dir> <fig_id>        # 8. 左右并排清晰对比
python3 scripts/vision.py judge <dir> <fig_id> --paper <crop> --mine figures/mine/<fig_id>.png  # 8.5 视觉对照证据
python3 scripts/check_hypotheses.py <dir>                          # 9. 假设台账与证伪留痕
python3 scripts/check_independence.py <dir>                        # 10. 独立性审计
python3 scripts/check_decisions.py <dir>                           # 11. 自主决策台账（选项/规则/升级策略）
python3 scripts/make_review.py <dir>                               # 12. 生成人工评审包 REVIEW.md
python3 scripts/check_review.py <dir>                              # 13. 评审包新鲜度与待裁决覆盖
python3 scripts/check_report.py <dir>                              # 14. 复现报告（仅 stage=final）
python3 scripts/validate.py <dir>                                  # 15. 按 stage 跑全套适用检查
```

---

## 6. 复现报告（复现成功后的交付物）

所有目标评分完成后（`stage=final`），必须输出项目根目录的 `REPORT.md`。模板：`references/report_template.md`；
校验：`scripts/check_report.py`。它**只查结构与证据绑定，不重算物理**。

固定六节，标题不得改写：

| 节 | 必填内容 |
|---|---|
| `## 0. 结论摘要` | 一句话结论：哪些观测量被定量复现到什么程度、哪些没有；点名验证对象与复现模式 |
| `## 1. 逐目标结果` | Markdown 表格，列含 `目标`/`判定`/`指标`/`证据`；每个 `project.json` 目标恰好一行 |
| `## 2. 门禁与证据` | 实际运行过的 `check_*.py` 与结果（≥3 个），外加绑定运行 `runs/<ID>/manifest.json` |
| `## 3. 局限与未完成项` | 逐条写清：**本次走的路线（Route A/B）与为何**、未留出验证、被调参影响的约定、采样密度不足、被移除的目标及原因、视觉对照 `disagree` 的项 |
| `## 4. 复现方法` | 可重跑的最小命令（含 `python`）、环境钉住项、关键数值旋钮 |
| `## 5. 参考来源与调参披露` | `reproduction_mode`、每个 `kind` 的来源与不确定度、`used_for_tuning` 的非留出声明、`digitized` 的回退理由 |

判定词表固定为 `定量符合`／`定性一致`／`未达标`／`未完成`。**硬约束**：

- 判定为 `定量符合` 或 `定性一致` 时，`指标` 列的数字必须与 `证据` 列那份 `reports/*.json` 里的
  指标数值一致（容差 1e-6），且该评分报告 `status` 必须是 `PASS`、`target` 必须同名；
- 存在 `used_for_tuning=true` 的参考时，§3 或 §5 必须出现"调参／tuning／非留出／held-out"字样；
- 任一目标判定为 `未达标`／`未完成` 时报告照常输出，**不得为凑齐全部通过而删除该目标**；
  删除目标必须在 §3 里写明原因（例如"逐键相位无法作为 loss 目标，已降级为标定项"）。

一句话原则：**报告是给人看的交付物，数字是给机器查的证据**。两者不一致时以 `reports/*.json` 为准。

---

## 7. 人工评审包（自主轮的人工入口）

`make_review.py` 从 `spec/decisions.json` 和已落盘的评分报告生成 `REVIEW.md`（**禁止手改**），
内容：自动产出汇总、**待裁决**清单（escalated）、已自动决策清单、已人工确认清单、评审动作。
`check_review.py` 校验它不陈旧、不漏待裁决项。

这不是取消人工，而是让一个人工轮**只停一次**，而且停的时候交付物是完整的（有报告、有结果、
有待裁决清单），而不是“做到一半没跑通就发问”。如果一轮里停下来超过一次，先回去看：是不是该把
该歧义改成判别实验或高置信可逆的自动决策。

### 决策台账样例（`spec/decisions.json`）

```json
{
  "items": [
    {
      "id": "D1", "question": "横轴 φ 的归一单位是每单位胎还是每超胎？",
      "options": ["每单位胎 φ/φ0∈[0,1]", "每超胎 φ/(n0φ0)"],
      "chosen": "每单位胎 φ/φ0∈[0,1]",
      "rule": "discriminator", "basis": "Fig.10 图注六个数的线性组合恰好给出 2π/7 的相位不变量，只有每单位胎读法自洽",
      "evidence": [{"file": "data/ground_truth/fig10_crop.png", "sha256": "<hash>", "metric": "hexagon_flux_sum", "result": 126.0}],
      "reversibility": "reversible", "reverse_cost": "只改 x 轴标注，谱数据不变",
      "confidence": "high", "impact": "convention", "status": "auto"
    },
    {
      "id": "D2", "question": "第二层相对平移取 −v 还是 0？",
      "options": ["−v=(−a/√3,0)", "0"],
      "chosen": "−v=(−a/√3,0)", "rule": "discriminator",
      "basis": "两种取法各跑一轮，下带边 rms_norm 0.00753 vs 0.00808，仅差 7%，不足以定案",
      "evidence": [{"file": "reports/variants/fig3_sm0m57735p0.json", "sha256": "<hash>", "metric": "rms_norm", "result": 0.00808}],
      "reversibility": "reversible", "reverse_cost": "重跑扫描，不改公式",
      "confidence": "low", "impact": "verdict", "status": "escalated",
      "escalation_reason": "两种取法的下带边差距仅 7%，无法用现有判别实验定案，而它影响带边结论"
    }
  ]
}
```

要点：`chosen` 必须是 `options` 里哪个字面量；`rule` 要在选择前就定好；
`confidence=low` 且 `impact=verdict` 的条不得写 `status=auto`（`check_decisions.py` 会拦）。
