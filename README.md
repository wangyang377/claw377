# claw377

一个轻量的终端 Agent playground：基于 `LiteLLM` 做流式对话与 tool calling，围绕“读写文件、执行命令、联网检索、子任务委派、上下文压缩”构建了一套最小可用架构。

这个项目适合用来：

- 理解一个 coding agent 的最小闭环是怎么搭起来的
- 试验自定义工具调用
- 观察会话持久化、上下文压缩、后台任务这些能力如何组合
- 作为自己 Agent 项目的简化起点

## 特性

- 终端交互式聊天，入口在 `loop.py`
- 基于 `LiteLLM` 的流式输出和函数调用
- 工具模块化设计，统一放在 `tools/`
- 动态系统提示词拼装，支持 bootstrap、memory、skills 注入
- 会话日志持久化到 `~/.claw377/sessions/`
- 长上下文自动压缩，并保留 transcript
- 支持后台命令执行和简单子代理委派

## 快速开始

### 1. 安装

开发环境：

```bash
uv sync
```

安装成命令行工具：

```bash
uv tool install .
```

或者：

```bash
pipx install .
```

安装后可直接运行：

```bash
claw
```

### 2. 配置环境变量

程序第一次启动会自动创建全局配置文件：

`~/.claw377/config.env`

你也可以在当前工作目录放一个本地 `.env` 覆盖全局配置。

最少需要配置一个模型名和对应 provider key，例如：

```env
XAI_API_KEY=your_api_key
MODEL_NAME=your_model
```

如果要使用联网搜索工具，还需要补充：

```env
TAVILY_API_KEY=your_tavily_api_key
```

说明：

- `MODEL_NAME` 会传给 `litellm.completion(...)`
- 当前工作目录里的 `.env` 优先级高于 `~/.claw377/config.env`
- 搜索能力依赖 `TAVILY_API_KEY`

### 3. 启动

```bash
claw
```

单次执行模式：

```bash
claw "帮我总结一下这个仓库"
```

查看数据目录：

```bash
claw --print-paths
```

退出命令：

- `q`
- `quit`
- `exit`

## 项目结构

```text
claw377/
├── claw377/             # Python package
│   ├── loop.py          # 主交互循环，负责流式输出、工具调用、会话保存、自动压缩
│   ├── context.py       # 构建 system prompt，拼装 templates/skills/日期信息
│   ├── app_paths.py     # 用户数据目录与配置加载
│   ├── templates/       # 打包进 wheel 的提示词模板
│   ├── skills/          # 打包进 wheel 的内置 skills
│   └── tools/           # 所有工具定义与执行逻辑
│       ├── __init__.py  # 汇总 TOOL_SCHEMA 和 TOOL_HANDLERS
│       ├── bash.py      # 执行 shell 命令
│       ├── read_file.py # 读取文件
│       ├── write_file.py# 写文件
│       ├── edit_file.py # 基于 old_text/new_text 做替换
│       ├── subagent.py  # 暴露 subagent 工具，启动 fresh-context 子代理
│       ├── task_system.py # 工作区级任务系统，状态保存在 ~/.claw377/workspaces/<id>/tasks/
│       ├── web_fetch.py # 抓取网页正文
│       ├── web_search.py# 使用 Tavily 搜索
│       ├── compact.py   # 对话压缩与 transcript 保存
│       └── background.py# 后台任务执行与状态轮询
├── loop.py              # 兼容入口，转发到 claw377.loop:main
└── test/                # 一些工具/模型调用实验
```

## 架构说明

这个项目可以理解为 4 层：

### 1. 交互层

`claw377/loop.py` 使用 `prompt_toolkit` 提供 REPL 体验：

- 用户在终端输入问题
- 程序把当前时间等运行时上下文附加到用户消息
- 进入 agent loop 持续与模型交互

这层的职责是“接住用户输入，驱动整轮对话”。

### 2. Prompt 组装层

`claw377/context.py` 负责构造 system prompt，来源包括：

- 项目身份与运行环境信息
- `claw377/templates/AGENTS.md`、`SOUL.md`、`USER.md`、`TOOLS.md`
- `claw377/templates/memory/MEMORY.md`
- 当前日期、时区规则
- `claw377/skills/*/SKILL.md` 的元数据

也就是说，这个项目不是把系统提示词硬编码成一大段字符串，而是拆成多个来源动态拼接。这样做的好处是：

- 更容易维护不同类型的约束
- 更容易扩展 memory / skill 机制
- 更接近真实 Agent 框架中的 prompt assembly 设计

