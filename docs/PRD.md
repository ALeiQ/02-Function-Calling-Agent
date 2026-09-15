# PRD: Function-Calling Agent（02 课题）

## 1. 背景与目标

**背景**：LLM 本身只有输入/输出文本的能力，无法触达真实世界（查数据、算数、拉 API）。Function Calling 让模型能"发起工具调用"，由应用层安全执行并回填结果，是 LLM 从聊天走向 Agent 的基础工程能力。

**目标**：自研一个基于 Ollama 本地模型的 Function-Calling Agent，能自主调用 **天气查询、数据库查询、计算器** 等工具完成用户任务。核心考察点：**结构化输出、工具注册、多轮工具调用**。

**非目标**：不做多 Agent 编排、不做长期记忆、不依赖 LangChain/LlamaIndex 等框架的 agent 封装（原理需可手讲）。

## 2. 用户画像与场景

- **主要用户**：本人（面试准备 + 工程实践），演示对象为面试官。
- **典型场景**：
  1. 「北京明天天气怎么样？」→ 天气工具
  2. 「计算 (12×8+9)÷5，再查订单表里金额超过这个数的订单」→ 计算器 → 数据库查询（跨轮依赖）
  3. 「员工表多少人？平均薪资呢？」→ 数据库查询 → 计算器（结果再加工）
  4. 「今天几号、星期几？」→ 时间工具
  5. 演示非法输入被护栏拦截：「删掉订单表」「给我跑个 SELECT」→ 只读拦截

## 3. 功能需求

### 3.1 工具层

| ID | 需求 | 说明 |
|----|------|------|
| F1 | 声明式工具注册 | `@tool` 装饰器注册，聚合 name/description/参数Schema/执行函数，自动生成 Ollama 兼容的 tool 定义 |
| F2 | 参数结构化校验 | pydantic 定义参数模型，`model_json_schema()` 生成 Schema；调用前校验，非法参数回传机器可读错误让模型自愈 |
| F3 | 计算器工具 | 受限 AST 求值（仅数字/四则/括号），不 eval 裸字符串；确定性结果 |
| F4 | 天气工具 | 内置 mock 城市天气数据（离线、确定性）；城市不存在则返回清晰错误 |
| F5 | 数据库工具 | 只读 SQLite 连接（`mode=ro`），仅允许 SELECT（大小写/空白归一后校验），拒绝 DROP/INSERT/UPDATE/`;` 注入构造 |
| F6 | 时间工具 | 返回当前日期/时间/星期/时区 |
| F7 | 工具可枚举与审计 | `agent tools` 可列出全部注册工具及其 Schema；执行轨迹可追踪（供 UI 与日志） |

### 3.2 Agent 引擎

| ID | 需求 | 说明 |
|----|------|------|
| F8 | 多轮工具循环 | model→tool_calls→执行→回填→再询，直到无 tool_calls 出最终答复 |
| F9 | 并行工具调用 | 一条回复含多个 tool_calls 时逐个执行、结果全部回填 |
| F10 | 调用错误自愈 | 工具抛错/校验失败 → 以 tool 消息回传错误 → 模型据错修正重试 |
| F11 | 迭代上限 | `max_turns`（默认 8）防死循环，超出返回明确兜底信息 |
| F12 | 会话管理 | 消息历史管理；CLI 交互会话与单次 chat 复用同一引擎 |

### 3.3 界面

| ID | 需求 | 说明 |
|----|------|------|
| F13 | CLI | `agent chat "问题"`（单次）、`agent repl`（交互）、`agent tools`（罗列）、`agent seed`（建库） |
| F14 | Web API | `POST /chat` 全量回复；`POST /chat/stream` SSE 流式，包含 tool_call 事件（名称/参数/结果）与逐字输出 |
| F15 | Web UI | 极简聊天页，实时展示工具调用轨迹（谁被调用、参数、返回）+ 流式回复 |

## 4. 非功能需求

- **安全**：DB 只读 + SELECT-only 强护栏；工具不执行 shell；计算器不允许任意 Python eval（AST 白名单）。
- **确定性/可测**：天气 mock、计算器纯函数，全链路无网络即可单测。
- **性能**：工具执行毫秒级；SSE 流式减少首个 token 等待。
- **可维护**：模块分 tools/agent/api 三层；ruff + pytest 全绿（沿用 01 的 `select=["E","F","I","N","W"]`、line-length=100）。

## 5. 技术方案

- **模型**：Ollama `qwen2.5`（原生工具支持最稳），`temperature=0`。
- **后端**：Python 3.9+，`ollama` SDK 直接调 `/api/chat` + `tools` 参数（不引入 agent 框架）。
- **结构**：

```
02-Function-Calling-Agent/
├── pyproject.toml / .env / .gitignore
├── agent.py            # CLI 入口（同 01 的 rag.py）
├── run_server.py       # uvicorn 启动
├── PRD.md / README.md
├── scripts/seed_db.py  # 生成 SQLite 员工/订单 demo 库
├── src/
│   ├── config.py       # pydantic-settings
│   ├── main.py         # typer CLI
│   ├── tools/          # registry + calculator/weather/sql/datetime_tool
│   ├── agent/          # schema + loop + session
│   └── api/            # app + routes + schemas
├── static/             # 前端
└── tests/
```

## 6. API 约定（草案）

- `POST /chat`：`{session_id, message}` → `{answer, trace: [{tool,args,result}]}`
- `POST /chat/stream`：SSE 事件 `event: tool_call / chunk / done`
- 校验失败等以结构化错误返回，不 panic。

## 7. 测试与验收标准

- **单测**（mock client 的 agent loop 可全离网跑）：
  - registry：注册/去重/Schema 生成正确
  - calculator：四则/括号/除零/非法表达式拒绝
  - sql：SELECT 放行；`delete`/`drop`/多语句注入拒绝；只读连接强制
  - weather：存在的城市返回数据、不存在返回错误
  - loop：多轮收敛、并行 tool_calls、错误自愈、超上限兜底
- **集成验收**（需 ollama 运行）：
  - 三个演示场景（依赖调用/结果加工/并发调用）在 CLI 与 Web UI 均成功；
  - 护栏场景被拦截。

## 8. 里程碑

1. 脚手架 + pyproject + config + 目录（✅ 完成）
2. 工具层（registry + 4 工具）+ seed 脚本（✅ 完成）
3. Agent 循环 + CLI（✅ 完成）
4. API + SSE + Web UI（✅ 完成）
5. 测试补全（99% 覆盖率）+ README（架构图 + trade-off）（✅ 完成）
6. 端到端验收（✅ 完成）

## 9. 风险与对策

- **qwen2.5 偶尔工具参数不稳** → 校验失败自愈机制兜底
- **循环不收敛** → max_turns 硬上限 + 兜底回复
- **DB 注入** → 双层护栏（只读连接 + SELECT-only 归一校验）