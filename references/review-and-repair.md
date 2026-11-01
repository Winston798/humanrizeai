# 全文审查与最小修正协议

在网站批次全部保存后使用。由 Codex 连续完成以下操作，不把填写审查记录交给用户。

## 审查范围与依据

读取 `review-prepare` 生成的完整原文 `review/source.txt`、网站合并稿 `review/website-raw.txt` 和 `job.json` 中的批次对应关系。通读全文并对照：

- 逻辑：因果反转、推论与前提不符、条件/例外消失、否定或可能性变成肯定。
- 事实：名称、角色、时间、地点、数字、单位、数量级、比较方向、引用和关键事实是否变了。
- 上下文：前后主张矛盾、术语指向变化、人物/代词错配、时序错乱、分批边界的句子或衔接失去含义。
- 遗漏：支撑后文的前提、限制、结论、必要句子是否丢失；识别凭空添加的断言。

以原文确认用户本意和网站引入的变化。原文不是外部事实绝对正确的证明：若疑点涉及外部事实且不能从材料确定，使用可靠的第一手资料核实，并记录依据；不要凭印象补造数据、引文或事实。无法确定的实质问题列入 `unresolved`，不猜改。无害同义改写、可接受的不同表述不算错误。

## 最小修改

以网站合并稿为底稿。先判断问题是否确实存在，再选择最小修补范围：一个数字、否定词、名称、指代、必要的连接词或最短的受影响短语；只有局部替换无法修复时才改一句。补回遗漏信息时使用与周边一致的简单表达，不机械还原整段原文。可删除网站凭空添加的错误内容。

保留未受影响部分的词汇、句式、段落顺序和语气。不为“更流畅”“更专业”做顺带润色，不新增通用过渡句或总结，不把全文重新生成。修正完成后回读相邻段落及全文，确认没有新矛盾或指代断裂。不要再次把整篇修正版交给网站循环改写；如用户另行要求才改变流程。

最小修改的目的是尽量保留网站处理后的表达；没有内置检测分数验证，不能保证 AI 率变化。事实和逻辑正确性优先于揣测检测分数。

## 记录、应用与复读

1. 复制 `review/report-template.json` 为工作报告（如 `review/authored-report.json`），保留原文/网站稿 SHA-256。完成相应检查后将六个 `checks` 置为 `true`。`summary` 写实际审查结论；无问题也必须有结论。
2. `edits` 为必要修正数组。每项格式：

   ```json
   {
     "category": "fact",
     "before": "website draft exact text",
     "after": "minimally corrected text",
     "reason": "What was wrong and why this is the smallest sufficient repair.",
     "evidence": "Source quotation/location, contextual evidence, or verified primary-source citation."
   }
   ```

   `category` 可用 `logic`、`fact`、`context`、`omission`、`reference`、`terminology`。`before` 精确匹配**未修改的网站合并稿**，默认要求唯一出现；重复时扩大匹配片段但只改必要部分，或提供 `start`（相对网站合并稿的零起始 Python 字符位置）。所有修正指向同一份原始网站稿，不能按前一项替换后的文本计算位置；范围不能重叠。跨批次问题可用跨边界原始片段定位。
3. 插入遗漏信息时，在 `before` 选择邻近现有文字，`after` 保留它并加入必要信息。删除错误内容时 `after` 可为空。无问题时 `edits: []`，不得制造修改。`unresolved` 保存尚未证实的实质疑点，全部解决才置为 `[]`。
4. 应用报告：

   ```text
   python "<skill>/scripts/humanize_batch.py" review-apply --job "<work/job>" --report "<authored-report.json>"
   ```

   程序保留网站原始结果，在 `review/report.json` 保存审查记录，在 `review/corrected-draft.txt` 生成修正稿。所有替换精确应用，其他文字保留。报告不完整、指向旧稿、片段找不到/重复不明或修正重叠时拒绝。
5. 通读 `corrected-draft.txt`，结合原文检查修正点及全局一致性，确认每处修改必要、足够小且没有新问题。如果仍需修改，更新报告（仍锚定原网站稿）并重新 `review-apply`，然后复读。有 `unresolved` 不能确认完成。
6. 确认复读的是同一份修正稿，使用 `review-apply` 输出的 SHA-256 和实际复读结论：

   ```text
   python "<skill>/scripts/humanize_batch.py" review-complete --job "<work/job>" --confirmed-sha256 "<draft-hash>" --note "<actual final contextual reread conclusion>"
   ```

   这条命令是 Codex 对已完成复读的明确登记，不是自动语义检测。不能只运行命令而跳过阅读。
7. 最后 `export` 并检查 `status`。只有 `workflow_complete: true` 才可宣称任务完成。最终正文不插入校对批注；回复中简短说明结论和必要修正数量。网站原始稿与审查细节保存在任务目录供核对。

## 恢复和旧任务

原有任务可继续加载，已有网站结果不会重跑；缺少审查记录时进入 `review_required`。修改报告或修正稿后需要重新应用并复读，不能沿用旧确认导出变化后的内容。审查中断后从已有原文、网站稿和报告继续，不重复提交网站。
