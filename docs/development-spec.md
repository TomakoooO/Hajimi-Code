# 个人级 Coding-Agent 辅助编程项目开发文档

## 1. 项目定位与范围
- 项目目标：构建一个个人可用的轻量级 coding-agent 辅助编程系统，优先满足“可用、稳定、易维护”，不追求企业级多租户、复杂协作与 Trae 级别能力。
- 能力边界：单用户、单工作区优先；默认本地运行；不做复杂权限体系；不做大规模插件市场；不做跨仓库全局语义索引集群。
- 质量基线：核心流程可闭环、异常可恢复、可观测、可迭代；允许能力“够用而非最强”。
- 核心场景：代码补全（行内/块级建议）、错误提示（语法/静态分析）、单文件重构建议（函数拆分/命名改进/复杂度提示）、对话式问答（解释代码/生成片段/修改建议）。
- 非目标说明：暂不支持团队协作审计、复杂 RBAC、云端多节点横向扩展、企业 SSO、全量 IDE 深度集成。

## 2. 总体架构
- 前端职责（Vue3）：编辑器 UI、会话面板、设置管理、流式渲染、交互状态同步、错误提示展示、Diff 对比展示。
- 后端职责（FastAPI）：REST + WebSocket 网关、LLM 调用封装、Agent 流程编排、上下文构建、会话池管理、工具链执行、日志与监控。
- 通信模式：前后端采用 WebSocket 全双工进行实时交互与流式 token 下发；REST 用于配置拉取、健康检查、历史会话查询、OpenAPI 暴露。
- 数据流概述：前端提交请求 -> 后端解析上下文 -> Agent 生成 Prompt -> 调用 LLM -> 流式回传增量内容 -> 后处理结构化 -> 前端渲染与持久化。

### 2.1 组件拓扑（文字图）
```text
[Vue3 App]
  ├─ Editor Module (Monaco/CM6)
  ├─ Session Panel
  ├─ Settings Panel
  └─ WS Client
        │
        ▼
[FastAPI Gateway]
  ├─ REST Router
  ├─ WS Router
  ├─ Auth Middleware
  ├─ Session Manager (Memory/SQLite)
  └─ Agent Service
       ├─ Context Builder
       ├─ Prompt Template Engine
       ├─ Toolchain (Lint/AST/Fuzzy Search)
       └─ LLM Client (OpenAI-Compatible)
```

### 2.2 关键技术选型理由
- Vue3 + Vite：启动快、开发体验好、生态成熟。
- FastAPI：异步友好、类型标注自然、原生 OpenAPI。
- WebSocket：适合流式输出和双向交互。
- pydantic-settings：统一环境配置并减少硬编码。
- Monaco/CodeMirror6：提供成熟编辑器能力与扩展性。

## 3. 技术栈与版本锁定
- 前端：Vue 3.4.x、Vite 5.x、TypeScript 5.4+、Pinia 2.x、Monaco Editor 0.4x（可选 CodeMirror 6）。
- 后端：Python 3.11.x、FastAPI 0.11x、Uvicorn 0.3x、WebSocket（Starlette/FastAPI）、pydantic-settings 2.x。
- LLM：OpenAI API 兼容接口，抽象 ModelProvider，支持一键切换模型。
- 依赖管理：前端提交 `pnpm-lock.yaml`；后端维护 `requirements.txt` + `poetry.lock`。
- 版本策略：锁定主次版本，按季度集中升级并执行回归测试。

## 4. 项目目录规范
- 命名规范：目录名统一小写，按职责分层，避免跨层耦合。
- 分层规则：`api -> services -> core/models/tools` 单向依赖，禁止反向依赖。

### 4.1 推荐目录结构
```text
coding-agent/
├─ frontend/
│  ├─ src/
│  │  ├─ api/
│  │  ├─ components/
│  │  ├─ views/
│  │  ├─ stores/
│  │  ├─ core/
│  │  ├─ models/
│  │  └─ static/
│  ├─ tests/
│  └─ pnpm-lock.yaml
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ models/
│  │  ├─ services/
│  │  ├─ tools/
│  │  └─ static/
│  ├─ tests/
│  ├─ requirements.txt
│  └─ poetry.lock
├─ scripts/
├─ docker-compose.yml
├─ Dockerfile
└─ README.md
```

