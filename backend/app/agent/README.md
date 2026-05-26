# Coding-Agent 核心架构说明 (s_full.py)

本文档对 `s_full.py` 中实现的全功能智能 Agent 的核心逻辑、包含的功能模块以及工作流程进行梳理。

该脚本是整个 Agent 交互的基石（Harness），集成了任务管理、上下文压缩、多智能体协作、后台执行等所有高阶机制，为大语言模型（LLM）提供了一个完整的“驾驶舱（Cockpit）”。

## 1. 核心工作空间与目录结构

Agent 的工作环境是动态可切换的（`switch_workspace_root`），当用户在前端切换项目目录时，以下目录会自动在目标工作空间中挂载：

- `.team/` 与 `.team/inbox/`: 存放多智能体（Teammates）状态配置及消息收件箱。
- `.tasks/`: 存放持久化的任务 JSON 文件。
- `skills/`: 存放按需加载的特定领域技能（Prompt 扩展，`.md` 格式）。
- `.transcripts/`: 存放上下文压缩时产生的历史对话归档文件（JSONL）。

## 2. 核心机制与模块

Agent 由多个核心管理器支撑，主要包括：

### 2.1 Todo 管理 (TodoManager - s03)
- 维护一个短期待办清单。
- 状态支持：`pending`、`in_progress`、`completed`。
- 具有限制：最多 20 个待办，且同时只能有 1 个处于 `in_progress`。
- 如果连续几个回合未更新清单，系统会注入 `<reminder>` 提醒 Agent 及时更新。

### 2.2 子智能体 (Subagent - s04)
- **短生命周期任务委派**：通过 `run_subagent` 派生。
- 支持 `Explore`（仅读/执行）和其他类型（支持写入/编辑）。
- 内部包含一个独立的 30 轮小循环，完成后向主 Agent 返回执行摘要。

#### 前端可视化：子智能体交互时序图
- **顶栏导航与状态管理**：前端引入横向 Tab 栏并采用 LRU（最近最少使用）淘汰策略管理打开的面板，最多保留 8 个。顶栏右侧存在「子智能体视图」入口，当监测到任务调用或 `sub-agent` 活动时高亮。
- **时序图视图**：点击「子智能体视图」将建立专用的 WebSocket 频道 (`/api/ws/agent/stream/${sessionId}`) 接收父子 Agent 交互数据。
- **渲染方案**：根据 `SKILL.md` 中定义的 PlantUML 时序图规范，系统会在 Agent 执行期间显示等待动画，待交互完成后 (`EOF` 标志)，自动将所有节点和交互转换成优雅清晰的 PlantUML 代码，并通过官方渲染器直接输出美观自然的高质量时序图图片。关闭面板自动释放内存。

### 2.3 技能加载 (SkillLoader - s05)
- 从 `SKILLS_DIR` 读取 `SKILL.md` 文件。
- 在 `system_prompt` 中注册可用技能，当模型遇到不熟悉的领域时，可使用 `load_skill` 动态获取指导规则。

### 2.4 上下文压缩 (Compression - s06)
解决长文本对话的 Token 溢出问题：
- **Microcompact**：微型压缩，在每轮交互前调用，移除过早的、超长的 `tool_result` 结果，保留摘要。
- **Auto-compact**：自动压缩，当 Token 预估超过 `TOKEN_THRESHOLD`（如 100k）时触发，将完整对话写入本地 `.transcripts/` 归档，并使用 LLM 生成上下文摘要，将对话列表重置为该摘要。

#### 前端可视化：上下文使用率与手动压缩
- **实时监控**：在聊天输入框的右下角，有一个圆环饼图图标实时展示当前的**上下文使用率百分比**（根据当前对话内容的 Token 估算值与 100K 阈值进行计算）。
- **交互展开**：用户鼠标悬停该百分比图标时，会弹出类似提示框（Popover）展开显示具体的使用情况，例如 `50K of 100K`。
- **手动压缩**：提示框内提供了一个**“压缩”**按钮，用户可点击该按钮调用后端的 `/api/chat/compact` 接口，强制触发 `auto_compact` 逻辑，同时前端 UI 的会话历史会同步更新为压缩后的摘要结果。

### 2.5 持久化任务与依赖管理 (TaskManager - s07)
- 提供基于 SQLite 的持久化任务板系统（创建、获取、更新、列表）。
- 支持分配所有人（`owner`）以及依赖阻塞机制（`blockedBy`）。

