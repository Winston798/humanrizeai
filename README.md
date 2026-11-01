# humanrizeai

一个 Codex skill，通过 [humanizeai.pro](https://www.humanizeai.pro/) 的网页分批处理长文，保存进度并合并；随后由 Codex 结合原文和全文审查逻辑、事实与上下文，作必要的最小修正，复读后交付最终版。

## 完整流程

保存原文 → 网页分批处理 → 合并网站原始输出 → 全文审查 → 最小修正 → 复读确认 → 导出最终版。

- 默认每批最多 180 个保守计数单位，上限可配置但不超过 200；中日韩文字按字符保守计算。
- 逐批提交，自动保存每批原文和网站结果，支持中断后继续。
- 检查逻辑因果、事实和数字、否定关系、指代、前后矛盾、遗漏及跨批次衔接。
- 以网站结果为底稿，仅修正有依据的明显错误，保留未出错部分的措辞和语气。
- 分别保存原文、网站原始稿、修正稿和每项修改理由。
- 程序拒绝未登记审查、未确认复读或仍有未解决问题的最终导出。

## 安装

将本仓库克隆到 Codex 的用户技能目录，并将文件夹命名为 `humanrizeai`。本技能使用的默认目录为 `~/.codex/skills`；如已配置其他技能目录，请使用实际路径。

Windows PowerShell：

```powershell
git clone https://github.com/Winston798/humanrizeai.git "$env:USERPROFILE/.codex/skills/humanrizeai"
```

macOS / Linux：

```bash
git clone https://github.com/Winston798/humanrizeai.git ~/.codex/skills/humanrizeai
```

如果目标文件夹已经存在，请先检查现有安装，不要覆盖未保存的本地修改。重新打开 Codex 后调用技能。

运行环境需要 Python 3.10+、Node.js/npm（提供 `npx`）和 Chrome。没有额外 Python 包依赖；首次运行可能下载 `@playwright/cli`。网页定位在 Chrome / Windows 环境实测，其他平台可能需要调整浏览器配置。

## 使用

在 Codex 中粘贴原文或附上文本文件，然后说：

> 使用 $humanrizeai，把这篇文字通过 humanizeai.pro 分批处理，结合原文和全文审查逻辑、事实与上下文，作必要的最小修正并复读后交付最终版。

Codex 会读取技能说明、运行辅助脚本并完成审查，不需要使用者手动填写报告。Word/PDF 需要先提取文字，默认交付新的 UTF-8 文本文件，不恢复原文档排版。

如果出现验证码，需要在打开的浏览器中手动完成，再让 Codex 继续。额度、登录、付费限制或超时会保留进度；不会绕过访问限制。

## 结构

```text
humanrizeai/
├── SKILL.md                        # Codex 的完整执行规则
├── agents/openai.yaml              # 技能名称、简介和调用示例
├── references/review-and-repair.md  # 全文审查及最小修正协议
└── scripts/humanize_batch.py        # 分批、网页操作、进度和交付检查
```

脚本提供 `prepare`、`run`、`status`、`accept`、`retry`、`review-prepare`、`review-apply`、`review-complete` 和 `export`。完整操作要求见 [SKILL.md](SKILL.md)，审查与修正格式见 [审查协议](references/review-and-repair.md)。

每次任务的数据保存在使用者自己的工作目录：包括 `job.json`、原文、网站输出、审查报告和修正稿。该公开仓库不包含任何任务数据或浏览器会话；实际使用时，每批待处理文字会提交至指定网站。

## 审查与能力边界

语义审查和最小修正由 Codex 执行；Python 脚本负责精确应用修改、检查记录与稿件一致性，以及限制最终导出。它没有独立的语义检测模型，也不能证明所有事实都已核实。无问题时允许零修改，但仍需审查和复读。

最小修改旨在尽量保留网站处理后的表达，不保证 AI 检测分数。网站布局或免费使用限制变化时，可能需要更新网页定位或操作步骤。