### 4.2 各目录职责
- `api`：路由层与接口协议定义。
- `core`：配置、中间件、基础设施能力。
- `models`：请求/响应 DTO 与领域模型。
- `services`：业务流程与 Agent 编排。
- `static`：静态资源、示例数据。
- `tests`：单元测试、集成测试、端到端测试。

## 5. 接口契约
- REST 统一响应：`{ code, message, data, request_id, ts }`，`code = 0` 表示成功。
- 错误码分段：`1000x` 鉴权，`2000x` 参数，`3000x` 会话，`4000x` LLM，`5000x` 系统异常。
- 鉴权方式：Bearer Token；个人版支持本地一次性密钥。

### 5.1 WebSocket 消息 Schema（示例）
```json
{
  "$id": "ws-message.schema.json",
  "type": "object",
  "required": ["type", "request_id", "payload"],
  "properties": {
    "type": {
      "type": "string",
      "enum": ["client.event", "server.delta", "server.done", "server.error", "server.meta"]
    },
    "request_id": { "type": "string", "minLength": 8 },
    "session_id": { "type": "string" },
    "payload": { "type": "object" },
    "ts": { "type": "integer" }
  }
}
```

### 5.2 REST 统一响应 Schema（示例）
```json
{
  "$id": "standard-response.schema.json",
  "type": "object",
  "required": ["code", "message", "request_id", "ts"],
  "properties": {
    "code": { "type": "integer" },
    "message": { "type": "string" },
    "data": {},
    "request_id": { "type": "string" },
    "ts": { "type": "integer" }
  }
}
```

## 6. Agent 核心流程设计
- 主流程：代码解析 -> 上下文构建 -> Prompt 模板化 -> LLM 调用 -> 结果后处理 -> 前端渲染。
- 代码解析：收集当前文件内容、光标位置、选中片段、语言类型与最近编辑差异。
- 上下文构建：滑动窗口截取邻近代码，附加会话摘要与工具输出。
- Prompt 模板：系统提示 + 任务模板（补全/问答/重构）+ 变量插槽（语言/约束/风格）。
- 结果后处理：清洗噪声、提取代码块、结构化建议（问题/原因/建议）。
- 工具链可插拔：语法检查、AST 提取、相似代码搜索（初期可使用正则/模糊匹配）。
- 稳健策略：超时控制（如 30 秒）、指数退避重试（最多 2 次）、并发限流、取消生成。
- 用量保护：请求前估算 token，超限自动裁剪上下文并提示。

## 7. 前端关键模块
- 编辑器封装：主题、快捷键、代码高亮、行内补全、Diff 渲染与补丁应用。
- 会话面板：左右分栏布局，支持线程新建、删除、重命名、切换。
- 设置页：模型选择、温度参数、最大 token、API-Key、服务端地址配置。
- 流式交互：逐 token 渲染、停止生成、失败重试、复制代码与一键应用建议。

## 8. 数据与状态管理
- 前端 Store 划分：`editorStore`、`sessionStore`、`settingsStore`。
- 前端持久化：设置项与最近会话索引保存到 `localStorage`。
- 后端会话：默认内存会话池，可选 SQLite 单文件持久化。
- 建议数据表：`sessions`、`messages`、`snapshots`。
- 迁移策略：使用版本号表管理 schema，提供迁移与回滚脚本。

## 9. 开发阶段划分与里程碑
- M1：基础项目骨架 + 可运行 Hello Agent。
- M2：Monaco 集成 + 代码补全 PoC。
- M3：WebSocket 流式问答 + 会话管理。
- M4：错误提示与重构建议。
- M5：打包、Dockerfile、GitHub Actions CI、README、用户文档。
- 验收原则：每个里程碑需有可演示脚本、通过标准、回归清单。

