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
- 提供基于文件的任务板系统（创建、获取、更新、列表）。
- 支持分配所有人（`owner`）以及依赖阻塞机制（`blockedBy`）。

### 2.6 后台任务管理 (BackgroundManager - s08)
- 允许运行耗时的 Bash 脚本而不阻塞主循环。
- 通过 `drain()` 在每次 LLM 调用前将后台执行状态与结果通过 `<background-results>` 注入到当前上下文中。

### 2.7 消息总线与多智能体协作 (MessageBus & TeammateManager - s09/s11)
- **MessageBus**：提供基于文件的消息传递系统（收件箱模式）。
- **TeammateManager**：持久化生成多个自主运行的协作者线程（Team members）。
- **协作者生命周期**：
  - **Work Phase（工作期）**：阅读收件箱，使用工具执行任务。
  - **Idle Phase（空闲期）**：如果没有明确任务，主动进入休眠并轮询。如果发现未分配的持久化任务，它们会自动认领（`auto-claim`）并继续工作。
- 支持领导者（Lead，即主 Agent）向团队广播（`broadcast`）、批准计划（`plan_approval`）和请求关机（`shutdown_request`）。

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
2. **通知吸收**：清空后台任务队列（`BG.drain()`）与收件箱（`BUS.read_inbox("lead")`），将其注入消息体。
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