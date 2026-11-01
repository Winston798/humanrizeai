<div align="center">

# humanrizeai

**在 Codex 中自动分批处理长文，全文审查后作最小修正。**

<p>
  <a href="SKILL.md"><img src="https://img.shields.io/badge/Codex-Skill-0F766E?style=flat-square" alt="Codex Skill"></a>
  <a href="#安装"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10 or newer"></a>
  <a href="scripts/humanize_batch.py"><img src="https://img.shields.io/badge/Playwright-Web_Automation-2EAD33?style=flat-square" alt="Playwright web automation"></a>
  <a href="references/review-and-repair.md"><img src="https://img.shields.io/badge/Review-Full_Context-8B5CF6?style=flat-square" alt="Full context review"></a>
  <a href="references/review-and-repair.md"><img src="https://img.shields.io/badge/Edits-Minimal-F59E0B?style=flat-square" alt="Minimal edits"></a>
</p>

通过 [humanizeai.pro](https://www.humanizeai.pro/) 网页逐批处理文字，保存进度，合并结果；
再由 Codex 对照原文与全文上下文，只修复网站引入、确定且影响含义的错误。

[快速使用](#快速使用) · [安装](#安装) · [工作流程](#工作流程) · [审查协议](references/review-and-repair.md) · [反馈问题](https://github.com/Winston798/humanrizeai/issues)

</div>

---

## 快速使用

安装后，在 Codex 中附上文本文件或粘贴原文，然后说：

> 使用 $humanrizeai，把这篇文字通过 humanizeai.pro 分批处理并审查全文，只修网站引入、确定且影响含义的错误，默认保留句式，逐项复查修改必要性后复读交付。

Codex 会运行网页处理、记录进度并完成审查，你不需要逐段复制，也不需要手动填写审查报告。

## 能做什么

| 能力 | 实际行为 |
| :--- | :--- |
| **自动分批** | 默认每批最多 180 个保守计数单位，配置上限 200；优先保留段落和句末 |
| **中断后继续** | 每批保存原文与网站结果，恢复时跳过已完成批次，先检查待确认提交 |
| **全文审查** | 对照原文，检查逻辑因果、事实数字、否定关系、指代、遗漏和跨批次矛盾 |
| **保守修正** | 只修网站引入、确定且影响含义的错误；默认保留句式，不补非关键遗漏 |
| **修改可追溯** | 保留原文、网站稿、修正稿、必要性与依据，以及实际改动片段和增删字符数 |
| **完整交付检查** | 未登记审查、未确认复读或仍有未解决问题时，程序拒绝导出最终版 |

英文主要按空白分隔的词块计算，中日韩文字按字符保守计数；该计数不等同于网站的精确计数器。

## 安装

**需要：** Python 3.10+、Node.js/npm（提供 `npx`）和 Chrome。

将仓库克隆到 Codex 的用户技能目录，文件夹命名为 `humanrizeai`。下面使用本技能的默认安装路径 `~/.codex/skills`；如果已配置其他技能目录，请改用实际路径。

<details open>
<summary><strong>Windows · PowerShell</strong></summary>

```powershell
git clone https://github.com/Winston798/humanrizeai.git "$env:USERPROFILE/.codex/skills/humanrizeai"
```

</details>

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
git clone https://github.com/Winston798/humanrizeai.git ~/.codex/skills/humanrizeai
```

</details>

重新打开 Codex 后，使用 `$humanrizeai` 调用。如果目标文件夹已经存在，请先检查现有安装，避免覆盖未保存的修改。

无需额外 Python 包；首次运行可能通过 `npx` 下载 `@playwright/cli`。网页定位在 Windows / Chrome 环境实测，其他平台可能需要调整浏览器配置。

## 工作流程

**保存原文 → 网页分批处理 → 合并网站稿 → 全文审查 → 最小修正 → 复读确认 → 导出最终版**

1. **处理原文。** 保存文字，按段落和句末切分，通过网页顺序提交，并记录每批结果。
2. **审查全文。** Codex 同时阅读原文和网站合并稿，结合前后文识别明显的逻辑、事实及语义问题。
3. **必要性复查与局部修复。** 每处修改先回答“不改会让读者具体误解什么”；答不出就撤销。优先改词或局部短语，句式调整必须说明为什么局部措辞修正无法解决。
4. **复读交付。** 只核查确认的错误是否解决、修正是否引入新问题，不再优化表述，之后导出新的 UTF-8 文本文件。无问题时允许零修改。

网站处理完成只是中间阶段。语义审查由 **Codex** 执行，程序负责精确应用修改、检查记录和稿件是否一致，并执行最终导出条件。

### 修正尺度

| 情况 | 处理 |
| :--- | :--- |
| 网站引入的确定错误，会造成事实、逻辑或上下文误解 | 有明确依据时作最小修正 |
| 同义改写、轻微生硬、非关键细节遗漏 | 保留网站表达，必要时仅备注 |
| 原文本身已有的问题或疑点 | 单独记录，不混入本轮自动修正 |
| 尚不能判定的网站新增实质问题 | 保留疑点，解决前不导出最终版 |

补回遗漏仅限事实失真、逻辑断裂、关键条件消失或后文无法理解的情况。默认保留句子结构，不为流畅、正式或文风统一改写。没有固定修改百分比；实际增删统计用于核对范围，不代表 AI 检测分数。

## 文件结构

```text
humanrizeai/
├── SKILL.md                        # Codex 的完整执行规则
├── agents/
│   └── openai.yaml                  # 界面名称、简介与调用示例
├── references/
│   └── review-and-repair.md         # 全文审查与最小修正协议
└── scripts/
    └── humanize_batch.py            # 分批、网页操作、进度与交付检查
```

| 文档 | 内容 |
| :--- | :--- |
| [技能说明](SKILL.md) | 如何开始任务、处理中断、执行审查和交付 |
| [审查与修正协议](references/review-and-repair.md) | 审查范围、最小修改边界及修改记录格式 |
| [自动化脚本](scripts/humanize_batch.py) | 网页批处理、任务恢复、审查登记和最终导出 |

<details>
<summary><strong>查看脚本命令</strong></summary>

| 命令 | 用途 |
| :--- | :--- |
| `prepare` / `run` / `status` | 创建任务、运行网页处理、查看完整流程状态 |
| `accept` / `retry` | 浏览器工具接手后登记结果，或检查后恢复提交 |
| `review-prepare` | 生成原文、网站稿和审查报告模板 |
| `review-apply` | 校验修正记录，生成独立修正稿 |
| `review-complete` | 登记对指定修正稿的最终复读 |
| `export` | 检查完整流程后导出最终版 |

</details>

当前审查报告格式为 **v2**，需记录错误来源、确定性、实质影响、修改必要性以及句式调整理由。已有任务的网站结果可继续使用；旧版审查报告需按新规则重新审查，不会自动沿用旧确认。

## 使用范围与数据

- **验证码与限制：** 出现验证码时，在打开的浏览器中完成验证后让 Codex 继续。额度、登录、付费限制或超时会保留进度，不绕过访问限制。
- **文件格式：** 默认处理和交付文本。Word/PDF 需要先提取文字，不恢复原始排版。
- **任务数据：** 原文、网站输出、进度和审查记录保存在本地任务工作目录；每批待处理文字会提交至指定网站。公开仓库不包含任务数据或浏览器会话。
- **审查边界：** 脚本没有独立的语义检测模型；最小修改旨在保留网站处理后的表达，不保证 AI 检测分数。
- **网页变化：** 网站布局或免费使用限制改变后，可能需要更新定位或操作步骤。

---

需要了解执行细节，请阅读 [SKILL.md](SKILL.md)。遇到问题，可在 [Issues](https://github.com/Winston798/humanrizeai/issues) 中描述复现步骤，并移除原文、浏览器记录中的私人信息。