## 10. 测试策略
- 前端：Vitest + `@vue/test-utils`，重点覆盖 Store 与核心组件。
- 后端：pytest + FastAPI TestClient，目标覆盖率 > 80%。
- 端到端：Playwright 至少覆盖 3 条主流程（问答、补全、重构建议）。
- CI 门禁：单测、类型检查、lint、E2E smoke 全通过后方可合并。

## 11. 性能与质量指标
- 性能目标：首屏 < 800 ms；本地 WebSocket 端到端延迟 < 300 ms。
- 代码规范：前端 ESLint + Prettier；后端 black + isort + flake8。
- 提交流程：Conventional Commits；主干保护；PR 模板（变更说明/测试证据/风险）。
- 观测指标：请求耗时、首 token 时间、失败率、token 用量统计。

## 12. 交付物清单
- 完整源码仓库（附分支策略说明）。
- `docker-compose.yml` 一键启动。
- 开发文档（本文件）+ 用户快速开始手册 + API 文档（OpenAPI JSON 自动导出）。
- 里程碑演示视频或 GIF。
- `.env.example` 与常见问题排查文档。

## 13. 风险与应对
- LLM 响应慢：启用流式输出、增加取消按钮、必要时降级短响应。
- 上下文超限：滑动窗口 + 摘要策略 + 关键片段优先。
- 浏览器兼容：锁定 Chromium 内核测试，提供 Tauri 桌面端备选。
- 外部 API 波动：模型切换、退避重试、错误分级提示。
- 本地安全风险：敏感信息脱敏日志、本地密钥保护、导出前确认。

## 14. 执行约束（团队/个人约定）
- 后续开发任务默认参考本文件，若实现与文档冲突，以“先更新文档再改代码”为原则。
- 每个里程碑结束后，必须同步更新本文件中的架构、接口或流程变化。
- 新增模块前先补充目录规范与接口契约，再开始编码。

## 15. 前端任务清单
- 状态枚举仅允许：`已完成`、`挂起`、`未开始`、`正在执行`。
- 任务依赖规则：前置任务全部为 `已完成` 后，当前任务才能进入 `正在执行`。
- 建议每次迭代开始前更新本表，迭代结束时补充“实际工时”和“验收结果”。

