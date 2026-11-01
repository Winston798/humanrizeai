# 全文审查与最小修正协议

在网站批次全部保存后使用。由 Codex 连续完成以下操作，不把填写审查记录交给用户。

## 审查范围与依据

读取 `review-prepare` 生成的完整原文 `review/source.txt`、网站合并稿 `review/website-raw.txt` 和 `job.json` 中的批次对应关系。通读全文并对照：

- 逻辑：因果反转、推论与前提不符、条件/例外消失、否定或可能性变成肯定。
- 事实：名称、角色、时间、地点、数字、单位、数量级、比较方向、引用和关键事实是否变了。
- 上下文：前后主张矛盾、术语指向变化、人物/代词错配、时序错乱、分批边界的句子或衔接失去含义。
- 遗漏：支撑后文的前提、限制、结论、必要句子是否丢失；识别凭空添加的断言。

本轮目标是修复**网站处理引入的错误**，不扩展为原文全面纠错。原文用于确认用户本意，不是外部事实的绝对真理。原文已有的问题或疑点记在 `source_notes`，不混入自动修正，也不单独阻止最终交付。只有为判断网站是否引入实质错误确需外部事实时，才作必要的第一手资料核实；不凭印象补造数据、引文或事实。

## 自动修正门槛

每项修正必须同时确认：

1. `introduced_by_website: true`：问题在网站稿中新出现，原文没有该错误。
2. `certain_error: true`：有具体证据证明是错误，不是语感偏好或猜测。
3. `material_impact: true`：会改变读者对事实、条件、逻辑或前后文的理解。
4. `reader_impact`：具体回答“如果不改，读者会误解什么”。没有明确答案就移除该修正。

缺少任何一项，不自动改正文。可接受的不同表述、轻微生硬和非关键细节遗漏保持网站原样；如有必要说明，记在 `observations`。只有尚不能判定的网站新增实质问题才列入 `unresolved` 并阻止最终确认，不把原文问题和无害差异放进去。

## 最小修改

以网站合并稿为底稿，**默认保留句子结构**。优先顺序：单词/数字 → 局部短语 → 必要片段的补删 → 局部无法修复时才调整句式。结构调整须声明 `structure_changed: true`，并在 `structure_reason` 说明为什么保留原结构无法消除错误。仅仅更通顺、更正式不构成结构调整理由。

遗漏仅在造成事实失真、逻辑断裂、关键条件消失或后文无法理解时才补。不要因为原文有某个细节就补回，例如载体差异不影响文章含义时，不因原文写了“纸质时刻表”就自动把网站的“时刻表”补成“纸质时刻表”。可以删除网站凭空添加、且确定造成实质含义错误的内容。

保留未受影响部分的词汇、句式、段落顺序和语气。不顺带润色，不补通用过渡句或总结，不重写全文。应用前逐项做必要性复查：不改会产生什么具体误解？是否能用更小且充分的修改修好？确认后登记 `necessity_rechecked: true`。先确定修正清单，再应用；最终复读只检查错误是否消除以及修正是否引入新问题，不再寻求更好的表述。若仍有确定的实质错误，仍须修复并重新复读；不能无限优化措辞。不要把整篇修正版再次交给网站循环改写，除非用户另行要求。

最小修改的目的是尽量保留网站处理后的表达；没有内置检测分数验证，不能保证 AI 率变化。事实和逻辑正确性优先于揣测检测分数。

## 记录、应用与复读

1. 复制 `review/report-template.json` 为工作报告（如 `review/authored-report.json`），保留 `version: 2` 和原文/网站稿 SHA-256。完成后将九个 `checks` 置为 `true`：六项全文内容检查，以及 `necessary_edits_only`（逐项必要性复查）、`original_structure_preserved_or_justified`（保留句式或充分说明例外）、`source_issues_separated`（原文疑点已分离）。`summary` 写实际结论，无问题也必须有结论。
2. `edits` 为必要修正数组。每项格式：

   ```json
   {
     "category": "fact",
     "before": "website draft exact text",
     "after": "minimally corrected text",
     "reason": "What was wrong and why this is the smallest sufficient repair.",
     "evidence": "Source quotation/location proving the website introduced the error.",
     "introduced_by_website": true,
     "certain_error": true,
     "material_impact": true,
     "reader_impact": "The concrete factual or logical misunderstanding if this text remains unchanged.",
     "necessity_rechecked": true,
     "structure_changed": false
   }
   ```

   `category` 可用 `logic`、`fact`、`context`、`omission`、`reference`、`terminology`。若 `structure_changed` 为 `true`，必须另填非空的 `structure_reason`。`before` 精确匹配**未修改的网站合并稿**，默认要求唯一出现；重复时扩大定位片段但只改必要部分，或提供零起始 Python 字符位置 `start`。所有修正锚定原始网站稿，范围不能重叠；允许跨批次定位。用于定位的长片段不代表其中所有文字都发生了改动。
3. 插入必要信息时用现有邻近文字作定位，`after` 保留它并只加必要内容；删除时 `after` 可为空。无问题用 `edits: []`。报告中 `source_notes`、`observations`、`unresolved` 都是文本数组，按上述范围分开填写，无项时为 `[]`。
4. 应用报告：

   ```text
   python "<skill>/scripts/humanize_batch.py" review-apply --job "<work/job>" --report "<authored-report.json>"
   ```

   程序保留网站原始结果，在 `review/report.json` 保存记录，在 `review/corrected-draft.txt` 生成修正稿，并在 `review/change-summary.json` 记录实际变化片段、增删字符数及声明的句式调整数量。没有按任意百分比限制修改；统计仅供核对，不等于 AI 分数或自动最小性证明。报告缺少必要确认/理由、使用旧策略、指向旧稿或修正定位有误时拒绝。
5. 通读 `corrected-draft.txt` 并看实际改动记录，仅核查确认的错误已解决、修改必要且没有新问题。发现某项只是表述优化时从报告移除，重新应用并复读。有未解决的网站新增实质问题不能确认完成；原文疑点和非关键差异仅备注。程序只校验记录完整和文本一致，不能替代 Codex 的证据判断或自行证明句式未变。
6. 确认复读的是同一份修正稿，使用 `review-apply` 输出的 SHA-256 和实际复读结论：

   ```text
   python "<skill>/scripts/humanize_batch.py" review-complete --job "<work/job>" --confirmed-sha256 "<draft-hash>" --note "<actual final contextual reread conclusion>"
   ```

   这条命令是 Codex 对已完成复读的明确登记，不是自动语义检测。不能只运行命令而跳过阅读。
7. 最后 `export` 并检查 `status`。只有 `workflow_complete: true` 才可宣称任务完成。最终正文不插入校对批注；回复中简短说明结论和必要修正数量。网站原始稿与审查细节保存在任务目录供核对。

## 恢复和旧任务

原有任务及网站结果继续保留，不重跑网站；缺少审查记录时进入 `review_required`。旧版审查报告不能直接沿用：重新 `review-prepare`，按版本 2 策略重新评估，不机械把旧确认改成新确认。修改报告或修正稿后重新应用并复读。审查中断从已保存材料继续，不重复提交网站。