### 2.6 后台任务管理 (BackgroundManager - s08)
- 允许运行耗时的 Bash 脚本而不阻塞主循环。
- 通过 `drain()` 在每次 LLM 调用前将后台执行状态与结果通过 `<background-results>` 注入到当前上下文中。

### 2.7 消息总线与多智能体协作 (MessageBus & TeammateManager - s09/s11)
- **MessageBus**：现已升级为基于 SQLite 的本地事务型消息总线。
- **TeammateManager**：持久化生成多个自主运行的协作者线程（Team members）。
- **协作者生命周期**：
  - **Work Phase（工作期）**：阅读收件箱，使用工具执行任务。
  - **Idle Phase（空闲期）**：如果没有明确任务，主动进入休眠并轮询。如果发现未分配的持久化任务，它们会自动认领（`auto-claim`）并继续工作。
- 支持领导者（Lead，即主 Agent）向团队广播（`broadcast`）、批准计划（`plan_approval`）和请求关机（`shutdown_request`）。
- **当前局限**：
  - 基于 `*.jsonl` 文件追加写入，缺少事务、ack、重试、重放与去重机制。
  - `read_inbox()` 是“读完即清空”，消费者处理中途失败时存在丢消息风险。
  - 多线程同时读写同一个 inbox 文件时存在竞争条件，不适合更高并发场景。

### 2.8 SQLite 消息总线迁移开发文档

本节定义将当前基于 JSONL 的 `MessageBus` 迁移为 SQLite 持久化消息总线的目标、数据结构、接口改造点与分阶段实施方案。

#### 2.8.1 迁移目标
- 将“文件收件箱”升级为“事务型本地消息队列”，提升并发安全性与消息可追踪性。
- 在不引入 Redis / RabbitMQ 的前提下，先解决单机、多线程、多任务场景下最核心的问题：
  - 原子写入
  - 原子领取
  - 明确消息状态
  - 消费失败可恢复
  - 支持基础审计与排障
- 保持现有系统的单机本地部署特性，不引入额外服务依赖。

#### 2.8.2 不在本期解决的问题
- 不做分布式多实例共享总线。
- 不做跨机器消息路由。
- 不做真正意义上的高吞吐 MQ 替代品。
- 不做严格的 exactly-once 语义，只追求 at-least-once + 幂等友好。

#### 2.8.3 现状问题复盘
- 当前实现见 `s_full.py` 中 `MessageBus.send()` 与 `MessageBus.read_inbox()`：
  - `send()`：向 `INBOX_DIR/<name>.jsonl` 追加一行 JSON。
  - `read_inbox()`：整文件读出后直接清空。
- 主要问题：
  - 写入和读取之间无事务保护。
  - 读与清空不是原子操作。
  - 没有“已投递 / 已领取 / 已处理 / 失败”的状态流转。
  - 无法区分“消息没到”还是“消息已被清空但处理失败”。
  - 无法支持重试、死信或审计查询。

#### 2.8.4 迁移后的核心设计
- 将 `MessageBus` 底层存储从 inbox 文件切换为 SQLite 数据库，例如：`.team/bus.db`
- 通信模型从“每个 agent 一个 inbox 文件”改为“一张消息表 + 状态字段”
- 读取模型从“读完清空”改为：
  - 先查询可消费消息
  - 在事务中原子标记为 `processing`
  - 处理成功后标记为 `done`
  - 失败时可重置为 `pending` 或标记 `failed`

#### 2.8.5 推荐表结构

建议至少建立以下两张表：

1. `messages`
- 用于存储实际消息

建议字段：
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `msg_type TEXT NOT NULL`
- `sender TEXT NOT NULL`
- `receiver TEXT NOT NULL`
- `content TEXT NOT NULL`
- `extra_json TEXT`
- `request_id TEXT`
- `status TEXT NOT NULL DEFAULT 'pending'`
- `created_at REAL NOT NULL`
- `claimed_at REAL`
- `processed_at REAL`
- `consumer TEXT`
- `retry_count INTEGER NOT NULL DEFAULT 0`
- `error_text TEXT`

建议索引：
- `INDEX idx_messages_receiver_status_created_at (receiver, status, created_at)`
- `INDEX idx_messages_request_id (request_id)`

2. `bus_meta`
- 用于记录 schema 版本、迁移信息、保留策略等

