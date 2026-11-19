# 配置与命令协议（v2）

Python >=3.10，脚本依赖 numpy、Pillow。领域求解器另装。本协议替代旧版 A/B 和旧 CLI；不自动迁移论文项目。

## 验证等级与阶段

- quick：限定目标，最小标定与定量误差；声明尚未做完整收敛/统计研究。
- standard：增加收敛实验和不确定度预算。
- strict：增加独立参考、后端或算法交叉检查；独立实现模式下官方实现须在基线之后对照。

等级是科学工作量约定，不是用开关跳过错误检查。三个等级都检查声明的数据与证据；脚本不能自动判定研究的科学充分性。

planning 仅运行 check_spec，允许探索代码；calibrated 加入实现、标定、环境和归因检查；final 运行全套适用检查。validate 根据 stage 选择检查，阶段不由脚本自动提升。

## 复现模式与验证对象

project.reproduction_mode 必填：paper（论文结果复现，允许使用官方代码但披露）、independent（独立实现基线后再对拍）、author（作者代码复运行/修复，official_code 必须为 true）。这与验证等级无关。

target.validation_subject 必填：paper_result（发表结果）、author_implementation（作者实现运行输出）、benchmark（解析解/外部基准）。官方新运行输出可直接用于 loss，但目标必须为 author_implementation；如需同时断言发表结果一致，另设使用发表参考的目标。作者已发布且明确对应论文结果的数据可登记 published_data，不等同于新运行输出。

优先寻找论文对应的原始数值、正文数值/表格、补充数据、勘误或作者说明，再按目标考虑官方运行和外部基准；图像提取是无可用数值数据时的后备方案，不强制截图。没有一种来源自动无误，发生冲突须报告。正文少量数字仅支持对应标量/表格，不能补造整条曲线。

**论文图复现硬性要求（与上述“图像提取仅为后备”不矛盾）**：真值仍优先取数值来源；但只要某复现对象的数值计算在论文中以图（Figure）呈现，就必须把自研计算结果画成图并与论文原图做左右并排对比（见“图像协议”与 SKILL §1）。这不是“从图里取真值”，而是“把算出来的量画成图去和论文图核对”，因此不因真值来源是数值/表格/published_data 而豁免。每个目标在 project.json 用 `paper_figure` 显式声明对应论文图 id（无数值图则填 null）。

## 领域包与实例化层（L1 通用 / L2 个性化）

领域知识分两层，不得混用：

- **L1 通用包** `references/domains/<pack>.md`：跨论文复用的物理知识。头部必须声明
  `pack_version`、`scope_includes`、`scope_excludes`、`verified_cases`。
  `scope_excludes` 是硬约束：论文落入排除区时**不得**直接套用，必须走 L2 扩展路径。
- **L2 实例档案** `spec/domain_profile.md`（scaffold 自动生成）：记录本论文如何实例化/扩展 L1。
  必填：`pack` + `pack_sha256`（钉住包版本）+ `失效条件`；§0–§7 逐段状态
  （`采用`/`实例化`/`扩展`/`偏离`/`不适用`），`采用` 需本文实例值，其余需定位或理由；
  另有**约定表**（规范/简并/符号/能量零点/单位——禁止沿用他文默认值）与**晋升候选表**。

`check_domain_profile.py` 验证：包哈希一致、§0–§7 无缺行、行级证据存在、晋升候选只有
`待验证` 或 `已验收:<证据>`。它只查结构与证据，不判断物理映射是否正确。

没有合适通用包时 `project.domain` 与档案 `pack` 都写 `generic`，并在档案的 `缺口` 行
说明缺什么知识、用什么替代。论文验证通过后可把 L2 的新知识回流 L1（晋升为人工确认制）。

## 基本操作

以下路径相对于 skill 目录；在其他工作目录运行时使用脚本绝对路径。

