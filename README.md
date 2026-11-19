# paper-repro

> 复现数值物理论文的**定量输出**（曲线图 / 表格 / 文中数值断言），并给出可审计的归因。
> 一个 [pi](https://github.com/earendil-works/pi) 的 skill 包（`SKILL.md` + 脚本 + 校验器 + 测试）。

`paper-repro` 不做「跑个代码看起来差不多」，它把复现拆成**可判定的闸门**：真值来源、路线选择、
校准锚点、特征分辨率、视觉读数、纠错台账、人工签署，每一项都有对应 `scripts/check_*.py`
在 `validate.py` 里强制校验，不过就停下来。

---

## 它解决什么

复现失败的典型死法有三种，本 skill 针对性地设卡：

| 死法 | 卡点 |
|---|---|
| **死线 / 空图 / 假拟合** —— 拟合论文图代替物理求解 | `check_loss.py`、`check_physics_code.py`、`check_figure_validity.py` |
| **对不上却说不清为什么** —— 只报「不匹配」 | `check_hypotheses.py`、`check_effect.py`：偏差必须绑定可检验假设 + 效应量 |
| **读数全靠人眼/模型嘴** —— 图上量随口报 | `check_visual_crop.py`：模型读数须带 `vision.raw` 哈希与真实应答模型名 |

## 两条路线

- **Route A（论文有官方代码）**：官方实现只作*指导教练*——提炼测量拓扑、引线角色、势能形态、
  电导矩阵数学映射，主 Agent 独立重写 Pipeline。**禁止直读/复制源码**，`check_independence.py` 校验。
- **Route B（无官方代码）**：以论文正文/表格/补充材料里的**印刷数值**为主真值，辅以解析极限与守恒
  关系充当预言机，`vision.py` 补齐图上的量。`check_route.py` 强制声明路线并禁止 B 路线出现
  `official_comparison`。

两条路线验收标准相同，见 `references/protocol.md`。

## 安装

```bash
# 作为 pi user skill
cp -r paper-repro ~/.pi/agent/skills/

# 或项目级
cp -r paper-repro <project>/.pi/skills/
```

依赖：Python ≥ 3.10，`numpy` 必需；`scipy` / `Pillow` / `matplotlib` 按用途可选
（`record_run.py` 会记录实际探测到的版本，`check_env.py` 校验环境快照）。

## 用法

```bash
# 1) 建工作区；--official-code 决定 Route A / B
python3 scripts/scaffold.py work --title 'Paper X Fig.1 复现' --level standard --official-code

# 2) 每轮只做 next.py 指的那一件事（唯一 NEXT；为什么要它看 --why）
python3 scripts/next.py work --why

# 3) 填 spec/ 后升 stage；升 stage 前跑全量验收
python3 scripts/validate.py work          # 逐项跑 check_*，输出 PASS/FAIL/INCOMPLETE

# 4) 视觉读数（OpenAI 兼容端点，默认 kimi 模型链）
export PAPER_REPRO_VISION_API_KEY=...      # 或 OPENAI_API_KEY / pi models.json
python3 scripts/vision.py describe crop.png -o read.json
python3 scripts/vision.py audit work crops/Fig1a.png --pdf paper.pdf --page 3 \
    --bbox 120,340,480,620
python3 scripts/vision.py critique work fig3 --paper crops/Fig3.png
```

`validate.py` 的退出码即汇总状态（`PASS`=0 / `FAIL`=1 / `INCOMPLETE`=2），可直接进 CI。

## v3 新增的三个机制

| 机制 | 文件 | 解决的问题 |
|---|---|---|
| **唯一的下一步** | `scripts/next.py` | 模型自己排步骤导致同一决定反复改（churn）；现在只输出一行 `NEXT:` |
| **首跑前的尺子** | `spec/anchors.json` + `check_anchors.py` | 看完结果再放宽允差；锚点在首个 `manifest.json` 里哈希锁定 |
| **算力与过程可回溯** | `spec/budget.json` + `check_budget.py`、`artifacts.jsonl` + `record_artifact.py` | 静默 300 CPU-h 作业、把超时文案当 ETA、产物按文件名重复计数 |

另有 `scripts/audit_self.py`（只读自审：盲重跑 / 决策 churn / 未钉产物的目标），
只用来挑下一个优化，**不进 `validate.py`**。

## 目录

```
SKILL.md              技能主文档（8 条红线 + 推进方式；≤160 行，长文按需取）
references/           协议、索引、踩坑清单、报告/规格模板、领域档案、v2.8 存档
scripts/              next / validate / check_* / vision / digitize / make_review ...
tests/                89 个 unittest 回归用例
reports/              示例审计产物
VERSION               当前发布标签（唯一编号来源，配合 CHANGELOG 顶部的对照表）
CHANGELOG.md          版本演进（每节标注「发布标签 / 开发线」）
```

## 版本

**发布标签**写 `VERSION`（今天 `v3`），**开发线**写 `CHANGELOG.md` 顶部对照表。
每个条目标题形如「发布标签 `v2` / 开发线 `v3.0`」，`selfcheck.py` 会强制这两者一致。

- tag `v1` = 首次公开发布，对应开发线 v2.8（人的介入只剩 `REVIEW.md` 签署与 E1–E5）。
- tag `v3` = 当前发布，对应开发线 v3.1（E2 付款规则：`escalated` 必须列判别实验与成本）。
- tag `v2` = 开发线 v3.0（`next.py` / `anchors` / `budget` / `artifacts` / SKILL 瘦身）。

## 测试

```bash
python3 -m unittest discover -s tests -q    # 89 tests, ~35s
python3 scripts/selfcheck.py                # 结构 + 版本标注 + 路由覆盖 + 全套回归
```

## 许可证

MIT，见 `LICENSE`。
