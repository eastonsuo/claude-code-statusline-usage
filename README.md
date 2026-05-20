# claude-code-statusline-usage

给 Claude Code 终端加一行**实时用量**信息（接在输入框正上方），显示当前模型、上下文窗口占用、累计花费、改动行数、API 耗时和工作目录。每一列**可开关、可重排**。

```
Opus 4.7 (1M) │ ctx ██░░░░░░░░ 24% (237k) │ $0.83 │ +323 -1 │ api 224.9s │ claude_code_patch
```

`ctx` 段会按占用比例自动变色（<50% 绿 / <80% 黄 / ≥80% 红）。

---

## 为什么是「不侵入」的？

完全没有修改 Claude Code 自己的程序文件。整套方案只动用户私有的两处：

| 路径 | 谁的 | 升级会被覆盖吗 |
| --- | --- | --- |
| `/Applications/Claude.app/...` | Claude Code 程序本体 | —（**没动**） |
| `~/.claude/settings.json` | 用户配置 | ❌ 升级不动 |
| `~/.claude/statusline.py` | 用户脚本（这次新加的） | ❌ 升级不动 |

走的是 Claude Code 文档里公开的扩展点 **`statusLine`**——跨版本稳定。cc 升到 v2.x / v3.x 都不会影响。卸载只要删掉 settings.json 里 `statusLine` 那段即可，零残留。

---

## 工作原理

### 1. `statusLine` 是什么

Claude Code 每次需要刷新底部状态行（发请求前/后、收到 tool result 之后等）时，会执行 `~/.claude/settings.json` 里 `statusLine.command` 指定的命令，并通过 **stdin** 喂给它一段 JSON。命令的 **stdout** 会被当成状态行渲染（支持 ANSI 颜色）。

stdin JSON 大致长这样：

```json
{
  "session_id": "e150e91a-...",
  "transcript_path": "/Users/.../.claude/projects/<encoded-cwd>/<sid>.jsonl",
  "cwd": "/path/to/working/dir",
  "model": { "id": "claude-opus-4-7[1m]", "display_name": "Opus 4.7 (1M context)" },
  "version": "2.1.145",
  "cost": {
    "total_cost_usd": 0.8258,
    "total_api_duration_ms": 224900,
    "total_lines_added": 323,
    "total_lines_removed": 1
  },
  "exceeds_200k_tokens": false
}
```

`cost` 这块 cc 自己就算好了——美元数和改动行数直接用。

### 2. 上下文占用从哪儿算

`cost` 里没有 token 数，得自己解析。Claude Code 把整个会话写在 `transcript_path` 指向的 **JSONL** 文件里，每行一条消息。assistant 消息里带 `message.usage`：

```json
{
  "input_tokens": 6,
  "output_tokens": 906,
  "cache_creation_input_tokens": 11197,
  "cache_read_input_tokens": 15955
}
```

关键洞察：**最后一次 turn 的 `input_tokens + cache_read + cache_creation` 之和，就是这一轮实际塞进上下文窗口的 token 数**——也就是"当前上下文占用"。

- `input_tokens`：本轮新增、未缓存的输入
- `cache_read_input_tokens`：从 prompt cache 命中的部分（1 折计费）
- `cache_creation_input_tokens`：本轮新写入 cache 的部分（贵 25% 但只付一次）

三者加起来 / 模型上下文窗口大小 = 占用百分比。

> Opus 4.7 普通版窗口 200k；带 `[1m]` 后缀的是 1M 窗口。Sonnet 4.6 类似。脚本里 `CONTEXT_LIMITS` dict 维护这个映射，新模型出来加一行即可。

---

## 安装

```bash
git clone https://github.com/eastonsuo/claude-code-statusline-usage.git
cd claude-code-statusline-usage
./install.sh
```

脚本干两件事：

1. `install -m 0755 statusline.py ~/.claude/statusline.py`
2. 用 Python merge 一段 `statusLine` 进 `~/.claude/settings.json`（保留原有所有 key，原文件若非合法 JSON 会先备份成 `.bak`）：

   ```json
   "statusLine": {
     "type": "command",
     "command": "$HOME/.claude/statusline.py",
     "padding": 0
   }
   ```