```bash
python3 scripts/scaffold.py /path/to/paper --title "论文标题" --level standard            # 无官方代码：不传 --official-code
python3 scripts/check_spec.py /path/to/paper
python3 scripts/check_domain_profile.py /path/to/paper
python3 scripts/check_route.py /path/to/paper
python3 scripts/vision.py probe
python3 scripts/vision.py audit /path/to/paper <crop> --pdf paper/paper.pdf --page 3 --bbox "x0,y0,x1,y1"
python3 scripts/record_run.py /path/to/paper --input paper/input.csv \
  --output data/mine/fig1.npz --output data/mine/runtime.json \
  --timeout 3600 --command /path/to/python code/simulate.py
python3 scripts/check_calibration.py /path/to/paper
python3 scripts/check_effect.py /path/to/paper fig1
python3 scripts/check_loss.py /path/to/paper fig1 --report /path/to/paper/reports/fig1.json
python3 scripts/check_visual_crop.py /path/to/paper data/ground_truth/fig1_crop.png
python3 scripts/check_figure_side_by_side.py /path/to/paper fig1
python3 scripts/check_figure_validity.py /path/to/paper fig1
python3 scripts/check_decisions.py /path/to/paper
python3 scripts/check_hypotheses.py /path/to/paper
python3 scripts/make_review.py /path/to/paper
python3 scripts/check_review.py /path/to/paper
python3 scripts/validate.py /path/to/paper
python3 scripts/selfcheck.py
```

scaffold 生成待填写文件（null/空列表有意不通过验收）；不会覆盖旧文件。source、domain、criterion 需要填写；没有领域包时 domain 可写 generic，并在 Spec 说明知识缺口。关闭可选检查必须给理由；从论文图提取数值必须启用 visual，直接数值参考不需要截图。**但每个目标必须显式声明 `paper_figure`（null 或论文图 id 列表）：数值计算在论文中有图就非空，并因此强制启用 visual + 并排对比。**

## project.json

```json
{
  "schema_version": 1,
  "title": "论文标题",
  "source": "DOI 或 arXiv",
  "level": "standard",
  "official_code": false,
  "reproduction_mode": "paper",
  "stage": "planning",
  "domain": "quantum-transport",
  "environment": "spec/environment.json",
  "independence": "spec/provenance.json",
  "targets": [{
    "id": "fig1", "type": "curve", "mode": "quantitative", "validation_subject": "paper_result",
    "criterion": "全区间误差及峰值符合预声明阈值",
    "paper_figure": ["Fig1(b)"],
    "checks": {
      "loss": {"enabled": true, "config": "spec/fig1.loss.json"},
      "visual": {"enabled": true, "config": "spec/fig1.visual.json", "reason": "论文 Fig1(b) 数值图，硬性要求复现并排对比"},
      "effect": {"enabled": false, "reason": "本目标不是微扰效应"}
    }
  }]
}
```

## 数值协议

历史字段 gt 和目录 data/ground_truth 表示“参考数据”，不宣称无误差真值；gt.file 可指向其他项目内目录，包括 comparisons/official。loss 的单独 PASS 仅是数值协议结果；来源与复现模式还须通过 check_independence 检查。

NPZ 的 units 是 JSON 字符串标量，例如 `np.savez(path, x=x, y=y, units=json.dumps({"x":"nm", "y":"kOhm"}))`。CSV 需表头及同名 `.meta.json`，含相同 units。keys 是文件中数组名称，roles 映射标准角色 x/y/coordinates 到数组名称。单位必须由调用方显式转换，不自动猜测。

曲线配置示例（数值仅演示结构，不是推荐阈值）：

```json
{
  "type": "curve", "domain": [0, 1], "grid_points": 201,
  "max_gap": 0.02, "min_coverage": 1.0, "scale": 10,
  "reference_uncertainty": 0.05,
  "threshold_basis": "独立估计参考提取误差 0.05 kOhm；另给数值误差预算 0.05 kOhm",
  "metrics": {
    "rms_norm": 0.01, "min_r": 0.9, "amp_ratio": [0.9, 1.1],
    "peak": {"kind": "max", "window": [0.2, 0.8], "x_tol": 0.02, "y_tol": 0.1}
  },
  "mine": {"file": "data/mine/fig1.npz", "keys": ["x", "y"], "roles": {"x":"x", "y":"y"}, "units": {"x":"nm", "y":"kOhm"}},
  "gt": {"file": "data/ground_truth/fig1.csv", "keys": ["x", "y"], "roles": {"x":"x", "y":"y"}, "units": {"x":"nm", "y":"kOhm"}}
}
```

