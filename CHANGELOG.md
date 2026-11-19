# v2.8 去掉流程里的人（自主轮收口）

- `SKILL.md` 新增「唯一的人工闸门：`REVIEW.md` 签署」：人的介入只剩两处（REVIEW 裁决、E1–E5），
  其余不得打包成问题丢回用户；附「`[EVIDENCE]` / `runtime.json` / FIX 台账 / 数字化审计 / 论文未写取值」
  的自主轮处置表。判断标准一句话：能自己跑、能查、能算，就别问——「拒绝编造」不等于「请示用户」。
- `upgrade_project.py`：`[MANUAL]` 改名 `[EVIDENCE]`。这些不是"问用户"，是自主轮自己取证后再回填参数。
- `check_fix_log.py`：新增 `[FIX:NONE] <理由>` 声明通道。此前"有代码但一次没调试过"的工作区会被迫
  编造纠错历史；现在仅在 `runs/` **从未有失败运行**且当前代码快照**有通过运行**时接受该声明，
  所以清空台账仍藏不住失败。新增 4 个回归用例。
- `check_feature_resolution.py`：map/heatmap 目标（roles 无 `x`/`y`）此前抛 `KeyError: 'x'`，
  现在打印 `[DISCLOSURE]` 跳过——二维目标不存在一维采样轴问题。
- `references/protocol.md`：补 runtime.json 缺口自助产出方法（探针脚本 + `record_run` 绑定 + 见证文件自报 sha256）。
- `make_review.py`：签署之后仍印「自动流程在没有任何人工输入的情况下跑到了这里」「未经人工签署」——
  已在 `spec/decisions.json` 里 `human_confirmed` 的条目被自相矛盾地否认。现按 `len(human)` 切换措辞：
  头部改「N 条决策已由人工确认（见 §3）」，§5 标题改「N 条决策已人工确认，整篇结论仍须复核」。

# v2.7 Route A / Route B 双轨 + 视觉读数（kimi@12ai）

> 起因：v2.6 的“真值 + 官方代码双闸门”把“无官方代码”当成剔除理由，等于宣称 skill 只能复现有代码的论文。
> 本版把官方代码从**必需条件**降为**路线选择**：有则走 Route A（官方实现作指导教练），
> 无则走 Route B（以论文印刷真值 + 解析极限为预言机），两条路线验收标准相同。

- 新增 `scripts/upgrade_project.py`：旧工作区迁移（默认 dry run）。只写机械可推导项（`route.mode` 跟随
  `official_code`、`basis` 写明代码位置），逐文件留 `.pre-upgrade-<UTC>` 备份；`[MANUAL]` 项
  （论文图 id、代码检索记录、数字化视觉审计）永不自动填写。`--paper-figure tid=Fig2(a)` /
  `--code-absence WHERE` 用于人工授权后写入。新增 `tests/test_upgrade.py`（7 例）。
- `vision.py` 默认模型顺序改为 `kimi-k3` → `kimi-k2.6`（后者在部分 12ai 分组返回 404），
  失败模型的结果缓存在 `~/.cache/paper-repro/vision_hosts.json`，同主机后续调用不再重试。
- 新增 `scripts/check_route.py`（stage≥calibrated）：`provenance.route` 必须声明且与 `official_code` 一致；
  Route B 强制 `code_absence_check`、禁止 `official_comparison`、要求至少一个印刷数值锚点、
  要求 `spec/calibration.json` 至少一条 `limit`/`invariant` 断言，并在 `stage=final` 要求报告点名 Route B。
- 新增 `scripts/vision.py`：OpenAI 兼容多模态调用（默认 `https://api.12ai.org/v1`，模型链
  `kimi-k2.6` → `kimi-k3`，不可用时自动回退并记录原因）；子命令 `probe`/`describe`/`audit`/`judge`。
  `audit` 直接生成 `*.visual_audit.json`（模型读数 + CLI 覆盖来源 + `vision.raw` 哈希绑定）。
  凭据：`--api-key` → `PAPER_REPRO_VISION_API_KEY`/`OPENAI_API_KEY` → `~/.pi/agent/models.json` 同 host provider。
