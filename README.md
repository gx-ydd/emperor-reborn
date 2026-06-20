# Emperor Reborn

本地个人 AI Agent，基于 Python 3.13+、FastAPI 与 pydantic-ai 构建，提供 Web UI 与 CLI 两种交互方式。

## 架构概览

```
emperor_reborn/
├── __init__.py          # 包初始化
├── config.py            # 配置管理（环境变量 / .env）
├── llm.py               # LLM 模型构建（Alibaba DashScope / OpenAI-compatible）
├── agent.py             # pydantic-ai Agent 定义及工具
├── security.py          # 安全模块（路径校验、命令白名单）
├── memory.py            # JSONL 对话历史存储
├── events.py            # 运行时事件模型（RuntimeEvent / EventSink）
├── runtime.py           # Agent 运行时（流式执行、任务管理）
├── runtime_store.py     # 运行时事件持久化存储
├── app.py               # FastAPI 应用（REST API + WebSocket）
├── cli.py               # Typer CLI（init / doctor / web）
└── test.py              # 异步测试示例
static/
└── index.html           # Web UI（暗色主题，WebSocket 聊天界面）
```

## 核心模块说明

| 模块 | 职责 |
|---|---|
| `config.py` | 从 `.env` 加载 `Settings`（host、port、workspace、provider、model、权限模式等） |
| `llm.py` | 根据 provider 构建 pydantic-ai 模型：支持 `alibaba`（DashScope Qwen）和 `openai-compatible` |
| `agent.py` | 定义 Agent 及 5 个工具：`read_file`、`list_files`、`web_fetch`、`run_command`、`write_file` |
| `security.py` | `safe_path` 防止路径逃逸；`validate_command` 白名单 + 危险令牌检测 |
| `memory.py` | `MemoryStore` 以 JSONL 存储展示历史与模型消息，支持增量追加 |
| `events.py` | `RuntimeEvent`（pydantic BaseModel）与 `EventSink` 工厂方法 |
| `runtime.py` | `AgentRuntime` 串联 Agent、Memory、EventStore，通过 `stream_chat` 产出流式事件 |
| `runtime_store.py` | `RuntimeEventStore` 持久化事件日志，维护 index.json 统计信息 |
| `app.py` | FastAPI：静态文件、健康检查、历史查询、事件查询、停止任务、诊断、WebSocket 聊天 |
| `cli.py` | Typer CLI：`init`（初始化目录和 .env）、`doctor`（检查配置）、`web`（启动 Web 服务） |

## Agent 工具

| 工具 | 说明 | 权限控制 |
|---|---|---|
| `read_file` | 读取工作区内文件（限 12000 字符） | 路径必须在 workspace 内 |
| `list_files` | 按 glob 模式列出工作区文件 | 限 workspace 内 |
| `web_fetch` | 抓取 HTTP/HTTPS 网页内容 | 仅允许 http(s) 协议 |
| `run_command` | 执行白名单内的安全命令 | 白名单：pwd/ls/cat/python/python3/git/grep；危险令牌拦截 |
| `write_file` | 写入文件到工作区 | `permission_mode=auto` 时才允许，否则需用户确认 |

## 安全机制

- **路径安全**：`safe_path` 确保所有文件操作不超出 workspace 范围
- **命令安全**：`validate_command` 使用白名单 + 危险令牌检测（rm/sudo/chmod/curl/wget 等）
- **Git 子命令**：仅允许 `status`/`diff`/`log`/`branch`
- **写入权限**：默认 `ask_before_edit` 模式，`auto` 模式才允许 Agent 直接写文件

## 支持的 LLM

- **Alibaba DashScope**：默认 provider，使用 Qwen 模型（如 `qwen-plus`），需要 `DASHSCOPE_API_KEY`
- **OpenAI-compatible**：需要 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`

## 快速开始

```bash
# 1. 复制环境配置
cp .env.example .env
# 编辑 .env 填入 API Key

# 2. 初始化
emperor-reborn init

# 3. 检查配置
emperor-reborn doctor

# 4. 启动 Web 服务
emperor-reborn web
```

访问 `http://127.0.0.1:8765` 即可使用 Web UI 与 Agent 交互。

## 技术栈

- **语言**：Python 3.13+
- **Web 框架**：FastAPI + Uvicorn
- **AI 框架**：pydantic-ai
- **HTTP 客户端**：httpx
- **CLI 框架**：Typer + Rich
- **配置管理**：python-dotenv
- **构建系统**：hatchling

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` | - | 阿里云 DashScope API Key |
| `EMPEROR_PROVIDER` | `alibaba` | LLM 提供商（alibaba / openai-compatible） |
| `EMPEROR_MODEL` | `qwen-plus` | 模型名称 |
| `EMPEROR_ALIBABA_BASE_URL` | DashScope 默认 | 阿里云 API Base URL |
| `EMPEROR_HOST` | `127.0.0.1` | Web 服务监听地址 |
| `EMPEROR_PORT` | `8765` | Web 服务监听端口 |
| `EMPEROR_WORKSPACE` | `.` | 工作区根目录 |
| `EMPEROR_MEMORY_DIR` | `memory` | 记忆存储目录（相对 workspace） |
| `EMPEROR_PERMISSION_MODE` | `ask_before_edit` | 权限模式（ask_before_edit / auto） |

## API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 返回 Web UI 页面 |
| `/api/health` | GET | 健康检查 |
| `/api/bootstrap` | GET | 初始化数据（历史 + 事件 + 状态） |
| `/api/history` | GET | 对话历史 |
| `/api/runtime/events` | GET | 运行时事件列表 |
| `/api/runtime/stop` | POST | 停止当前运行任务 |
| `/api/diagnostics` | GET | 诊断信息 |
| `/ws` | WebSocket | 实时聊天通信 |