- rms_norm = sqrt(mean(((mine−reference)/scale)^2))；scale 必须预声明，无伪 L2 别名。
- 比较使用固定等距网格；不外推、不自动删除 NaN、不自动去重/排序。
- 默认要求完整覆盖；如确需部分覆盖，在科学结论中明确限制。max_gap 限制任一输入的采样缺口。
- 峰值在显式窗口内按 max/min 搜索，峰位和峰高都参与判定。
- peak 可为对象或对象列表：含多个显著极值的参考必须逐特征声明窗口（峰1/峰2…），
  只声明一个窗口等于对其余特征放弃审计。
- reference_uncertainty 是数据单位下的误差估计；脚本不自动放宽阈值，阈值预算须在 threshold_basis 中说明。
- digitize 输出 excluded_x；含缺口的参考必须拆分目标，每段输入声明 valid_domain，等于该目标 domain，且不得覆盖 excluded_x。
- scalar：只需 y 角色且恰好一个值；table/map：需要 y 和 coordinates，坐标/行列顺序必须逐项一致，不自动重采样。可将完整网格坐标保存为 (N, d)，y 保存为 (N,) 或相应网格形状。
- 随机结果应先生成统计量、误差棒和额外统计检验，附到报告；通用检查器不自动实施 MC/DFT 专属验收。

## 标定与效应

calibration.json：assertions 非空，三类 limit/invariant/paper 均需覆盖或在 not_applicable 中以类别名写不适用理由。

```json
{
  "not_applicable": {"paper": "本文只给完整曲线，无额外独立标定值；曲线由 loss 协议验证"},
  "assertions": [
    {"id":"C1", "category":"limit", "desc":"匹配单模导线", "kind":"value", "file":"data/mine/calibration.npz", "key":"T", "expect":1, "rtol":1e-8, "atol":1e-10},
    {"id":"C2", "category":"invariant", "desc":"幺正缺陷", "kind":"abs", "file":"data/mine/calibration.npz", "key":"unitarity_error", "expect":0, "atol":1e-8}
  ]
}
```

value 使用 `|x−expect| <= atol+rtol*|expect|`；abs/identity 仅用 atol；range 必填有限 min/max。数组标量断言用 index；空数组/非有限值不通过。支持 NPZ/JSON。

effect 配置：`{"file":"data/mine/pilot.npz","key":"y","expected_span":1.2,"uncertainty":0.1,"ratio_bounds":[0.8,1.2]}`。expected_span=0 时要求跨度不超过 uncertainty；非零时检查预期区间及不确定度，零结果不能以除零通过。先导实验不等于完整扫描。

## 图像协议

图像识别统一用 `scripts/vision.py`（OpenAI 兼容端点，默认 `https://api.12ai.org/v1`，默认模型链 `kimi-k2.6` → `kimi-k3`）：

```bash
python3 scripts/vision.py probe
python3 scripts/vision.py describe <img> -o <img>.vision.json
python3 scripts/vision.py audit  . data/ground_truth/fig1_crop.png --pdf paper/paper.pdf \
        --page 3 --bbox "50,100,300,400" --subfigure "Fig1(a)"
python3 scripts/vision.py judge  . fig1 --paper data/ground_truth/fig1_crop.png --mine figures/mine/fig1.png
```

凭据解析顺序：`--base-url/--model/--api-key` → `PAPER_REPRO_VISION_BASE_URL` / `PAPER_REPRO_VISION_MODELS` /
`PAPER_REPRO_VISION_API_KEY` → `OPENAI_BASE_URL` / `OPENAI_API_KEY` → `~/.pi/agent/models.json` 中同 host
的 provider。模型不可用（分组未开通）时自动回退下一个候选，并把 `model_requested` / `model_used` /
回退原因全部写进产物。**不联外网时**（端点不可达）仍可手写 `*.visual_audit.json`，但 `review.method` 只能是
`human`；写 `model` 会被 `check_visual_crop.py` 要求 `vision.model_used` + `vision.raw` 哈希。

裁切图 `fig1_crop.png` 对应 `fig1_crop.visual_audit.json`：