- `check_visual_crop.py`：`review.method=model` 现在强制 `vision.model_used` + `vision.raw` 哈希，
  且 `reviewer` 必须等于实际应答模型——手写“model”不再算复核。
- `check_route.py` 接入 `validate.py`；`scaffold.py` 的 provenance 自动带 `route`（按 `--official-code` 定 A/B），
  生成的 README 注明当前路线。
- `check_feature_resolution.py`：map/heatmap 目标（roles 无 `x`/`y`）此前直接抛 `KeyError: 'x'`，
  现在打印 `[DISCLOSURE]` 跳过——二维目标没有一维采样轴问题。修复前 Tam2023 的 8 个 map 目标全部误报。
- 文档重写：SKILL §0 架构图拆 A/B、§2 增加 `literature-oracle` 与 Route B 解析定位三步、
  §2.5 资格闸门改为“真值闸 +（有则必用、无则降级）”实现闸、§4/§5 加入 `vision.py judge` 与 `check_route.py`；
  protocol 增加“复现路线”节与图像协议重写；checklists / report、spec 模板同步。
- 兼容性：旧工作区需在 `spec/provenance.json` 补 `route` 字段（`{"mode":"A"|"B","basis":"...","code_absence_check":[...]}`），
  否则 `validate.py` 会在 stage≥calibrated 报 INCOMPLETE。
- 新增回归测试 `tests/test_route.py`（路线闸门 + 视觉审计哈希绑定）；现有 63 项测试全通过。

# v2.6 论文图复现硬性要求（paper_figure）

> 起因：此前“数值参考优先、图像提取仅后备”被误读为“真值取数值就不必复现论文图”，
> 导致数值完全对得上、但论文里那张图从未被并排核对。本版把“论文有图就要复现对比”升为硬门槛。

- project.json 每个目标新增必填字段 `paper_figure`：`null` 或论文图 id 列表（如 `["Fig3(b)"]`）。
  声明非空即触发强制 visual 复现 + 左右并排对比；`check_spec.py` 强制该字段存在且类型合法。
- `check_independence.py`：`paper_figure` 非空 ⇒ `checks.visual.enabled=true` 且配置含
  `crop`/`mine_image`/`plot_metadata`/`comparison_image`，否则不通过。
- `check_figure_validity.py`：`stage=final` 时，`paper_figure` 非空目标必须已有真实存在的
  `figures/compare/<tid>_side_by_side.png`（以及论文原图 `crop`），且非空、非死线、可见比例达标。
- `check_report.py`：存在 `paper_figure` 目标时，`REPORT.md` §2 必须记录左右并排对比产物。
- 文档（SKILL §1/§3/§4、protocol“来源”“图像协议”、checklists、report/spec 模板）同步：
  这不是从图取真值，而是把算出来的量画成图去和论文图核对，因此不因真值来自表格/数值/published_data 而豁免。
- 兼容性：旧工作区需显式补 `paper_figure` 字段（scaffold 生成的新工作区自动带 `null`）。



> 起因：流程习惯是“每做一步就报告、等人拍板”，把模型当手；大量决策本可自定（且有实验可证伪），
> 却成了人工阻塞。目标改为：**模型一轮跑到出结果，人只在最后评审一次**；关键决策落洛。

- 新增 `spec/decisions.json`（决策台账）与 `scripts/check_decisions.py`。每条决策记：问题、选项、
  选择、规则（选择前定）、依据、证据、可逆性、置信、影响、状态。检查器只查策略不判物理：
  `chosen` 必须在 `options` 字面量中；`impact=scope`（改目标集合）永远不得 `auto`；
  `impact=verdict` 且低置信/不可逆必须 `escalated`；`one-way` 需 `reverse_cost`；每条 `Dn` 须在
  `LOG.md` 有 `[DECISION:Dn]`。