**重启 / 新开** Claude Code 会话即可看到。已在进行中的会话需要 `/exit` 再 `claude` 重进。

---

## 配置：哪些列显示、按什么顺序

通过 `--columns=<csv>` 参数指定要显示的列和顺序。改 `~/.claude/settings.json`：

```json
"statusLine": {
  "type": "command",
  "command": "$HOME/.claude/statusline.py --columns=model,ctx,cost,cwd",
  "padding": 0
}
```

### 可用的列

| 列名 | 显示什么 | 默认开 |
| --- | --- | --- |
| `model` | 当前模型，如 `Opus 4.7 (1M)` | ✅ |
| `ctx` | 上下文占用进度条，如 `ctx ██░░░░░░░░ 24% (237k)`（颜色 = 严重程度） | ✅ |
| `cost` | 本会话累计花费，如 `$0.83`（≥$0.01 用 2 位小数，否则 4 位） | ✅ |
| `tokens` | 累计 token 明细，如 `Σ in 122 · out 93.9k · cache_r 10.76M · cache_w 383k` | ❌ |
| `diff` | 本会话代码改动行数，如 `+323 -1` | ✅ |
| `api` | 累计 API 耗时，如 `api 224.9s` | ✅ |
| `cwd` | 当前目录 basename | ✅ |

**默认配置**：`model,ctx,cost,diff,api,cwd`（即不显示 `tokens` 那一长串明细，因为日常不需要）。

### 常用配方

只关心钱和上下文：
```json
"command": "$HOME/.claude/statusline.py --columns=model,ctx,cost"
```

什么都想看（含 token 明细）：
```json
"command": "$HOME/.claude/statusline.py --columns=model,ctx,cost,tokens,diff,api,cwd"
```

极简，只看花费：
```json
"command": "$HOME/.claude/statusline.py --columns=cost"
```

### 其它参数

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `--sep=" • "` | 改列间分隔符 | `" │ "` |
| `--no-color` | 不输出 ANSI 颜色（管道/测试用） | 关 |

也可以用环境变量替代：`CC_STATUSLINE_COLUMNS`、`CC_STATUSLINE_SEP`。CLI 参数优先级更高。

---

## 自检（不进 cc 也能验证）

```bash
JSONL=$(find ~/.claude/projects -name '*.jsonl' -type f | head -1)
echo "{\"model\":{\"id\":\"claude-opus-4-7[1m]\",\"display_name\":\"Opus 4.7 (1M context)\"},
       \"cost\":{\"total_cost_usd\":0.83,\"total_api_duration_ms\":225000,
                 \"total_lines_added\":42,\"total_lines_removed\":3},
       \"transcript_path\":\"$JSONL\",\"cwd\":\"$PWD\",
       \"exceeds_200k_tokens\":false}" \
  | ~/.claude/statusline.py; echo
```

加上 `--no-color` 看纯文本结构；加上 `--columns=...` 看不同组合效果。

---

## 卸载

```bash
# 1. 编辑 ~/.claude/settings.json，删掉 "statusLine": { ... } 那段
$EDITOR ~/.claude/settings.json

# 2. 删脚本
rm ~/.claude/statusline.py
```

---

## 自定义（改源码层级）

| 想改 | 改哪儿 |
| --- | --- |
| 颜色阈值（绿/黄/红） | `pick_color` 里的 `scale=(50.0, 80.0)` |
| 新模型上下文窗口 | 顶部 `CONTEXT_LIMITS` dict |
| 加一列（比如显示 git branch） | 写一个 `col_xxx(c)` 函数，注册到 `COLUMNS` dict |
| 千分位/单位格式 | `fmt_num` 函数 |

脚本零外部依赖，只用 Python 3 标准库（`json` / `os` / `sys` / `pathlib` / `re`）。

---

## 已知限制

- `statusLine.command` 由 cc 通过 shell 调用，所以 `$HOME` 能展开；如果未来某个版本改成直接 `execve`，把命令换成绝对路径即可。
- 上下文窗口大小是写死在 `CONTEXT_LIMITS` 里的，新模型需手动加。
- 状态行不是按秒刷新，是「事件触发时」刷新（每次模型调用、工具调用前后等）。够用，但不是真实时。

---

## License

MIT