| 任务ID | 任务内容 | 状态 | 前置任务ID | 优先级 | 预估工时 | 验收标准 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FE-001 | 初始化前端工程（Vue3 + Vite + TS + Pinia）并建立目录规范 | 已完成 | 无 | P0 | 0.5d | 本地可启动，目录结构符合文档第4章 | 已创建 `fronted` 并完成 Pinia 接入 |
| FE-002 | 引入 ESLint + Prettier + Husky + lint-staged | 已完成| FE-001 | P0 | 0.5d | `pnpm lint` 与 `pnpm format:check` 可通过 | lint 与 format:check 通过 |
| FE-003 | 搭建基础布局（左会话/右编辑器/顶部操作栏） | 已完成 | FE-001 | P0 | 1d | 页面布局稳定，支持最小分辨率 1280x720 | 基础布局已完成，满足 1280x720|
| FE-004 | 封装 `settingsStore`（模型、温度、max tokens、API-Key） | 已完成 | FE-001 | P0 | 0.5d | 设置可读写、刷新后可恢复 | settingsStore 已封装并支持 localStorage 恢复 |
| FE-005 | 设置页 UI 与参数校验 | 已完成 | FE-004 | P1 | 1d | 必填项校验有效，保存提示明确 | 设置抽屉表单已完成并含参数校验 |
| FE-006 | 集成 Monaco Editor（基础高亮、主题、快捷键） | 已完成 | FE-001, FE-003 | P0 | 1.5d | 支持至少 2 种主题和常用快捷键 | Monaco 已接入并支持快捷键 |
| FE-007 | 编辑器差异视图（Diff）组件封装 | 已完成 | FE-006 | P1 | 1d | 可展示原始与建议代码差异 | `DiffViewer` 组件已接入并支持应用修改 |
| FE-008 | 封装 `editorStore`（代码内容、光标、选区、语言） | 已完成 | FE-006 | P0 | 1d | 状态变更可追踪，组件间共享一致 | `editorStore` 已接入 Monaco 事件 |
| FE-009 | 会话列表与线程管理（新建/删除/重命名/切换） | 已完成 | FE-003 | P0 | 1.5d | 线程操作可用，切换不丢失上下文 | 线程增删改切换已完成并持久化 |
| FE-010 | 封装 `sessionStore`（消息流、线程索引、活动会话） | 已完成 | FE-009 | P0 | 1d | 消息流与线程状态一致，刷新后可恢复索引 | `sessionStore` 已支持线程 + 消息持久化 |
| FE-011 | WebSocket 客户端封装（连接、重连、心跳、断线提示） | 已完成 | FE-001 | P0 | 1d | 异常断连后自动重连，状态可视化 | `ws-client` 已接入状态灯与重连 |
| FE-012 | 流式渲染组件（delta 增量展示、停止生成按钮） | 已完成 | FE-010, FE-011 | P0 | 1d | token 逐步渲染，支持手动取消 | `StreamOutput` 已接入并可停止 |
| FE-013 | 代码补全交互 PoC（触发、候选展示、插入） | 已完成 | FE-008, FE-011 | P0 | 1.5d | 可完成单次补全请求并插入编辑区 | `completionPoc` 已接入编辑器按钮 |
| FE-014 | 错误提示面板（问题定位、跳转行号） | 已完成 | FE-008, FE-011 | P1 | 1d | 可展示错误列表并定位到编辑器行 | `ErrorPanel` 已接入并支持行定位 |
| FE-015 | 重构建议面板（建议说明 + Diff + 应用） | 已完成 | FE-007, FE-010, FE-011 | P1 | 1.5d | 可查看建议并一键应用变更 | `RefactorPanel + DiffViewer` 已接入 |
| FE-016 | REST API 封装层（统一响应拦截、错误码映射） | 已完成 | FE-001 | P1 | 0.5d | 统一处理 `code/message/data`，错误提示一致 | `api/http.ts` 已实现统一响应封装 |
| FE-017 | 前端单测（Stores + 核心组件） | 已完成 | FE-005, FE-010, FE-012, FE-015 | P0 | 2d | Vitest 通过，核心模块覆盖率达标 | 已新增 Vitest 用例覆盖 store/组件 |
| FE-018 | Playwright E2E（问答/补全/重构） | 已完成 | FE-013, FE-015, FE-017 | P1 | 1.5d | 至少 3 条主流程稳定通过 | 已新增 3 条 Playwright 主流程 |
| FE-019 | 性能优化（首屏、渲染、WS 延迟） | 已完成 | FE-012, FE-017 | P1 | 1d | 首屏 < 800ms，关键交互无明显卡顿 | Monaco 懒加载 + manualChunks 分包 |
| FE-020 | 打包与交付（Docker 静态资源、README 前端章节） | 已完成 | FE-018, FE-019 | P0 | 1d | 生产构建可用，文档齐全 | 已补充 Dockerfile 与前端 README |
| FE-021 | 打开本地项目文件夹（Directory Picker） | 已完成 | FE-003, FE-008 | P0 | 0.5d | 可选择目录并加载根节点 | 已增加目录选择中状态与取消/失败提示 |
| FE-022 | 左侧资源管理器（目录树展开/收起） | 已完成 | FE-021 | P0 | 1d | 左侧可显示多级目录并可展开收起 | 目录优先排序，支持递归构建树 |
| FE-023 | 点击文件后在编辑器展示内容 | 已完成 | FE-022, FE-010 | P0 | 1d | 点击文件后编辑器展示内容并推断语言 | 已同步 editorStore/sessionStore 语言状态 |
| FE-024 | 三栏工作台布局重构（类 Trae） | 已完成 | FE-021, FE-022, FE-023 | P0 | 1d | 左目录/中编辑器+终端/右Agent交互布局稳定 | 已移除流式输出、错误分析、重构建议、Diff 预览区 |
| FE-025 | 会话线程改为左上角下拉面板 | 已完成 | FE-024 | P1 | 0.5d | 默认按钮态，点击后展开会话列表并支持切换 | 本步修改记录：`App.vue` 重构模板与交互、`style.css` 新增三栏与下拉样式 |
| FE-026 | 修复编辑区黑块遮挡与文件内容不可见问题 | 已完成 | FE-024 | P0 | 0.5d | 选择文件后编辑器稳定显示代码，不再出现黑块覆盖 | 本步修改记录：`MonacoEditor.vue` 将容器改为 `width/height:100%`，`style.css` 为 `editor-shell` 增加 `display:flex` 与子项拉伸规则 |
| FE-027 | 目录文件类型图标与选中态视觉增强 | 已完成 | FE-022, FE-023 | P1 | 0.5d | 目录树可按文件类型显示图标，点击文件有选中高亮 | 本步修改记录：`App.vue` 新增 `getNodeIcon`，`style.css` 新增 `explorer-glyph/active` 样式 |
| FE-028 | Agent 区模型参数标签迁移与图标化 | 已完成 | FE-024 | P1 | 0.5d | DeepSeek/温度/Max 标签显示在 Agent 输入框上方并带图标 | 本步修改记录：`App.vue` 新增 `getModelIcon`，右上角仅保留文件标签，Agent区新增 `meta-chip` 标签 |
| FE-029 | 工作台视觉美化（暗色层次/间距/卡片） | 已完成 | FE-027, FE-028 | P2 | 0.5d | 目录区、消息区、标签区视觉统一，信息层次更清晰 | 本步修改记录：`style.css` 调整 `agent-panel` 渐变背景、消息卡片圆角与间距、chip 文本截断 |
| FE-030 | 对话中插入代码地址引用（非粘贴代码正文） | 已完成 | FE-023, FE-029 | P0 | 1d | 用户可在输入区添加“代码地址引用卡片”，发送后消息中展示地址与文件摘要 | 已接入引用卡片、发送时携带 `code_refs` 到后端 |
| FE-031 | 代码变更可视化（新增绿/删除红）UI 规范化 | 已完成 | FE-030 | P0 | 1d | 对比视图中新增行为绿色、删除行为红色，支持行级高亮与图例说明 | 已接入 `/api/code/diff-preview` 并完成红绿行渲染 |
| FE-032 | Agent 工作时序图面板（实时渲染） | 已完成 | FE-029 | P0 | 1.5d | 页面可实时展示用户/父Agent/子Agent/LLM/工具的时序交互 | 已接入 `/api/ws/timeline` 实时事件渲染（Agent事件为占位） |
| FE-033 | 时序图节点筛选与回放控制 | 已完成 | FE-032 | P1 | 1d | 支持按角色筛选事件、暂停/继续渲染、按 request_id 回放 | 已支持 actor 筛选、暂停实时、按 request_id 回放 |
| FE-034 | 对话区信息架构优化（引用卡片+时序图联动） | 已完成 | FE-030, FE-032 | P1 | 1d | 点击代码地址可回到资源管理器定位，点击时序事件可定位对应消息 | 已支持点击引用路径/时序事件尝试定位对应文件 |
| FE-035 | 对话交互区重构（气泡聊天布局） | 已完成 | FE-024 | P0 | 1d | 将右侧交互区重构为聊天气泡形式，移除堆叠的时序图回放面板，输入框置于底部 | 消息分左右气泡排列，引入自动滚动，移除旧版下方的 Timeline 回放面板 |
| FE-036 | 后端日志实时接入控制台面板 | 已完成 | FE-024 | P1 | 0.5d | 前端中下方终端面板实时接收并滚动渲染后端的日志输出 | 新增 `/api/ws/logs` 频道并在 `App.vue` 建立连接，加入自动滚动 |
| FE-037 | IDE 项目切换与 Agent 工作路径自动同步 | 已完成 | FE-021, BE-014 | P0 | 1d | 用户选择项目目录后自动通知后端切换 Agent 工作路径，并反馈切换状态 | `openProjectFolder` 已调用 `/api/ide/workspace/switch`，终端显示切换结果 |
| FE-038 | 编辑器多行代码引用（右键/快捷键） | 已完成 | FE-023, FE-030, BE-015 | P0 | 1d | 可选中多行代码并通过右键或 `Ctrl/Cmd+Shift+R` 添加到对话，保留原始格式和行号 | Monaco 新增 `code-reference` action，聊天输入区新增可视化 snippet 卡片 |
| FE-039 | 聊天区用户与Agent头像集成 | 未开始 | FE-035 | P1 | 0.5d | Agent显示布偶猫头像(AI-Coding)，用户显示用户头像(用户一) | 待处理 |
| FE-040 | 聊天区等待状态与“思考中”动画 | 未开始 | FE-035 | P1 | 0.5d | 用户提问后等待响应时显示思考动画 | 待处理 |
| FE-041 | 聊天区流式输出渲染支持 | 未开始 | FE-035, BE-016 | P0 | 1d | 接收后端流式消息并逐字渲染 | 待处理 |
| FE-044 | 变更审查卡片与批量决策交互 | 已完成 | FE-035, FE-043, BE-018 | P0 | 1.5d | 聊天区按文件展示审查卡片（文件名、+/-行数、审查按钮），支持批量“同意/回退” | 已接入 `pendingReviews` 卡片、单批与批量审查动作 |
| FE-045 | 编辑区审查高亮与 Diff 模式切换 | 已完成 | FE-044 | P0 | 1d | 点击审查项后可定位首个变更行，新增/删除行高亮，并可一键切换代码/Diff视图 | Monaco 增加行装饰，工具栏新增 `Diff 模式` 按钮 |
| FE-046 | 审查事件驱动的无闪烁刷新 | 已完成 | FE-044, BE-018 | P1 | 0.5d | 收到后端审查事件后自动刷新目录树与当前文件，避免整页抖动 | 已接入 `/api/ws/review`，增量刷新当前目录与选中文件 |
| FE-042 | 资源管理器右键“加入对话文件附件”能力 | 已完成 | FE-022, FE-035, BE-017 | P0 | 1d | 右键文件可加入对话附件，发送时不展开全文，展示为可移除附件图标卡片 | 已支持 `@contextmenu` 右键加入文件附件，输入区渲染附件 chip |
| FE-043 | 代码片段附件卡片化（Trae风格） | 已完成 | FE-038 | P1 | 0.5d | 已选片段不再展示全文，而以图标+路径区间的附件卡片展示 | 已替换原 snippet 展开卡片为 `attachment-chip` 样式 |