```json
{
  "image": {"file":"data/ground_truth/fig1_crop.png","sha256":"填实际哈希"},
  "pdf": {"file":"paper/paper.pdf","sha256":"填实际哈希"},
  "page": 3, "bbox_pdf": [50,100,300,400], "subfigure_id":"1a",
  "xaxis": {"label":"x","unit":"nm","limits":[0,1],"scale":"linear"},
  "yaxis": {"label":"R","unit":"kOhm","limits":[0,10],"scale":"linear"},
  "review": {"method":"model","reviewer":"kimi-k3","time":"ISO 时间","notes":"原页与裁切的子图、轴和刻度核对结论"},
  "vision": {"model_used":"kimi-k3","raw":{"file":"...fig1_crop.vision.json","sha256":"..."},
             "confidence":"high","uncertainty_notes":"模型自报的读不准项"}
}
```

`vision.py audit` 会自动写除人工覆盖项之外的全部字段：`--xlabel/--xunit/--xlims/--xscale` 与 `--ylabel/--yunit/--ylims/--yscale`
任一给出即记为 `model+override`；模型读不到量程时**直接报错而不猜**。坐标标定仍必须用
`digitize.py` 的像素刻度（`--xcal/--ycal`），**不得把模型输出的数值当数字化结果**。

visual 配置：`{"crop":"data/ground_truth/fig1_crop.png","mine_image":"figures/mine/fig1.png","plot_metadata":"figures/mine/fig1.plot.json","comparison_image":"figures/compare/fig1_side_by_side.png","min_visible":0.95}`。

plot 元数据含 image/data 两个 `{file,sha256}`、xkey/ykey、与裁切一致的 xaxis/yaxis、review（reviewer/time/notes）。必须由实际绘图参数生成，data 是实际绘图 NPZ。没有观测量通用正负限制。

并排脚本只生成，不审计。图像检查验证哈希、元数据、可见比例和已记录复核，不证明图像像素实际由声明数据生成。旧 overlay 入口只返回弃用提示；crop_anchors 是 crop 检查兼容入口，不声称执行 OCR。

### 论文图复现硬性要求（`paper_figure`）

目标 `paper_figure` 非空（如 `["Fig3(b)"]`）时，该数值计算必须在论文里有图，验收强制要求：

- `checks.visual.enabled=true` 且配置含 `crop`/`mine_image`/`plot_metadata`/`comparison_image`（`check_independence.py` 在 final 强制）；
- `figures/mine/<tid>.png`（+`*.plot.json`）由实际绘图数据生成，`check_figure_validity.py` 过（非空、非死线、可见比例达标）；
- `figures/compare/<tid>_side_by_side.png` 必须已由 `check_figure_side_by_side.py` 生成并真实存在（`check_figure_validity.py` 在 `stage=final` 强制），左栏为论文原图、右栏为复现图；
- `REPORT.md` §2 必须记录该并排对比产物（`check_report.py` 强制）。

真值来源可以与图不同（例如真值取表格/`published_data`，图用于形状与量级核对），但两者都要在 provenance 与目标里可追溯。`paper_figure=null` 是“该计算在论文中没有数值图”的声明；声明不实等同来源造假。

## 复现路线（Route A / Route B）

`project.json` 的 `official_code` 决定路线，`spec/provenance.json` 必须显式声明：

```json
"route": {"mode": "A", "basis": "作者随 arXiv 发布代码", "code_absence_check": []}
```

- **Route A**（`official_code=true`）：官方实现作建模期指导教练；若登记 `official_comparison` 参考，
  必须有成功运行绑定；若只在建模期用过代码、未做逐位对拍，在 `basis` 写明原因（`check_route.py` 会提示）。
- **Route B**（`official_code=false`，论文无官方代码）：
  1. `code_absence_check` 列出查过的位置（arXiv source / 作者主页 / GitHub 搜索 / 补充材料 / Zenodo 等）；
  2. 禁止出现 `official_comparison` 参考（没代码却用官方输出属来源造假）；
  3. 至少一个**印刷数值**来源（`paper`/`supplement`/`published_data`/`analytic`/`database`/`author_material`），
     不能只靠 `digitized` 图作唯一真值；
  4. `spec/calibration.json` 至少一条 `limit` 或 `invariant` 断言——这是官方实现缺席时的**替代预言机**；
  5. 每条 `digitized` 参考必须有视觉审计，`review.method=model` 时还须 `vision.model_used` + `vision.raw` 哈希；
  6. `stage=final` 时 `REPORT.md` 必须点名 Route B。

两条路线的验收标准相同（`check_loss` / `check_figure_side_by_side` / `check_figure_validity` /
`check_physics_code` 一个都不降级），只是可用预言机不同。`check_route.py` 在 stage≥calibrated 强制上述结构。

