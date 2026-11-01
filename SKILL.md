---
name: humanrizeai
description: "通过 humanizeai.pro 将长文分批降 AI（每批不超过 200 words），保存进度并合并，再结合原文与全文审查逻辑、事实及上下文，只作必要的最小修正后交付。用于用户指定此网站的批量改写请求。"
---

# humanrizeai

完整流程：**保存原文 → 网站分批处理 → 合并网站原始输出 → 全文审查 → 必要的最小修正 → 复读确认 → 导出最终版**。网站处理结束不能作为任务结束。所有正常交付都必须经过审查，即使最终无需修改。

网站原始结果必须来自 https://www.humanizeai.pro/ 。之后的本地修正属于审查步骤，需要记录，不能把本地重写或其他服务输出当作网站原始结果。

## Start a job

Resolve `scripts/humanize_batch.py` relative to this skill. It requires Python 3.10+, Node/npm (`npx`), and Chrome; there are no Python package dependencies. Discover available equivalents if executable names differ. On first use `npx` may download `@playwright/cli`. If Chrome is unavailable, inspect Playwright CLI's browser options instead of repeatedly retrying.

1. Save the supplied text as UTF-8 under the task's `work/` folder, or read the provided plain-text file. For Word/PDF input, extract with the appropriate document tool first and explain that this workflow returns text, not original document layout. Do not infer which document to process if none is supplied.
2. Create a new job directory under `work/`:

   ```text
   python "<skill>/scripts/humanize_batch.py" prepare --input "<input.txt>" --job "<work/job>"
   python "<skill>/scripts/humanize_batch.py" run --job "<work/job>"
   ```

   The default is 180 conservative word units, with each CJK character counted separately. The hard configurable maximum is 200. Splits prefer paragraphs and sentence endings; an overlong sentence is split at a word boundary. Do not add overlap or context to submissions. Use the site's free default settings unless the user requests another available setting; the helper leaves browser settings unchanged.
3. Run with a yielding shell tool and poll its session. It prints progress for every saved batch. Do not run two workers on one job. The job has an isolated visible browser session; leave it available if the user must complete a challenge.
4. `run` resumes the same job, skips saved results, and checks a pending submission before doing anything new. It never automatically resubmits an ambiguous timeout. Requests are sequential, with a three-second gap. Do not rotate identities, bypass access controls, or increase parallelism to overcome site limits.

## Interruptions and UI changes

The verified UI labels are `Input Textarea` (input), `Humanize AI` (submit), and `Humanized output` (output textarea). Read the output's **value**, which excludes the visual change-highlighting layer. Cookie `Decline` and the optional onboarding `Skip` can be dismissed. These labels were verified on 2026-11-01; take a fresh snapshot when a locator fails and adapt to the actual interface.

The helper stops and preserves progress for a visible CAPTCHA, quota/login/payment prompt, timeout, or unexpected UI. Ask for only the action actually needed. A static reCAPTCHA footer is not a challenge. Do not claim completion or silently replace a failed chunk with its original.

- After the user resolves a challenge, run the same command again to recover any completed output.
- If a pending request demonstrably never completed, inspect the current UI before using `retry --job "<job>" --index N`. This clears only that pending submission; then rerun. At most two submissions per chunk are allowed. A quota/login/payment interruption requires resolution, not a blind retry.
- For browser-tool fallback, inspect `status`, use `job.json` for the exact next chunk, fill and submit through the available browser tool, wait for completion, and save **only verified website output** as UTF-8. Record it using `accept --job "<job>" --index N --text-file "<result.txt>"`. Do not copy display diffs, old output, or marketing text. The helper rejects empty or conflicting results.

## 必经的全文审查与最小修正

所有网站批次保存后，执行：

```text
python "<skill>/scripts/humanize_batch.py" review-prepare --job "<work/job>"
```

接下来**阅读并遵循 [references/review-and-repair.md](references/review-and-repair.md)**。它规定完整审查范围、最小修正规则、审查记录格式和确认步骤。

同时阅读 `review/source.txt` 和 `review/website-raw.txt`，结合全文而非只看孤立批次，检查逻辑与因果、事实/数字/单位/否定关系、人物和指代、时序、前后论点、遗漏以及分批边界。对长文可分段阅读，但须覆盖全文，并带着全局事实和上下文回查边界。

只修正有证据的明显问题；以网站生成版为底稿，保留未出错部分的措辞、语序和语气，采用能修好问题的最小替换。漏掉关键限定或句子时，只补足必要信息。不要顺手润色、统一文风、扩写、调整全篇结构或回退成整篇原文。不要为降低检测分数保留事实或逻辑错误，也不要声称最小修改能保证检测分数不升。

审查由当前 Codex 完成；脚本不调用独立语义检测模型，只校验审查记录、精确应用修正并强制执行交付条件。无需另行询问是否允许修正，用户已授权此完整流程。

## 最终交付

按审查协议应用修改，通读修正后的全文，确认修正未引入新冲突，再登记复读。`export` 只允许导出与已确认审查对应、且没有未解决问题的最终文本；旧任务也需要补做审查。

```text
python "<skill>/scripts/humanize_batch.py" export --job "<work/job>" --output "<outputs/name-humanized-final.txt>"
```

保留原文、网站原始结果、逐项修改理由及审查记录，输出新文件。简短告诉用户已做全文审查、修改了几处及修改类型；无修改则明确说明无需修正。只有最终版已成功导出才能宣称整个任务完成。存在无法证实的实质疑点时，保留已完成工作、说明具体问题，必要时向用户确认；不擅自猜改，也不把未完成审查的草稿当最终版。如果没有原文，只完成技能设置并给出调用示例，不虚构处理任务。
