# GroupMate 教师 Dashboard 使用与交接

入口：运行本机引擎后打开 http://127.0.0.1:8765/teacher 。原课堂工作台仍在 `/`，顶部有互相进入的链接。页面使用本机教师口令；没有在网页中放置 XIPU 密钥。

## 已实现的操作

1. 在原工作台确认活动并创建小组、组织讨论、冻结提交。已有课堂记录可直接使用。
2. 打开 Dashboard，以相同教师口令登录。点“创建场次”，选择同一活动快照的小组，填写名称和数据来源。合成验证数据与真实课堂记录明确区分。创建后的范围保存在 SQLite。
3. “课堂概览”显示实际提交数、已入组人数、评价覆盖、知识支持证据与覆盖缺失。未知应到人数不推算；等级分布须选择课堂条件分层。
4. “小组洞察”查看学生原始提交、成员确认、独立的报告归纳和个人评价。点“核查并保存教师评价”，查看本人原话、AI 基线和活动量表，修改采用结论与解释，填写采用说明并保存。AI 原始记录保留；缺少量表或本人证据时仍不能硬定级。
5. “证据审核”可按组或从选维入口回查，打开原话上下文，并转入本人评价核查。
6. “教学反馈”打开个人、小组或班级报告。编辑后先“保存为新草案”，再“发布当前版本”。每次修订保留旧版，发布新版后旧版标为已有新版。刷新仍可回查。
7. 个人反馈仍遵守学生先自评/按规则明确跳过、只见本人已发布反馈的规则；小组共享依活动配置，班级汇总仅教师可见。教师采用评价变化后，依赖旧版的个人与班级报告显示来源已变化，需重新生成，不能直接发布旧稿。

## 模型生成仍使用既有工作流

“教学反馈”下方可准备候选证据、独立评价、个人反馈、小组报告或场次班级汇总任务。将实际输入复制到 XIPU 统一总入口试运行，再导入完整结果。没有模型结果时显示缺失，不填入内置台词或自动捏造评价。

新增采用评价合同 v2：个人反馈输入同时保留 `independent_assessment`（原始 AI）和 `adopted_assessment`（当前采用）。有教师修订时，输出 `dimension_details`、`knowledge_observations` 必须复制当前采用版本。输入的 `feedback_contract` 写明这一要求。2026-10-25 已将平台 WF04C 发布为 v0.3.0 并完成真实联调，现已自动遵守以下合同；旧版本若仍复制原始 AI 值，引擎会拒绝不一致输出：

> PERSONAL：若存在 adopted_assessment，以该对象作为 dimension_details 和 knowledge_observations 的唯一来源，原样复制；independent_assessment 仅供追溯原始 AI 判断。不得按目标或自评重定等级。保持 workflow_binding 原样返回。

2026-10-25：WF04C v0.3.0 已发布并通过教师采用版本真实运行；WF03 v0.2.1 同步修正英文短回复及版本字段。仍使用人工工作流桥接，没有新增 API 渠道、密钥或自动调用。后续启用 API 不需要重写 Dashboard。

## 给前端合作者

- `static/dashboard.html`：原视觉外壳；`dashboard.css`：保留合作者样式并增加引擎表单样式。
- `static/dashboard.js`：四个真实数据页面、教师评价和分类报告编辑；`engine-adapter.js`：唯一的同源 API 客户端。
- `groupmate/dashboard.py`：场次、页面读模型与证据上下文；`assessment_reviews.py`：独立保存教师采用版本。
- 新接口：`GET/POST /api/v1/teacher/sessions`、`GET .../sessions/{id}/dashboard`、`GET .../groups/{id}`、`GET .../evidence/{id}/context`、`GET .../reports/{id}`、`POST .../assessment-reviews`。
- 报告生成/导入/修订/发布复用既有 `/api/review/*`。所有命令都在服务器核查教师权限。
- GitHub Pages 原站仍是原型展示；本次真实引擎版本运行于本机同源 `/teacher`。其他设备需后续配置可达的校内服务器/HTTPS；不能把别人的 localhost 当作本机服务。
- 知识展示采用“支持证据＋覆盖”口径，未实现互斥的组级 Partial Application 分类；不把部分覆盖冒充应用不完整。个人/班级没有总分、均值或排名。

## 视觉来源

使用并适配合作者公开仓库 GroupMate-AI_Dashboard 的 HTML/CSS，固定提交 `c7a0953cacc6f46fc12761e5ef335583932a6f1c`：https://github.com/Sivan-Bu/GroupMate-AI_Dashboard 。没有修改或推送其仓库。未把旧 UI/Design 里的求职定位、强制短练习或固定四知识库恢复为本版必需流程。

## 本轮验证范围

自动检查仅包括两个正常 HTTP 主流程和原有核心反馈/产品路径的选定检查，另进行浏览器的读取→教师评价保存→报告修订→发布→刷新回查。浏览器新增记录明确标注为合成夹具，未声称是本轮真实模型输出或教学效果验证；另可切换“历史 XIPU 实跑记录（合成课堂）”查看前轮实际工作流导入的数据。

2026-10-24 验证结果：4项选定核心检查通过；浏览器实际保存教师评价、修订并发布小组报告和六部分班级报告，刷新后保留。统计引用回查补齐分子/分母、分层条件及关联证据/反例。浏览器控制台未见错误或警告。本轮未运行完整保护性测试套件。

## Unified English classroom interface

The classroom workspace at `/` now shares the Dashboard visual language: purple accents, translucent cards, a top status bar and role-based navigation. Teachers see preparation resources, activity design, preview/publishing and group/report sections. Students see task materials, private goals/strategy, shared discussion, group proposals and reflection/feedback. On small screens, navigation moves to a horizontally scrollable bottom bar.

All authored interface labels, controls, status messages and workflow instructions are in English. Existing teacher materials, rubric text, activity titles, student messages, submissions, reflections and report bodies remain in their original language. Source enum values remain compatible with published activity snapshots. System control/submission notices have English display labels without rewriting stored records.

Core check: teacher sign-in, draft save and confirmation; student join → goal/strategy → bilingual contribution → original submission/confirmation → freeze → reflection → published feedback → next action. Original multiline message and submission matched the server record exactly. Three selected existing core tests passed; no broad or protective test suite was run. The model output used for this UI check was explicitly labelled as a synthetic test fixture.