## 环境与运行

模拟进程输出 runtime.json：python（完整版本）、executable（实际解释器路径）、packages（名称到精确版本）、solver（实际入口，例如 scipy.linalg.solve）、dtypes（输出数组键到 dtype）、data（NPZ 的 file/sha256）。可追加随机数生成器、种子、硬件和锁定文件等字段。

environment.json 的 expected 填上述五项预期值，runtime 和 run 分别是运行元数据与 `runs/ID/manifest.json` 的 `{file,sha256}`。run 的 outputs 必须绑定 runtime.json 和对应 NPZ。记录器自己的环境另标为 recorder_environment，不能充当模拟环境。

缺 runtime.json 时**不要让用户去补**：写一个极小的 `code/bin/record_runtime.py`（跑一次真实求解器调用 + 存一个 dtype 见证 NPZ），用 `record_run.py --output data/mine/runtime.json --output data/mine/runtime_probe.npz` 绑定即可；见证文件必须自报 sha256，否则 `check_env` 会报 `hash mismatch`。

record_run 记录 code 下 Python 文件和 spec 下 JSON 快照、声明输入/输出、提交号（有 Git 时）、时间和日志哈希；失败也保存记录。声明的输出若已存在会拒绝启动，要求使用新的运行目录；这仍不能证明命令没有复制旧数据。它也不捕获所有外部文件/原生扩展，因此调用方必须声明输入。普通文件时间和本地哈希不是防篡改审计；严格历史证据需外部签名/可信时间戳。

## 来源和归因

provenance.json 包含 declaration（模式/来源声明）、official_metadata_used（官方资料使用列表，无则空）、references 和 comparisons。所有 loss.gt 都必须按规范化路径唯一注册。

每个 reference 必填：
- file/sha256：本地参考文件绑定。
- kind：paper（正文/表格）、supplement、published_data（作者发布的图表原始数据）、author_material（勘误/说明）、analytic、database、digitized（矢量或截图提取）、official_comparison（新运行官方代码的输出）。
- citation、version、locator、conditions、extraction：引用、版本、页/表/图/数据集定位、参数及适用条件、提取或转换步骤，均为非空字符串。版本不明需明确写“不明”及限制，不猜测。
- uncertainty（数据单位下的非负值）、uncertainty_basis：舍入/提取/统计等误差及依据；未知误差须先估计或保留未完成状态，不以零冒充未知。
- purposes：非空列表，取 calibration / validation / implementation_comparison；loss 的论文/基准目标需 validation，实现对拍目标需 implementation_comparison。
- used_for_tuning：显式布尔值；为 true 必填 reuse_disclosure，报告其非留出验收及影响。仅用于标定的参考不能默默充当最终验收。

论文正文参考例（仅演示）：

```json
{
  "file":"data/ground_truth/table1.csv", "sha256":"实际哈希", "kind":"paper",
  "citation":"DOI", "version":"发表版", "locator":"Table 1, row A",
  "conditions":"正文指定参数组 A", "extraction":"抄录并复核单位和有效数字",
  "uncertainty":0.005, "uncertainty_basis":"末位舍入半单位，单位与 y 相同",
  "purposes":["validation"], "used_for_tuning":false
}
```

对于多个观测量/不等误差，拆分参考记录与文件，并在数值协议中说明误差预算。reference_uncertainty 与来源误差须一致解释；检查器不能证明估计科学合理。

digitized 另需 fallback_reason（为何无可用数值来源），其目标必须启用 visual。论文图目标（`paper_figure` 非空）同样必须启用 visual 并绑定 `crop`/`comparison_image`（见“图像协议”）。

official_comparison 允许直接作为 loss.gt，但必须：
- official_code=true，文件在 comparisons/official/ 下，目标 validation_subject=author_implementation。
- run 为成功运行清单的 `{file,sha256}`，outputs 必须绑定该参考文件哈希；version 记录提交，conditions 记录配置/种子/环境和对应目标。
- independent 模式还需 baseline_run `{file,sha256}`；检查成功、基线快照及记录时间先后。paper/author 不要求先有独立基线，也不禁止直接导入作者代码。