建议字段：
- `key TEXT PRIMARY KEY`
- `value TEXT NOT NULL`

#### 2.8.6 建议消息状态机
- `pending`：已写入，等待消费
- `processing`：已被某个消费者原子领取，正在处理
- `done`：已处理完成
- `failed`：处理失败，需要人工排查或重试
- `dead`：超过最大重试次数，不再自动消费

推荐规则：
- 消费者只读取 `pending`
- 领取成功后立刻改成 `processing`
- 处理成功后改成 `done`
- 处理失败时：
  - 若 `retry_count < max_retry`，回退到 `pending`
  - 否则标记为 `dead`

#### 2.8.7 Python 层接口设计

建议保留 `MessageBus` 类名，但重写内部实现，避免上层调用大改。

建议接口如下：

```python
class MessageBus:
    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict | None = None) -> str:
        ...

    def claim_inbox(self, name: str, limit: int = 20) -> list[dict]:
        ...

    def ack_messages(self, message_ids: list[int], consumer: str) -> None:
        ...

    def fail_messages(self, message_ids: list[int], consumer: str, error_text: str) -> None:
        ...

    def broadcast(self, sender: str, content: str, names: list[str]) -> str:
        ...
```

说明：
- `send()`：插入消息行
- `claim_inbox()`：在事务内查询并原子标记消息为 `processing`
- `ack_messages()`：将处理成功的消息标记为 `done`
- `fail_messages()`：失败时做重试计数与失败原因记录

#### 2.8.8 关键事务设计

`claim_inbox(name)` 必须是迁移中的关键点。

推荐做法：
- 开启事务
- 查找目标接收者最早的 `pending` 消息
- 立即将这些消息更新为 `processing`
- 提交事务
- 再返回这批消息给调用方

这样可以避免两个 Agent 同时读取到同一批消息。

SQLite 层面建议：
- 使用 `BEGIN IMMEDIATE`
- 开启 `PRAGMA journal_mode=WAL`
- 开启 `PRAGMA busy_timeout=3000`

#### 2.8.9 与现有代码的对应改造点

当前重点改造位置：

1. `MessageBus` 类
- 文件：`backend/app/agent/s_full.py`
- 替换 `send()` / `read_inbox()` / `broadcast()` 的底层实现

2. 主 Agent 收件逻辑
- 当前位置：`agent_loop()` 中 `BUS.read_inbox("lead")`
- 改造后建议变成：
  - `claimed = BUS.claim_inbox("lead")`
  - 成功注入上下文后 `BUS.ack_messages(...)`

### 2.9 安全沙箱升级开发文档

本节定义将当前“工作区路径约束 + 高危命令黑名单 + 超时控制”的轻量安全设计，升级为更接近 Claude Code 风格的多层防护方案。目标不是一次性实现完整 OS 级原生沙箱，而是分阶段把命令执行逐步迁移到更强的受限执行模型。

#### 2.9.1 当前问题
- 当前 `bash` 与 `background_run` 依赖 `subprocess.run(..., shell=True)`，命令注入和变形绕过风险较高。
- 仅靠少量黑名单字符串拦截危险命令，无法覆盖 PowerShell 变体、脚本套壳、间接副作用等情况。
- 文件安全主要依赖 `safe_path()`，这能防止文件工具路径逃逸，但不能约束 Bash 子进程访问行为。
- 没有网络隔离、没有审批分级、没有低权限执行用户、没有 OS 级沙箱边界。

#### 2.9.2 目标形态
- **第一层**：命令白名单 + 参数化执行 + 风险分级 + 受限环境变量
- **第二层**：低权限子进程 / 受限执行账号，减少命令进程拿到的系统权限
- **第三层**：预留接入独立 sandbox runner 或容器执行层，向接近 Claude Code 的“能力边界约束”演进

#### 2.9.3 分阶段任务清单

1. **阶段一：立即增强**
- [x] 去掉 `shell=True`
- [x] 引入统一 `SandboxRunner`
- [x] 建立命令白名单（只允许开发常用命令）
- [x] 对命令做语法限制，禁止 `&&`、`||`、重定向、管道等复合 shell 特性
- [x] 引入风险分级：`read_only / workspace_write / blocked`
- [x] 所有前台 `bash` 和后台 `background_run` 共用同一执行入口
- [x] 收紧环境变量，只保留必要 PATH 与工作区变量
- [x] 增加 `.sandbox/audit.jsonl` 审计日志

