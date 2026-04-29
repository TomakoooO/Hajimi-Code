# Fronted 前端开发导读

本目录是个人级 coding-agent 的前端工程，技术栈为 `Vue3 + Vite + TypeScript + Pinia + Monaco`。  
本文档用于帮助后续开发者快速理解代码结构、模块职责、数据流与常用操作。

## 1. 快速开始

> 当前项目约定：命令建议在 `myFastAPI` conda 环境中执行，避免环境差异。

### 1.1 安装依赖

```bash
conda run -n myFastAPI npm install
```

### 1.2 启动开发服务

```bash
conda run --no-capture-output -n myFastAPI npm run dev -- --host 0.0.0.0 --port 5173
```

- 页面地址：`http://localhost:5173/`
- 使用 `--no-capture-output` 是为了避免 conda 缓冲导致“终端看起来卡住”

### 1.3 质量检查

```bash
conda run --no-capture-output -n myFastAPI npm run lint
conda run --no-capture-output -n myFastAPI npm run format:check
conda run --no-capture-output -n myFastAPI npm run test
conda run --no-capture-output -n myFastAPI npm run build
```

### 1.4 E2E 测试

首次运行需安装浏览器：

```bash
conda run --no-capture-output -n myFastAPI npx playwright install chromium
conda run --no-capture-output -n myFastAPI npm run test:e2e
```

## 2. 目录结构与职责

```text
fronted/
├─ src/
│  ├─ api/          # REST 与业务 API 封装
│  ├─ core/         # 基础能力（如 WS 客户端）
│  ├─ components/   # 可复用 UI 组件
│  ├─ stores/       # Pinia 状态管理
│  ├─ App.vue       # 主工作台页面
│  ├─ main.ts       # 应用入口
│  └─ style.css     # 全局样式
├─ tests/
│  ├─ unit/         # Vitest 单元测试
│  └─ e2e/          # Playwright 端到端测试
├─ Dockerfile
└─ playwright.config.ts
```

## 3. 核心模块说明

### 3.1 页面入口

- `src/main.ts`：创建 Vue 应用并挂载 Pinia。
- `src/App.vue`：主工作台，聚合“会话区 + 编辑器区 + 工具区 + 设置抽屉”。

### 3.2 状态管理（Pinia）

- `src/stores/settings.ts`
  - 管理模型、温度、maxTokens、apiKey
  - 支持 `localStorage` 持久化与恢复
- `src/stores/session.ts`
  - 管理线程列表、活动线程、消息流
  - 支持新建/删除/重命名/切换线程
- `src/stores/editor.ts`
  - 管理编辑器语言、内容、光标、选区
  - 作为 Monaco 与业务逻辑之间的状态桥梁
- `src/stores/index.ts`
  - Pinia 实例与 store 统一导出

### 3.3 通信层

- `src/api/http.ts`
  - 统一 REST 请求与响应解包
  - 统一错误抛出（`ApiError`）
- `src/api/agent.ts`
  - 补全 PoC、重构建议、错误分析等业务 API
  - 后端不可用时包含轻量降级逻辑
- `src/core/ws-client.ts`
  - WebSocket 连接、重连、心跳、状态事件分发

### 3.4 组件层

- `MonacoEditor.vue`：Monaco 封装（主题、快捷键、光标/选区事件）
- `StreamOutput.vue`：流式输出区域（支持停止）
- `ErrorPanel.vue`：错误面板（支持按行定位）
- `RefactorPanel.vue`：重构建议面板
- `DiffViewer.vue`：差异预览与一键应用

## 4. 页面数据流（简化）

1. 用户在 Monaco 编辑代码  
2. `MonacoEditor` 事件更新 `editorStore` / `sessionStore`  
3. 点击工具按钮触发 `api/agent.ts` 或 `ws-client.ts`  
4. 返回结果写回状态并渲染到工具组件  
5. 会话与设置自动持久化到 `localStorage`

## 5. 已实现能力映射

- FE-005：设置抽屉 + 参数校验
- FE-006：Monaco 集成（主题/快捷键/语言）
- FE-007：Diff 组件封装与应用
- FE-008：`editorStore` 封装
- FE-009/FE-010：线程管理 + `sessionStore` 消息结构
- FE-011：WebSocket 客户端
- FE-012：流式渲染组件
- FE-013：代码补全 PoC
- FE-014：错误提示面板
- FE-015：重构建议面板
- FE-016：REST 封装层
- FE-017：Vitest 单测
- FE-018：Playwright 主流程用例
- FE-019：Monaco 懒加载 + build 分包
- FE-020：Docker 与交付文档

## 6. 开发建议

- 修改交互逻辑优先看 `App.vue` 与 `stores/*`
- 新增接口优先扩展 `api/http.ts` 与 `api/agent.ts`
- 新增“工具能力”优先做成独立组件并接入 `tool-grid`
- 每次提交前至少执行：`lint + format:check + test + build`

## 7. 常见问题

- dev 命令无输出：改用 `conda run --no-capture-output -n myFastAPI ...`
- E2E 失败提示缺少浏览器：执行 `npx playwright install chromium`
- 运行时配置问题：检查 `VITE_API_BASE_URL` 与 `VITE_WS_URL`