comparisons 可为空；每项 baseline_run/comparison_run 都是 `{file,sha256}`，用于显式的迟到对拍。独立模式下有限 AST 导入启发式仍会报警；其余模式不把官方导入当作违规。本地记录和启发式不能证明没有提前阅读官方代码，也不能证明参考就是论文发表结果。

hypotheses.json：items 可为空但需 empty_reason。每项 id（H1 等）、claim、experiment、prediction、status（open/supported/falsified/retired）。supported/falsified 还需 premise、run（运行清单的 file/sha256）、evidence（列表，每项 file/sha256/metric/result）。falsified 需 retraction 及 LOG 中 `[RETRACT:H1]`。MD 叙述可保留，但 JSON 是机器检查来源。

## 复现报告（final 阶段交付物）

`stage=final` 时项目根必须有 `REPORT.md`（模板 `references/report_template.md`，校验 `check_report.py`）。
报告固定六节：结论摘要、逐目标结果、门禁与证据、局限与未完成项、复现方法、参考来源与调参披露。

§1 是一张含 `目标`/`判定`/`指标`/`证据` 的表格，每个 `project.json` 目标恰好一行，判定取
`定量符合`／`定性一致`／`未达标`／`未完成`。检查器对通过类判定做两件事：

1. `证据` 列必须是 `reports/*.json` 路径，且该 JSON 的 `target` 与判定行同名、`status` 为 `PASS`；
2. `指标` 列里至少有一个数字与那份 JSON 的某个数值指标相等（相对容差 1e-6）。

这条约束的作用是**禁止手写未经评分的数字**：报告只能复述已经落盘的评分结果。检查器不重算物理，
也不判断阈值是否科学——那是人工复核与 `check_loss`/`check_calibration` 的职责范围。

其余结构性要求：§2 至少列出三个实际运行过的 `check_*.py` 与绑定运行清单；§3 不得为空且必须逐条列出
局限（存在 `used_for_tuning=true` 的参考时须披露非留出验收）；§4 必须给出含 `python` 的可重跑命令；
§5 必须写明 `reproduction_mode`、逐条来源 `kind` 与不确定度，`digitized` 需说明回退理由。

判定为 `未达标`／`未完成` 的目标照常写入报告，不得为了凑齐全部通过而从 `project.json` 删除；
确需移除的目标必须在 §3 写明原因。`stage<final` 时缺少 `REPORT.md` 返回 NOT_APPLICABLE，不算失败。

## 自主复现轮与决策台账

默认工作方式是**一轮到底**：模型不逐步等人工拍板，而是遇到歧义就「决策—留痕—继续」，
跑到产出可评分的完整结果后再交给人评审一次。每次非平凡决策写入 `spec/decisions.json`，
并在 `LOG.md` 记 `[DECISION:Dn]`。`check_decisions.py`（stage≥calibrated）校验策略，不判物理：

- `chosen` 必须是 `options` 里的一个字面量（禁事后改变说法）；
- `impact=scope`（目标冻结后改目标集合）永远不得 `status=auto`；
  `impact=eligibility`（冻结前“无真值即剔除”的机械资格过滤）可 `status=auto`，但需给出排查依据；
- `impact=verdict` 且（`confidence!=high` 或 `reversibility=one-way`）不得 `auto`，必须 `escalated`；
- `reversibility=one-way` 需 `reverse_cost`；`escalated` 需 `escalation_reason`；
- `human_confirmed`/`human_overridden` 需 `human_review{by,date,note}`；
- `impact∈{verdict,scope,eligibility}` 或 `confidence=high` 需绑定证据（`file`+`sha256`+`metric`+`result`）或 `evidence_reason`。

字段取值：`rule ∈ {paper-literal, least-commitment, discriminator, consistency, analytic-limit, external-benchmark}`；
`impact ∈ {verdict, scope, numeric, convention, eligibility}`；`status ∈ {auto, escalated, human_confirmed, human_overridden}`；
`reversibility ∈ {reversible, one-way}`；`confidence ∈ {high, medium, low}`。空台账可写 `empty_reason`。