### 3. Agent 运行层

`claw377/loop.py` 中的核心逻辑是 `agent_loop()` 和 `stream_assistant_message()`。

它们一起完成以下事情：

1. 调用 `litellm.completion(...)` 与模型通信
2. 开启 `stream=True`，一边接收一边把 assistant 文本打印到终端
3. 在流式响应中增量组装 `tool_calls`
4. 如果模型请求调用工具，就根据工具名找到对应 handler 执行
5. 把工具结果以 `role=tool` 的消息重新塞回上下文，再继续下一轮
6. 如果没有新的工具调用，则本轮回答结束

这是一个典型的 ReAct / function calling loop，只是实现得非常轻量。

### 4. 工具执行层

`claw377/tools/__init__.py` 做了两件事：

- 暴露给模型的工具 schema 列表 `TOOLS`
- 工具名到 Python 函数的映射 `TOOL_HANDLERS`

每个工具模块遵循统一约定：

- 提供 `TOOL_SCHEMA`
- 提供 `run(...)`

这样新增工具时，只需要新增一个模块并在 `tools/__init__.py` 注册即可，扩展成本很低。

## 一次完整请求的执行链路

下面是用户输入一条消息后，系统内部的大致流程：

```text
User Input
   ↓
PromptSession 读取输入
   ↓
附加 runtime context（动态拼装messages）
   ↓
agent_loop()
   ↓
LiteLLM 流式生成 assistant 文本 / tool_calls
   ↓
如果有工具调用：
   tools handler 执行
   ↓
工具结果写回 messages
   ↓
继续调用模型
   ↓
直到 finish_reason != tool_calls
   ↓
保存 session 到 ~/.claw377/sessions/
```

如果中途上下文过长，还会插入一条支线流程：

```text
estimate_tokens(messages)
   ↓
超过 AUTO_COMPACT_THRESHOLD
   ↓
compact.summarize(messages)
   ↓
保存 transcript 到 ~/.claw377/transcripts/
   ↓
用摘要替换历史消息，继续运行
```

## 核心模块细节

### `loop.py`

这是项目入口，也是控制中心，负责：

- 创建会话 ID 和 session 文件
- 给每条用户消息附加运行时上下文
- 处理后台任务通知
- 触发自动压缩
- 执行工具并写回结果
- 持久化整个 history

可以把它理解成一个“极简 agent runtime”。

### `context.py`

负责 system prompt 的分层拼接，而不是直接 hardcode：

- `_identity_section()`：身份、操作系统、Python 版本
- `_bootstrap_section()`：读取 `claw377/templates/` 里的规则
- `_memory_section()`：读取长期记忆
- `_list_skills()`：扫描本地 skills 元数据
- `build_system_prompt()`：最终合成提示词

这部分体现的是“配置驱动的 agent 行为注入”。

### `tools/subagent.py`

这个工具比较有代表性，因为它实现了“子代理”能力：

- 为子任务创建 fresh context
- 共享当前工作目录
- 复用现有工具，但避免递归调用 `subagent`
- 在限定迭代次数内独立完成任务

对外暴露的工具名是 `subagent`，因此主代理可以把某个问题拆出去，让一个轻量子代理先做探索或局部执行。

### `tools/task_system.py`

这个模块实现了持久化任务系统：

- `task_create`：创建任务，保存到 `~/.claw377/workspaces/<id>/tasks/task_<id>.json`
- `task_update`：更新状态、owner 或依赖关系
- `task_list`：列出所有任务摘要
- `task_get`：查看单个任务详情

它和 `tools/subagent.py` 不同：

- `subagent.py` 暴露的是 `subagent` 工具，用来把工作委派给 fresh-context 子代理
- `task_system.py` 是“把任务状态持久化到文件系统”

这样即使对话被压缩，任务状态也仍然保留在工作区里。

### `tools/background.py`

这个模块实现了后台任务：

- `background_run`：异步执行命令
- `check_background`：查看任务状态
- 在主循环下一次调用模型前，把已完成任务的通知注入消息历史

这让模型可以处理一些不必阻塞前台对话的操作。

### `tools/compact.py`

压缩模块负责解决上下文窗口膨胀问题：

- 先把完整消息保存到 `~/.claw377/transcripts/*.jsonl`
- 再调用模型生成摘要
- 用一条“压缩后的摘要消息”替换原始长历史

同时，`micro_compact()` 还会对较早的工具输出做更轻量的裁剪，减少无效上下文占用。