## 16. 后端任务清单
- 状态枚举仅允许：`已完成`、`挂起`、`未开始`、`正在执行`。
- 任务依赖规则：前置任务全部为 `已完成` 后，当前任务才能进入 `正在执行`。
- 目标范围：个人简易版后端，仅覆盖单用户本地开发场景。

| 任务ID | 任务内容 | 状态 | 前置任务ID | 优先级 | 预估工时 | 验收标准 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BE-001 | 初始化 `backend` 项目目录与基础分层（app/api/core/models/services/tools/tests） | 已完成 | 无 | P0 | 0.5d | 目录结构可用，启动入口可运行健康检查 | 已创建后端骨架目录、`backend/app/main.py`、`backend/app/api/routes/health.py` 与 `backend/requirements.txt` |
| BE-002 | FastAPI 应用骨架与统一配置加载（环境变量） | 已完成 | BE-001 | P0 | 0.5d | 服务可启动，配置项可通过 `.env` 覆盖 | 已新增 `core/config.py` 与配置化 `create_app` |
| BE-003 | REST 与 WebSocket 基础网关建立 | 已完成 | BE-002 | P0 | 1d | 提供健康检查REST与基础WS连接握手 | 已建立 `/api/*` REST 与 `/api/ws/timeline` WS |
| BE-004 | 代码地址读取接口（按项目路径读取文件内容） | 已完成 | BE-003 | P0 | 1d | 输入代码地址后可返回文件内容片段与元信息 | 已实现 `/api/code/read` |
| BE-005 | 代码地址安全策略（路径校验、越权拦截、扩展名限制） | 已完成 | BE-004 | P0 | 1d | 非法路径访问被拒绝并返回标准错误码 | 已实现 workspace 白名单、扩展名限制、越权拦截 |
| BE-006 | 对话请求编排接口（消息+代码地址引用） | 已完成 | BE-004, BE-005 | P0 | 1d | 后端能解析“文本+地址引用”并构建上下文 | 已实现 `/api/chat/ask`，支持多代码地址引用 |
| BE-007 | LLM 调用适配层（OpenAI兼容）与超时重试 | 已完成 | BE-006 | P0 | 1d | 单次请求可拿到结构化响应，失败可重试与降级 | 当前为占位实现：固定语句 + 超时重试框架 |
| BE-008 | 代码变更结构化输出协议（新增/删除/上下文） | 已完成 | BE-006, BE-007 | P0 | 1d | 返回可直接驱动前端红绿标记的diff结构数据 | 已实现 `/api/code/diff-preview` |
| BE-009 | 会话与消息存储（内存优先，可选SQLite） | 已完成 | BE-003 | P1 | 1d | 会话可创建/查询/追加消息并可恢复最近上下文 | 已实现内存会话存储 `session_store` |
| BE-010 | 时序事件流协议（user/parent-agent/sub-agent/llm/tool） | 已完成 | BE-003, BE-006 | P0 | 1d | WebSocket 可实时推送标准时序事件 | 已实现时序事件发布与 WS 订阅推送（Agent事件占位） |
| BE-011 | 时序事件回放接口（按 request_id 重放） | 已完成 | BE-010, BE-009 | P1 | 1d | 指定请求可按时间顺序返回完整事件序列 | 已实现 `/api/timeline/replay/{request_id}` |
| BE-012 | 后端测试与可观测性（日志、错误码、核心用例） | 已完成 | BE-008, BE-010, BE-011 | P1 | 1.5d | 核心API/WS流程有测试与日志字段，问题可追踪 | 已添加 `unittest` 用例并通过；已加入基础日志配置 |
| BE-013 | 后端全局日志拦截与 WS 推送通道 | 已完成 | BE-012 | P1 | 0.5d | 所有 `print` 和 `logging` 输出被拦截并推送给所有连接的客户端 | 新增 `logging_config.py` 的拦截器，并增加 `/api/ws/logs` 路由 |
| BE-014 | 工作路径上下文管理与映射服务 | 已完成 | BE-002, BE-005 | P0 | 1d | 支持基于项目名切换 Agent 工作根目录，维护项目名到绝对路径映射，接口可查询当前路径 | 新增 `workspace_context.py` 与 `/api/ide/workspace/current|switch` |
| BE-015 | 对话代码片段引用协议（路径+行号+原文） | 已完成 | BE-006, BE-014 | P0 | 1d | `/api/chat/ask` 支持 snippets 数组并将代码片段按原格式注入上下文 | 更新 `ChatAskRequest` 与 `chat_service.py`，支持 snippet_count 事件埋点 |
| BE-016 | Anthropic API 流式输出适配与推送 | 未开始 | BE-007, AG-005 | P0 | 1d | 重构 `chat_service.py` 和 `s_full.py` 支持 yield 流式响应 | 待处理 |
| BE-018 | 快照与审查编排服务（REST+WS） | 已完成 | BE-014, BE-015 | P0 | 2d | 支持快照创建、提交生成统一diff、审查确认/回退、审查事件WS广播 | 新增 `review_store.py` 与 `/api/review/*`、`/api/ws/review` |
| BE-019 | Agent 写盘前后审查钩子 | 已完成 | BE-018, AG-005 | P0 | 1d | Agent 执行前自动生成快照，执行后自动提交审查结果并返回前端 | `chat_service.py` 已在 `agent_loop` 前后接入 snapshot/commit 流程 |
| BE-020 | 审查异常恢复与回退测试集 | 已完成 | BE-018 | P1 | 1d | 覆盖快照-提交-回退关键路径，确保回退可还原文件 | `tests/test_api.py` 新增 `test_review_snapshot_commit_and_rollback` |
| BE-017 | 对话文件附件协议（路径+全文） | 已完成 | BE-006, BE-014 | P0 | 1d | `/api/chat/ask` 支持 files 数组，Agent 获取文件路径与全文，聊天消息仅保留附件摘要 | 已新增 `ChatFile` 模型并在 `chat_service.py` 注入 file blocks 到 Agent history |