**目标资格过滤（自主，先于冻结）**：定义目标前逐对象过两道闸，路线由 `official_code` 决定：
（G1）真值闸（两条路线都必需）：至少一个可定位可哈希的真值来源（正文/表格数值、补充材料、`published_data`、
`analytic`/`benchmark`、数据库，或无数值来源时的 `digitized` 图）；
（G2）实现闸：有官方代码（`paper/refcode/` 或声明路径）→ Route A，官方实现作指导教练；
无官方代码 → Route B，**不剔除**，但要求 ① 至少一个印刷数值锚点、② 至少一条 `limit`/`invariant` 标定断言、
③ `route.code_absence_check` 登记检索位置。既无代码又只有数字化图且无任何退化极限者才剔除。
剔除记 `spec/decisions.json`（`impact=eligibility`、`status=auto`、`rule=least-commitment`，`basis` 列出查过的
真值来源与官方代码），并在 `REPORT.md` §3 说明路线与被剔除对象。此为冻结前机械过滤，不属 E3。

**升级条件**（只有这几种才允许打断自主轮，写入 `escalation_reason`）：
E1 需伪造数据/硬编码才能通过；E2 判定级歧义且做不出判别实验；E3 目标冻结后改目标集合；
E4 不可逆且影响判定且置信非高；E5 所有参考不可得。违反 E1 一律停：不存在“造假式通过”。

自主轮收尾（`stage=final`）交两份产物：`REPORT.md`（复现报告，见上）与 `REVIEW.md`（人工评审包，
由 `make_review.py` 从台账与评分报告生成，**禁手改**）。`check_review.py` 校验评审包不陈旧且覆盖
全部待裁决项；`check_report.py` 要求每个 `escalated` 决策被 `REPORT.md` §3 点名——自动流程
不得把开放问题埋在交付物里。

## 迁移旧项目

0. 先跑迁移器看差什么（默认 dry run，不改文件）：
   ```bash
   python3 scripts/upgrade_project.py <dir>            # [WOULD]/[EVIDENCE] 清单
   python3 scripts/upgrade_project.py <dir> --apply \
       --paper-figure <tid>=Fig2(a) --code-absence "arXiv source" --code-absence "GitHub search"
   ```
   它只写**机械可推导**项（如 `route.mode` 跟随 `official_code`、`route.basis` 写明代码在哪），
   并给每个被改文件留 `*.pre-upgrade-<UTC>` 备份；`[EVIDENCE]` 项（论文图 id、代码检索记录、
   数字化视觉审计）**永不自动写**——那属于来源造假。
1. 保留旧 Spec、LOG 和数据；另备份后运行 scaffold，只补缺失文件。
2. 将 A/B 拆成 level、official_code、reproduction_mode、逐目标 validation_subject、目标类型及阶段，不根据是否有代码自动推导等级。
3. 将旧 calibration 增加 category；清理宽泛区间，明确 N/A。
4. 将旧 loss CLI 参数迁入逐目标配置，明确单位/网格/覆盖率/不确定度；旧数据需补真实元数据，不凭猜测填写。
5. 补齐 provenance 的版本/定位/条件/误差/用途/调参披露；旧 official_comparison 可保留名称并作为参考，但需补运行绑定和相应验证对象；截图提取补 fallback_reason。
6. 旧 hypotheses.md 人工迁入 JSON，保留历史和原证据。重新运行可追溯计算后再声明验收。
7. 新增 `spec/decisions.json`：把迁移过程中做出的约定选择、参数取舍、目标增删逐条登记（含选项、规则、依据、可逆性、置信、影响），并在 `LOG.md` 补 `[DECISION:Dn]` 标记。

## 预注册锚点（spec/anchors.json）

`calibration.json` 答"我的代码自洽吗"，`anchors.json` 答"我的物理对得上论文吗"。后者必须在**第一次真实运行之前**落盘，
否则"跑完发现低 6%，把阈值放到 7%"在流程上完全合法——这是复现最常见的自证路径。

```json
{"items": [
  {"id": "A1", "quantity": "plateau_square_Mz0.4", "expected": 0.390, "unit": "e2/h",
   "tolerance": 0.01,
   "source": {"kind": "paper", "locator": "Fig.3(b) 平台段正文值"},
   "discriminates": "hard-wall vs periodic 边界条件",
   "status": "untested"}
]}
```

- `source.kind` 取 `paper` / `supplement` / `published_data` / `analytic` / `database` / `author_material`；`locator` 必须能定位到页/表/图。
- `tolerance` 是**看到结果前**写下的允差，必须 > 0。
- `status`：`untested` → `held` / `violated`。两者都要绑证据（`file` + `sha256` + `metric` + `result`，通常指向 `reports/<tid>.json`）；
  `violated` 还必须写 `resolution`（"为什么偏低/偏高"），并在 `REPORT.md` §3 披露。
