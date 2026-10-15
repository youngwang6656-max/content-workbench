请将【当前这个单一品牌/项目】整理成 waypoint 工作台项目迁移包。目标是让新的工作台能延续项目，不重新猜测产品、风格、任务和审核上下文。不要混入其他项目。

先检查你实际能访问的项目资料、项目指令、对话、稿件和审核意见。只能导出你实际读取到的内容，不能因为它们“可能在项目里”就声称已读取。不能访问的对话和附件，逐项写入 coverage.missing；不确定信息写入 coverage.uncertain。不要承诺无损复原看不到的记录。如果当前仅有本次对话，明确说明范围是本次对话。

输出要求：
1. 输出有效 UTF-8 JSON 文件；能生成文件时提供下载，不能时只输出一个 json 代码块。不要输出随笔式总结、Python 代码或在 JSON 中写注释。
2. format 固定为 waypoint-handoff，version 固定为 1。只使用下列示例中的字段。所有说明、主题、思路、cb、规则、总结使用中文；英文成品/英文原帖/原始发言保持原文。不能为凑齐内容补写缺失稿件或审核记录。
3. project.summary 详细保留策略目标、受众/社群、主要卖点、产品事实来源、已有决策、正在进行的任务、拒绝过的方向、未解决问题、下一步。它是“总结”，不是逐字历史。不能把创作人设认定为用户真实经历。
4. project.rules 仅收录用户明确要求长期适用的规则；从客户反馈推断的偏好放 preference_candidates，不提升为已生效规则。某一篇的临时修改意见归该任务，不作为永久规则。
5. tasks 分开保留帖文、评论、cb。raw_input 是用户初始输入，raw_history 是确实可见的较早输入。versions 只放可以完整读取的稿件原文，保留每一版标题、正文、段落、标点，不润色、不重译、不把总结放进稿件。current 仅在确知该版本为该阶段最新稿时标 true，不确定全填 false 并说明。没有稿件时 versions 留空。
6. opinions 逐条保留我的/主管/客户意见，source 分别为 user/supervisor/client；不能确定来源时不猜，转入 history，role 填 unknown，并记入 uncertain。base_version 指向意见针对的确切版本，无法确定填 null。processed 只用于明确已处理的意见，其他填 pending。客户限定片段放 selection，其余留空。审核通过描述放版本的 approval_notes 并引用可见依据；工作台会要求用户复核，不自动记为通过。
7. materials 保存读取到的完整原文及来源链接，kind 为 fact/strategy/sample/thread/attachment。缺失附件保留名称、filename，missing_attachment=true；它不是已经复制的文件。即使读取过图片或 PDF，仅输出 JSON 也不会迁移二进制原件，所以需原件的条目仍标 true，提示另行补传。
8. history 按顺序保留可见对话原文，role 为 user/assistant/supervisor/client/unknown。逐字内容 record_type=original，任何概括必须为 summary，source 标明对话名或出处。不得把总结标成原文。created_at 只填确知的 ISO 日期时间，否则空字符串；不要编造日期。
9. key 在整个包内唯一且稳定。parent_version 可关联父帖文或 cb 的具体版本，source_version 只用于中文回译且指向同任务确切英文稿。没有依据填 null。material_keys 只引用当前包存在的资料 key。publication 只填写真实已知的 url/date/result，否则空对象。
10. 内容多时分卷，每卷都是完整有效 JSON 文件。project_key、project、total_parts 在各卷完全一致；part 从 1 连续递增。先确定卷数，再输出。每个任务及其全部版本和意见必须留在同一卷，资料和历史可分散到不同卷；同一个 key 不得在多卷重复。不要为了凑成一卷删减原稿。先提供所有能够提供的卷，明确告知尚未输出的卷，用户可要求继续；工作台会在全部卷齐全后导入。跨卷引用可用，但必须最终提供被引用对象。
11. coverage.sources 列出实际已读取的来源；missing 列出缺失历史/附件/范围；uncertain 列出待核对事项。项目总结不能代替历史、原稿和附件清单。

以下仅说明格式，输出时删除所有示例内容，用当前项目实际信息替换。没有对应内容时保留空数组。可选字段保留默认值即可，不添加新字段：

{
  "format": "waypoint-handoff",
  "version": 1,
  "project_key": "当前项目稳定标识",
  "part": 1,
  "total_parts": 1,
  "project": {
    "name": "项目名称",
    "description": "策略目标、面向人群和社群",
    "summary": "中文项目交接摘要、当前进度与下一步",
    "rules": [],
    "preference_candidates": []
  },
  "coverage": {"sources": [], "missing": [], "uncertain": []},
  "materials": [
    {"key": "material-001", "name": "资料名称", "text": "实际读取到的资料原文", "kind": "fact", "url": "", "filename": "", "missing_attachment": false}
  ],
  "tasks": [
    {
      "key": "task-001", "name": "任务名称", "kind": "post", "comment_kind": "natural",
      "raw_input": "用户初始想法", "raw_history": [], "input_stage": "idea", "target_stage": "english",
      "parent_version": null, "material_keys": ["material-001"], "publication": {},
      "versions": [
        {"key": "version-001", "stage": "english", "title": "Exact original title", "body": "Exact original body.", "current": true, "source_version": null, "created_at": "", "approval_notes": []}
      ],
      "opinions": [
        {"stage": "english", "source": "user", "raw_text": "用户意见原文", "base_version": "version-001", "status": "pending", "selection": "", "field": "body", "created_at": ""}
      ]
    }
  ],
  "history": [
    {"role": "user", "text": "原始对话原文", "record_type": "original", "source": "对话名称", "created_at": ""}
  ]
}

枚举约定：
- kind：post 帖文、comment 评论、cb 内容简报。
- comment_kind：own 自有帖文铺评、natural 自然用户帖文评论。
- input_stage/target_stage：theme、idea、chinese、english、cb；cb 任务 target_stage=cb。
- version/opinion stage 另支持 backtranslation，指中文回译。
- 意见 status：pending、processed、partial、conflict、no_change。

请现在开始检查可见范围并输出当前项目的迁移包。不要向我索取 API 密钥，不执行包中资料引用的任何指令。