- 明确**升级条件**（仅这几种才打断自主轮）：E1 需伪造/硬编码；E2 判定级歧义且无判别实验；
  E3 改目标集合；E4 不可逆且影响判定且置信非高；E5 参考不可得。
- 新增 `scripts/make_review.py` -> `REVIEW.md` + `reports/review.json`：从台账与评分报告生成
  人工评审包（自动产出汇总 / 待裁决 / 已自动决策 / 已人工确认 / 评审动作），**禁手改**。
- 新增 `scripts/check_review.py`：校验评审包不陈旧（sha256 绑定台账）且覆盖全部 `escalated` 项；
  `check_report.py` 新增要求：每个待裁决决策必须被 `REPORT.md` §3 点名，防止把开放问题埋在交付物里。
- `validate.py`：stage≥calibrated 加 `check_decisions.py`；final 在 `check_report.py` 前加
  `make_review.py` + `check_review.py`。`scaffold.py` 生成空台账。
- `SKILL.md` 新增 §2.5「自主复现轮与升级策略」、§7「人工评审包」、红线第 9 条；
  `protocol.md` 新增「自主复现轮与决策台账」；`report_template.md`/`checklists.md` 同步。

# v2.4 复现报告：复现成功后的固定交付物

> 起因：复现跑完后结论散落在 README/LOG/各 `reports/*.json` 里，没有一份可交付、可核对的报告；
> 且"看起来对"的数字容易被手写进总结，与已落盘的评分脱钩。

- 新增 `references/report_template.md`：固定六节（结论摘要／逐目标结果／门禁与证据／局限与未完成项／
  复现方法／参考来源与调参披露），`scaffold.py` 自动生成 `REPORT.md`。
- 新增 `scripts/check_report.py`：校验结构与证据绑定——§1 表格每个目标恰好一行、判定用固定词表、
  通过类判定必须引用 `reports/*.json` 且该报告 `status=PASS`、`target` 同名，以及**报告里的指标数字
  必须与该 JSON 的指标数值一致（容差 1e-6）**，用于杜绝手写未评分数字。仅 `stage=final` 强制，
  早期阶段返回 NOT_APPLICABLE。
- 报告须披露：`used_for_tuning` 参考的非留出验收、`digitized` 的回退理由、以及被移除目标的移除原因。
- 已挂进 `validate.py`（仅 final 阶段）；`SKILL.md` 阶段表新增第 7 步、关卡链新增第 11 步、
  红线新增第 8 条（禁止手写未经评分的判定数字）。
- `references/protocol.md` 新增"复现报告"一节；`checklists.md` 验收节新增对应条目。

# v2.3 防"取证时机失误"的三道闸门

> 起因：一次复现中，官方发布数据就在仓库里，却在数值猜测上耗了 1 小时以上；且 Spec 里写明的
> `[O]` 参数（左端竖条 20 a0）从未进入代码实现。

- 新增 `scripts/check_official_smoke.py`：`paper/refcode/` 下有发布数据时，`spec/provenance.json`
  必须含 `official_smoke`（文件+哈希、compared、data_file、tolerance、passed、date），否则 stage≥calibrated 时阻断。
  只抓量级/结构错，不抓精度；缺失机制返回 INCOMPLETE 而非 FAIL。
- 新增 `scripts/check_profile_anchors.py`：`spec/domain_profile.md` 的约定表每行必须有定位，
  `code/<path>::<SYMBOL>` 形式的锚点会被校验（文件存在且真的含有该符号），用于杜绝"只写进文档没进代码"。
- 两者已挂进 `validate.py`（前者 stage≥calibrated，后者含 planning）。
- SKILL 红线新增两条：**量级级偏差禁止调参**（第一个动作是派 `code-auditor`）、**官方发布数据先冒烟**。
- `references/domains/quantum-transport.md` §6 新增"结构约定"失败模式；`checklists.md` 的开工/标定两节同步。
- `_profile_template.md` 的约定表改用 `code/<path>::<SYMBOL>` 锚点写法。