- **指纹机制**：`record_run.py` 每次运行都把当时的 `spec/anchors.json` sha256 记进 `manifest.json` 的 `anchors_sha256`。
  `check_anchors.py` 取**最早**那份 manifest 作基线；当前哈希与之不符时，必须在 `spec/decisions.json` 提供一条
  `{"anchors_amendment": true, "rule": "discriminator", ...}`——即改动由判别实验驱动，而不是由结果驱动。
- `stage=final` 时不允许还有 `untested`。无 `anchors.json`、或最早 manifest 早于 v3（无该字段）时返回
  `NOT_APPLICABLE`，所以旧工作区不会被误判。

## 算力预算（spec/budget.json）

长扫描最容易变成"静默的 300 CPU-hour 作业"，或者把工具错误文案里的秒数当成真实上限。`check_budget.py` 只查结构：

```json
{"estimate": {"cpu_hours": 300, "planned_configs": 400, "basis": "8/3 n^3 * 20 layers * 150 pts / 1e9 * ..."},
 "paths_considered": ["缩尺寸 L=10", "换算法（块对角）", "GPU", "缩截面"],
 "chosen": {"configs": 300, "chunk_size": 25, "resume": true},
 "measured": [{"chunk": "c01", "done": 25, "run": {"file": "runs/R03/manifest.json", "sha256": "..."}}],
 "eta_hours": 9.8, "eta_basis": "measured 47.2 s/config from runs/R03", "churn_count": 2}
```

- `estimate.basis` 写算式，不写结论；`cpu_hours > 2` 时 `paths_considered` 至少两条。
- `chosen.chunk_size >= 1`、`resume` 显式布尔——长任务必须可续跑，不能靠 `nohup` + `tail` 黑箱推进。
- `measured[].run` 指向真实 `runs/*/manifest.json`（哈希校验）；`seconds` 缺省时用 manifest 的 `started`/`finished`。
- `eta_hours` 必须带 `eta_basis` 且引用实测（含 `measured`/`manifest` 字样）；偏离实测投影超过 2x 需要
  `{"budget_amendment": true}` 决策条目。
- `chosen.configs < estimate.planned_configs`（砍规模）同样需要该决策条目，并披露 `churn_count`。
- 不需要长扫描时写 `{"not_applicable": "<真实理由>"}`；scaffold 写的是 `TEMPLATE:` 前缀，`stage=final` 前必须落定。

## 产物台账（artifacts.jsonl）

```bash
python3 scripts/record_artifact.py <dir> figures/compare/fig3_side_by_side.png \
        --kind figure --target fig3 --note "左栏论文原图，右栏复现，VLM critique 已过"
python3 scripts/record_artifact.py <dir> --list
```

- append-only，按 **sha256** 去重（同一内容换个文件名不会重复计数）；`--supersede <path>` 记录取代边。
- `kind` 取 `figure` / `table` / `code` / `log` / `data` / `report` / `delivery`。
- `make_review.py` 把台账渲染成 `REVIEW.md` §6 的过程时间线；`reports/review.json` 里也带产物路径列表。
- 它不替代 `record_run.py`：前者记"产物是什么/取代了谁"，后者记"哪条命令产出它"。

## 失败归因表（record_run 的 failure_class）

失败必须分类，否则"重跑一次"会伪装成进展。失败记录建议补三个字段：

| 字段 | 取值 |
|---|---|
| `failure_class` | `convention`（约定/单位） · `numeric`（数值不收敛） · `runtime`（OOM/超时/被杀） · `tool`（工具或环境坏） · `blocked`（沙箱策略拦截） · `input`（输入缺失/格式错） |
| `retry_mode` | `retry_same`（原样重试） · `retry_param`（改参重试） · `reroute`（换路绕行） |
| `retry_reason` | 一句判别依据（哪条证据说明这次重试不是碰运气） |

- `retry_same` 连续出现 >= 2 次必须有理由，否则视为盲重跑（`audit_self.py` 会统计）。
- `blocked` 不是代码错误：先在 `LOG.md` 记下被拒的操作与替代路径，再改策略（例如后台进程被拒时改用前台分块）。
