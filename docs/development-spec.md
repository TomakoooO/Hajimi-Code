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
| FE-002 | 引入 ESLint + Prettier + Husky + lint-staged | 未开始 | FE-001 | P0 | 0.5d | `pnpm lint` 与 `pnpm format:check` 可通过 | 规范先行 |
| FE-003 | 搭建基础布局（左会话/右编辑器/顶部操作栏） | 未开始 | FE-001 | P0 | 1d | 页面布局稳定，支持最小分辨率 1280x720 | 对应里程碑 M1 |
| FE-004 | 封装 `settingsStore`（模型、温度、max tokens、API-Key） | 未开始 | FE-001 | P0 | 0.5d | 设置可读写、刷新后可恢复 | 与设置页联调 |
| FE-005 | 设置页 UI 与参数校验 | 未开始 | FE-004 | P1 | 1d | 必填项校验有效，保存提示明确 | 对应里程碑 M3 |
| FE-006 | 集成 Monaco Editor（基础高亮、主题、快捷键） | 未开始 | FE-001, FE-003 | P0 | 1.5d | 支持至少 2 种主题和常用快捷键 | 对应里程碑 M2 |
| FE-007 | 编辑器差异视图（Diff）组件封装 | 未开始 | FE-006 | P1 | 1d | 可展示原始与建议代码差异 | 对应里程碑 M4 |
| FE-008 | 封装 `editorStore`（代码内容、光标、选区、语言） | 未开始 | FE-006 | P0 | 1d | 状态变更可追踪，组件间共享一致 | 支撑补全与重构 |
| FE-009 | 会话列表与线程管理（新建/删除/重命名/切换） | 未开始 | FE-003 | P0 | 1.5d | 线程操作可用，切换不丢失上下文 | 对应里程碑 M3 |
| FE-010 | 封装 `sessionStore`（消息流、线程索引、活动会话） | 未开始 | FE-009 | P0 | 1d | 消息流与线程状态一致，刷新后可恢复索引 | 与 WS 消息解耦 |
| FE-011 | WebSocket 客户端封装（连接、重连、心跳、断线提示） | 未开始 | FE-001 | P0 | 1d | 异常断连后自动重连，状态可视化 | 对应里程碑 M3 |
| FE-012 | 流式渲染组件（delta 增量展示、停止生成按钮） | 挂起 | FE-010, FE-011 | P0 | 1d | token 逐步渲染，支持手动取消 | 挂起原因：等待后端 WS 事件字段冻结 |
| FE-013 | 代码补全交互 PoC（触发、候选展示、插入） | 未开始 | FE-008, FE-011 | P0 | 1.5d | 可完成单次补全请求并插入编辑区 | 对应里程碑 M2 |
| FE-014 | 错误提示面板（问题定位、跳转行号） | 未开始 | FE-008, FE-011 | P1 | 1d | 可展示错误列表并定位到编辑器行 | 对应里程碑 M4 |
| FE-015 | 重构建议面板（建议说明 + Diff + 应用） | 未开始 | FE-007, FE-010, FE-011 | P1 | 1.5d | 可查看建议并一键应用变更 | 对应里程碑 M4 |
| FE-016 | REST API 封装层（统一响应拦截、错误码映射） | 未开始 | FE-001 | P1 | 0.5d | 统一处理 `code/message/data`，错误提示一致 | 对应文档第5章 |
| FE-017 | 前端单测（Stores + 核心组件） | 未开始 | FE-005, FE-010, FE-012, FE-015 | P0 | 2d | Vitest 通过，核心模块覆盖率达标 | 对应文档第10章 |
| FE-018 | Playwright E2E（问答/补全/重构） | 挂起 | FE-013, FE-015, FE-017 | P1 | 1.5d | 至少 3 条主流程稳定通过 | 挂起原因：等待后端联调环境稳定 |
| FE-019 | 性能优化（首屏、渲染、WS 延迟） | 未开始 | FE-012, FE-017 | P1 | 1d | 首屏 < 800ms，关键交互无明显卡顿 | 对应文档第11章 |
| FE-020 | 打包与交付（Docker 静态资源、README 前端章节） | 未开始 | FE-018, FE-019 | P0 | 1d | 生产构建可用，文档齐全 | 对应里程碑 M5 |
