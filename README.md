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

# 2) 填 spec/ 与 spec/project.json 的 null；stage 走 planning -> calibrated -> final
python3 scripts/validate.py work          # 逐项跑 check_*，输出 PASS/FAIL/INCOMPLETE

# 3) 视觉读数（OpenAI 兼容端点，默认 kimi 模型链）
export PAPER_REPRO_VISION_API_KEY=...      # 或 OPENAI_API_KEY / pi models.json
python3 scripts/vision.py describe crop.png -o read.json
python3 scripts/vision.py audit work crops/Fig1a.png --pdf paper.pdf --page 3 \
    --bbox 120,340,480,620
```

`validate.py` 的退出码即汇总状态（`PASS`=0 / `FAIL`=1 / `INCOMPLETE`=2），可直接进 CI。

## 目录

```
SKILL.md              技能主文档（流程、闸门、升级条件）
references/           协议、检查清单、报告/规格模板、领域档案
scripts/              scaffold / validate / check_* / vision / digitize / make_review ...
tests/                75 个 unittest 回归用例
reports/              示例审计产物
CHANGELOG.md          版本演进（当前内容版本 v2.8）
```

## 版本

Git tag **v1** = 本仓库首次公开发布，对应技能内容 **v2.8**（「去掉流程里的人」版：人的介入只剩
`REVIEW.md` 签署与 E1–E5 升级两处）。之后 GitHub tag 独立编号，内容版本继续在 `CHANGELOG.md` 里递增。

## 测试

```bash
python3 -m unittest discover -s tests -q    # 75 tests, ~35s
```

## 许可证

MIT，见 `LICENSE`。