2. **阶段二：进程级受限执行**
- [x] 抽象 `restricted_user` 配置
- [x] 预留低权限子进程执行入口
- [x] 将沙箱执行与普通执行显式区分
- [ ] 为 Windows 低权限用户 / ACL / runas 接入预留扩展点

3. **阶段三：接近 Claude Code 的安全边界**
- [ ] 设计独立 sandbox runner 接口
- [ ] 预留容器化或外部受限执行器接入点
- [ ] 预留网络白名单/代理层接口
- [ ] 后续可将命令执行完全下沉到受限运行时

#### 2.9.4 本期验收标准
- `bash` 与 `background_run` 不再使用 `shell=True`
- 默认拒绝复合 shell 命令和高风险命令
- 非白名单命令直接失败
- 所有命令执行统一经过 `SandboxRunner`
- 文档中清晰标注：当前是“接近 Claude Code 的安全边界方向”，仍未实现真正的 OS 级文件系统/网络双隔离

#### 2.8.10 分阶段实施方案

##### Phase 1：引入 SQLite 基础设施
- 新增 `SQLiteMessageBus` 实现
- 初始化 `.team/bus.db`
- 建表与索引
- 保留原 JSONL `MessageBus`，暂不删除

交付物：
- 可初始化数据库
- 可写入消息
- 可查询消息

##### Phase 2：完成 send / claim / ack / fail 闭环
- 实现事务型 `claim_inbox`
- 实现 `ack_messages`
- 实现 `fail_messages`
- 将主 Agent 与 teammate 消费路径切到 SQLite

交付物：
- 主 Agent 能稳定收消息
- 队友能稳定收消息
- 处理失败不再直接丢消息

##### Phase 3：兼容现有工具与调试能力
- 保持 `send_message` / `broadcast` / `read_inbox` 工具行为兼容
- 增加调试接口：
  - 查看 `pending`
  - 查看 `processing`
  - 查看 `failed`
  - 按 receiver 查询

交付物：
- 前端与 REPL 行为不明显倒退
- 排障能力优于 JSONL 方案

##### Phase 4：迁移与清理
- 停用 JSONL inbox
- 删除旧的文件消息读写逻辑
- 更新 README、提示词和调试命令说明

交付物：
- 项目中只保留 SQLite 消息总线

#### 2.8.11 测试计划

必须覆盖以下测试：

1. 基础写入测试
- `send()` 后数据库中出现对应消息

2. 原子领取测试
- 两个消费者同时 `claim_inbox("lead")`
- 同一条消息只能被一个消费者领取

3. 成功确认测试
- `claim -> ack` 后消息状态变为 `done`

4. 失败重试测试
- `claim -> fail` 后消息回到 `pending` 或进入 `failed`

5. 广播测试
- `broadcast()` 生成多条目标不同的消息

6. 重启恢复测试
- 程序中途退出后，`processing` 消息可被回收或人工恢复

#### 2.8.12 额外优化建议
- 可增加“超时回收器”：
  - 若某条 `processing` 消息超过阈值未完成，则回退为 `pending`
- 可增加“幂等键”：
  - 防止某些高价值消息被重复投递
- 可增加“会话维度查询”：
  - 通过 `request_id` 将同一轮协作消息串起来
- 可增加“软删除与归档”：
  - 对老消息做归档清理，避免数据库膨胀

#### 2.8.13 实施建议结论
- 如果目标是“把当前 demo 提升到单机可用、并发更稳、便于排障”，SQLite 是非常合适的下一步。
- 它不会像 Redis / RabbitMQ 那样引入额外部署复杂度，但能明显提升事务性、可追踪性和并发安全。
- 建议优先完成：
  - `messages` 表
  - `claim_inbox`
  - `ack_messages`
  - `fail_messages`
  - 主 Agent / teammate 的消费闭环改造
- 做完这一步，你的消息总线就会从“文件 inbox demo”升级成“单机事务型本地队列”。

## 3. 工具集 (Tool Dispatch)

主 Agent 被赋予了丰富的工具集以应对全方位开发需求：