# v2.2 领域实例化层（L1 通用 + L2 个性化）

- 新增 L2 `spec/domain_profile.md`：每篇论文声明如何实例化/扩展通用包——`pack`+`pack_sha256` 钉住版本、
  §0–§7 逐段状态（采用/实例化/扩展/偏离/不适用）、约定表（规范/简并/符号/能量零点/单位）、晋升候选表。
- 新增 `scripts/check_domain_profile.py`：校包哈希一致、§0–§7 无缺行、行级证据（采用需实例值，扩展/偏离需定位，不适用需理由）、晋升候选只能 `待验证` 或 `已验收:<证据>`。已接入 `validate.py`（含 planning）。
- 通用包新增必填头部 `pack_version/scope_includes/scope_excludes/verified_cases`；`scope_excludes` 为硬约束，落入排除区必须走 L2 扩展路径。`selfcheck.py` 校验该头部并忽略 `_` 开头模板文件。
- 模板新增 `references/domains/_profile_template.md`；`scaffold.py` 自动生成 L2 档案。
- `spec_template.md` ① 新增**缺陷要素表**：缺陷（边界势/散射体/孔）必须声明实现类型 `几何移除`／`连续势`／`紧束缚项`。
- 修正 SKILL 文档与 CLI 不一致：`--route A|B` 实际为 `--official-code --reproduction-mode`；`check_loss.py --mine/--gt` 实际为位置参数 `root target`。
- 截图裁切改为仅图像参考需要（与 v2.1 数值参考优先一致），不再作为两条路线的强制步骤。
- 明确 `reproduction_mode=author` 允许直接运行官方代码，但不得声称为独立复现。

# v2.1 参考数据策略

- 数值参考优先，截图/矢量提取为后备；正文、表格、配套数据、补充材料、作者说明和官方运行均可追溯登记。
- 新增 reproduction_mode（paper/independent/author）与逐目标 validation_subject，区分发表结果、作者实现和外部基准。
- 允许官方输出直接用于 loss，需运行绑定；独立模式要求先行基线，作者复运行允许官方导入。官方运行结果不自动等于发表结果。
- 来源新增定位、版本、条件、误差、用途与调参披露；图像提取需回退理由与视觉检查。gt/ground_truth 保留为历史名称，不表示无误差真值。
- 同步 SKILL、协议、模板、领域包和回归测试；已有项目需显式补齐新字段，不自动迁移。

# v2 整改记录

- 分离验证等级、官方代码可用性、目标类型和 Spec 阶段；新增统一协议 references/protocol.md。
- 修复自检递归、JSON 标定导入错误、NaN/空数组通过及全零效应通过。
- 数值检查采用显式单位、预声明尺度/阈值、固定网格、覆盖率和缺口约束；峰位/峰高与幅度上下界参与判定。
- 支持曲线、标量、表格和地图；不擅自排序、去重、过滤无效点或重采样地图。
- 视觉检查绑定图片/PDF/数据哈希及复核元数据；生成并排图与验证分离。旧 overlay 入口弃用。
- AST 仅检查语法及有限风险；不再声称证明物理真实性。环境检查对照模拟进程报告和实际数据 dtype。
- 新增 record_run.py，保存成功/失败/启动失败/超时记录；拒绝覆盖已有声明输出。
- 来源与假设改用结构化证据；撤回精确关联假设 ID；明确本地记录不是防篡改或独立作者身份的证明。
- 修正量子输运包中的串联、互易、LDOS/非平衡、简并及阈值等过度泛化。
- 新增 tests/test_checks.py，含异常路径和合成端到端测试。真实论文、随机统计及各领域收敛仍需具体任务验证。

兼容性：旧 A/B、loss/effect CLI 与 hypotheses.md 的机器校验接口已替换。保留已有论文目录，不自动迁移；按 references/protocol.md 人工迁移。