## 17. Agent 开发任务清单
- 状态枚举仅允许：`已完成`、`挂起`、`未开始`、`正在执行`。
- 任务依赖规则：前置任务全部为 `已完成` 后，当前任务才能进入 `正在执行`。
- 目标范围：父/子 Agent 编排、工具调用与时序追踪，不扩展多租户复杂能力。

| 任务ID | 任务内容 | 状态 | 前置任务ID | 优先级 | 预估工时 | 验收标准 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AG-001 | 定义 Agent 角色与职责边界（父Agent、子Agent、工具代理） | 已完成 | 无 | P0 | 0.5d | 角色输入输出、职责边界、失败回退规则文档化 | 引入 `s_full.py` 参考实现，支持 lead、subagent、teammate 多角色编排 |
| AG-002 | 统一任务上下文模型（用户文本+代码地址引用+会话状态） | 已完成 | AG-001, BE-006 | P0 | 1d | Agent 输入结构稳定，支持多地址上下文拼装 | `chat_service.py` 转换 session messages 并集成代码地址 |
| AG-003 | 代码地址解析策略（按需读取、分段截取、窗口裁剪） | 未开始 | AG-002, BE-004 | P0 | 1d | Agent 能基于地址拉取必要代码片段并控制 token | 与 BE-005 安全策略协同 |
| AG-004 | 父Agent 路由策略（问答/改写/修复/解释） | 已完成 | AG-002 | P1 | 1d | 不同任务类型可分发到对应子Agent流程 | `s_full.py` 包含完整的 `TOOL_HANDLERS` 工具调度逻辑 |
| AG-005 | LLM 调用模板与提示词策略（简易版） | 已完成 | AG-003, AG-004, BE-007 | P0 | 1d | 关键任务可稳定返回结构化结果 | `s_full.py` 已提供 `SYSTEM` prompt 和 `Anthropic` 调用 |
| AG-006 | 代码变更建议结构化器（新增/删除/原因说明） | 未开始 | AG-005, BE-008 | P0 | 1d | 输出可直接驱动前端红绿变更展示 | 与 FE-031 联调 |
| AG-007 | 工具调用规范（读取文件、基础检索、校验） | 已完成 | AG-003 | P1 | 1d | 工具调用有统一输入输出与失败处理 | `s_full.py` 预置了20+项基础与高级工具 |
| AG-008 | 子Agent 协作编排（串行/并行、结果汇总） | 已完成 | AG-004, AG-007 | P1 | 1.5d | 父子Agent流程可闭环并返回统一结果 | `s_full.py` 中的 `run_subagent` 与 `spawn_teammate` 提供支持 |
| AG-009 | Agent 时序事件埋点（开始/调用LLM/调用工具/结束） | 已完成 | AG-004, BE-010 | P0 | 1d | 全流程关键节点可实时推送并被前端渲染 | 已在 `s_full.py` 注入 `timeline_store.publish` 埋点 |
| AG-010 | Agent 回放与诊断能力（基于 request_id） | 未开始 | AG-009, BE-011 | P1 | 1d | 可完整回放一次Agent执行轨迹并定位失败步骤 | 与 FE-033 联动 |
| AG-011 | Agent 容错策略（超时、空响应、工具失败降级） | 未开始 | AG-005, AG-008 | P1 | 1d | 失败可回退并给出可读错误说明 | 保证个人本地场景稳定性 |
| AG-012 | Agent 核心流程测试清单与验收脚本 | 未开始 | AG-006, AG-010, AG-011 | P1 | 1.5d | 核心链路有最小可回归用例与验收步骤 | 支持后续迭代扩展 |