| 类别 | 工具 | 描述 |
|---|---|---|
| **基础文件/命令** | `bash`, `read_file`, `write_file`, `edit_file` | 执行 Shell，读写与局部文本替换。 |
| **跟踪记录** | `TodoWrite` | 更新短期待办清单。 |
| **委派与知识** | `task`, `load_skill` | 委派给临时子智能体，加载专项技能。 |
| **上下文** | `compress` | 手动触发上下文归档与压缩。 |
| **后台执行** | `background_run`, `check_background` | 提交后台线程命令，并检查状态。 |
| **持久化任务** | `task_create`, `task_get`, `task_update`, `task_list`, `claim_task` | 操作任务板（CRUD 与认领）。 |
| **团队协作** | `spawn_teammate`, `list_teammates`, `send_message`, `read_inbox`, `broadcast`, `shutdown_request`, `plan_approval`, `idle` | 多智能体生命周期、消息通信、决策审批。 |

## 4. 主循环工作流 (Agent Loop)

`agent_loop` 函数是驱动 Agent 行为的核心生成器，它会在后台与前端进行流式通信。其每一轮生命周期如下：

1. **预处理与压缩**：检查是否触发微压缩或自动压缩。
2. **通知吸收**：清空后台任务队列（`BG.drain()`）并以 `claim -> ack/fail` 模式读取主 Agent 收件箱，将其注入消息体。
3. **记录生命周期**：通过 `timeline_store` 发送 `llm request` 事件。
4. **模型调用与流式输出**：调用 Anthropic API 接口流式获取模型回复（`stream.text_stream`），并将 Token 交给调用者。
5. **结束判定**：记录 `llm response` 事件，如果未触发工具使用，则退出循环。
6. **工具分发执行**：
   - 遍历解析出的所有 `tool_use` 块。
   - 记录 `tool call` 事件。
   - 调用 `TOOL_HANDLERS` 映射表执行真实逻辑，捕获结果。
   - 记录 `tool_result` 事件返回给时间轴。
7. **Todo 监督**：检查连续未使用 `TodoWrite` 的轮数，触发条件则强行塞入提醒。
8. **循环继续**：将包含 `tool_result` 的消息追加进历史，开启下一轮迭代。

## 5. REPL 调试命令

如果是直接在终端通过命令行运行该脚本，支持以下内置 REPL 指令：
- `/compact`：手动压缩对话。
- `/tasks`：打印所有持久化任务列表。
- `/team`：打印当前所有团队协作者的状态。
- `/inbox`：打印主 Agent 的当前收件箱。

## 6. 测试提示词 (Todo Card 渲染与动画验证)

为确保前端 TodoCard 组件能被正确触发并呈现预期的 UI 状态及动画，可以在前端聊天框内输入以下测试提示词进行验证：

**提示词 1：生成多步骤任务清单 (测试初次渲染与 Pending 状态)**
> "帮我制定一个三步走的开发计划，请使用 TodoWrite 工具记录下来。第一步是创建前端组件，第二步是编写 API 接口，第三步是进行联调。目前只列出清单，状态全为 pending。"

**提示词 2：更新状态为进行中 (测试进行中动画图标)**
> "现在开始执行第一步，请将第一步的状态更新为 in_progress，其他保持不变。"

**提示词 3：完成部分任务并划线 (测试划线动画与进度计算)**
> "第一步已经完成了，请将其状态更新为 completed，并把第二步设为 in_progress。"

**提示词 4：任务完全闭环 (测试整体完成状态)**
> "所有步骤都完成了，请将它们的状态都更新为 completed。"

## 7. 测试提示词 (子智能体视图渲染与动画验证)

为确保前端“子智能体视图”以及时序图组件能被正确触发、记录并呈现预期的 UI 状态及连线动画，可以在前端聊天框内输入以下测试提示词：

**提示词 1：单次子智能体调用 (测试顶栏按钮高亮与基础节点生成)**
> "请使用 task 工具（子智能体）帮我查看一下 fronted/package.json 中的主要依赖信息，然后告诉我结果。"
*预期结果：顶栏「子智能体视图」按钮高亮。点击后打开面板，Agent 执行期间显示正在思考的等待动画，执行完毕后展示 PlantUML 标准时序图。*

**提示词 2：多次子智能体调用 (测试复杂调用链渲染)**
> "请分别派生两个子智能体：第一个负责查看 backend/requirements.txt，第二个负责查看 fronted/package.json。两者执行完毕后，帮我汇总一下前后的依赖库清单。"
*预期结果：执行完毕后，时序图中会出现多个子智能体节点与完整的调用流向和结果参数，图表使用柔和配色的 Clean Style 呈现，非常美观。*
