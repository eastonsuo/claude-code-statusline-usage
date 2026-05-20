# claude-code-statusline-usage

给 Claude Code 终端加一行**实时用量**信息（接在输入框正上方），显示当前模型、上下文窗口占用、Claude.ai 订阅的 5 小时窗口 / 周用量、累计花费、改动行数和工作目录。每一列**可开关、可重排**。

```
Opus 4.7 (1M) │ ctx ██░░░░░░ 24% (237k) │ 5h ███░░░░░ 38% ↻2h53m │ 7d █░░░░░░░ 18% ↻10h33m │ $0.83 │ +42 -3 │ claude_code_patch
```

跟 Claude.ai 「Plan usage limits」页面**保持同向**：bar 显示**已用**比例，数字也是已用 %，越接近上限越红。

颜色规则（三个进度条统一标准）：
- <50% 绿 / 50–80% 黄 / ≥80% 红
- `↻` 后面是距下次重置的相对时间（`2h53m` / `10h33m` / `3d4h` / `45m` / `30s`）

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

## 工作原理（速览）

```
cc 自己跟 Anthropic API 通信（你每发一条消息都在通信）
  ↓ 响应里夹带 cost / context_window / rate_limits
cc 把这些数字存进自己内存
  ↓ 状态行要刷新时，序列化成 JSON 通过【管道】灌进
   ↓
~/.claude/statusline.py 读 stdin → 算字符串 → 写 stdout → 退出
  ↓
cc 把 stdout 贴到状态行
```

整个项目本质就是一个 **30 行 stdin → stdout 过滤器**，剩下都是装饰。

我们从 cc 的 stdin payload 拿三块关键数据：

| 字段 | 谁给的 | 用途 |
| --- | --- | --- |
| `cost.total_cost_usd` | cc 累计算好 | 显示 `$0.83` |
| `context_window.used_percentage` | cc 算好（v2+） | 显示 `ctx 24%` |
| `rate_limits.{five_hour,seven_day}` | API 响应夹带，cc 透传 | 显示 `5h 38%` / `7d 18%` |

> ⚠️ `rate_limits` 只对 **Claude.ai 订阅用户**有效，且只在**首次发请求之后**才出现。非订阅或新会话还没说话时，5h / 7d 两列自动消失（这不是 bug）。

> 想完整理解为什么这么设计、stdin / 管道 / 扩展点是什么、cc 还有哪些扩展接口——见 **[docs/PRINCIPLES.zh.md](docs/PRINCIPLES.zh.md)**（小白友好的深度版）。

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
| `ctx` | 上下文占用进度条 `ctx ██░░░░░░ 24% (237k)`，按占用变色 | ✅ |
| `5h` | Claude.ai 5 小时窗口**已用** % + 重置 ETA，如 `5h ███░░░░░ 38% ↻2h53m` | ✅ |
| `7d` | Claude.ai 7 天周用量**已用** % + 重置 ETA，如 `7d █░░░░░░░ 18% ↻10h33m` | ✅ |
| `cost` | 本会话累计花费，如 `$0.83`（≥$0.01 用 2 位小数，否则 4 位） | ✅ |
| `tokens` | 累计 token 明细：`Σ in 122 · out 93.9k · cache_r 10.76M · cache_w 383k` | ❌ |
| `diff` | 本会话代码改动行数，如 `+42 -3` | ✅ |
| `api` | 累计 API 耗时，如 `api 224.9s` | ❌ |
| `cwd` | 当前目录 basename | ✅ |

**默认配置**：`model,ctx,5h,7d,cost,diff,cwd`。`5h` / `7d` 在非订阅用户或刚起会话时**会自动空着**（不会占位、不会报错）。

### 常用配方

只关心钱和上下文：
```json
"command": "$HOME/.claude/statusline.py --columns=model,ctx,cost"
```

订阅用户最关心额度：
```json
"command": "$HOME/.claude/statusline.py --columns=5h,7d,ctx,cwd"
```

什么都想看（含 token 明细）：
```json
"command": "$HOME/.claude/statusline.py --columns=model,ctx,5h,7d,cost,tokens,diff,api,cwd"
```

极简：
```json
"command": "$HOME/.claude/statusline.py --columns=5h,cost"
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
NOW=$(date +%s)
cat <<EOF | ~/.claude/statusline.py --no-color; echo
{
  "model": {"id":"claude-opus-4-7[1m]","display_name":"Opus 4.7 (1M context)"},
  "cost": {"total_cost_usd":0.83,"total_api_duration_ms":225000,
           "total_lines_added":42,"total_lines_removed":3},
  "context_window": {"used_percentage": 24.0,
                     "current_usage": {"input_tokens":50,"output_tokens":900,
                                       "cache_creation_input_tokens":11000,
                                       "cache_read_input_tokens":225950}},
  "rate_limits": {
    "five_hour": {"used_percentage": 23, "resets_at": $((NOW + 15120))},
    "seven_day": {"used_percentage": 12, "resets_at": $((NOW + 273600))}
  },
  "cwd": "$PWD"
}
EOF
```

加 `--columns=...` 看不同组合效果；去掉 `--no-color` 看真彩色。

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
- 状态行不是按秒刷新，是「事件触发时」刷新（每次模型调用、工具调用前后等）。所以 `5h` 的 ETA 不会"嘀嗒嘀嗒"倒数——等下次发消息时才更新。够用但不是真实时。
- `CONTEXT_LIMITS` dict 只对老版本 cc 的 fallback 路径生效；v2+ 用 stdin payload 里 cc 算好的 `context_window.used_percentage`，无需维护新模型。

---

## License

MIT
