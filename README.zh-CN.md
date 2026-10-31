[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-MinecraftAdapter" />

# ErisPulse-MinecraftAdapter

**ErisPulse Minecraft 适配器 — RCON 命令、消息发送与日志事件**

<p>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-MinecraftAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-MinecraftAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## 简介

MinecraftAdapter 是基于 RCON 协议的 Minecraft Java 版服务器适配器，支持命令执行、游戏内消息发送，并（可选）通过监听服务器日志将聊天 / 加入 / 退出事件转成标准事件。

**亮点：**
- 全量 RCON 命令面：`Api.exec()` 执行任意命令，玩家列表与状态类型化方法
- 消息发送：`To("user", player)` 单人 tellraw，`To("server", ...)` 全服 say
- 可选日志监听：聊天 → message 事件、加入/退出 → notice 事件（零插件依赖）
- 多服务器：每账户一台服务器，断线指数重连 + 保活
- 零第三方依赖：RCON 协议内置实现（约 150 行）

## 安装

```bash
epsdk install MinecraftAdapter
```

или:

```bash
pip install ErisPulse-MinecraftAdapter
```

## 服务器前置配置

在 `server.properties` 中启用 RCON：

```properties
enable-rcon=true
rcon.port=25575
rcon.password=your_rcon_password
```

## 配置

```toml
[MinecraftAdapter.accounts.default]
host = "127.0.0.1"             # RCON 服务器地址
port = 25575                   # RCON 端口（rcon.port）
password = "your_rcon_password"
bot_id = ""                    # 可选，默认为账户名
enable_log_tail = false        # 启用日志监听（聊天/加入/退出事件）
log_path = "logs/latest.log"   # 日志文件路径（与本机服务器同机或已挂载）
poll_interval = 1.0            # 日志扫描间隔（秒）
enabled = true
```

**配置项说明（每账户）：**
- `host` / `port` / `password`：RCON 端点（必填）
- `bot_id`：事件中的机器人标识（默认为账户名）
- `enable_log_tail` / `log_path` / `poll_interval`：日志事件源；要求适配器与服务器同机运行或日志目录已挂载

## 使用

### 消息发送

```python
from ErisPulse import sdk
mc = sdk.adapter.get("minecraft")

# 单人消息（tellraw）
await mc.Send.To("user", "Steve").Text("Hello Steve")

# 全服广播（say）
await mc.Send.To("server", "myserver").Text("服务器广播")

# @玩家 内联渲染
await mc.Send.To("server", "myserver").At("Steve").Text(" 看看这个")

# 多服务器
await mc.Send.Using("server2").To("server", "s2").Text("来自第二台服务器")
```

### 标准 API 动作

```python
r = await mc.Api.get_player_list()      # {"players": ["Steve", "Alex"], "raw": "..."}
r = await mc.Api.get_status()           # {"status": "ok", "connected": true}
r = await mc.Api.get_self_info()        # 服务器身份
r = await mc.Api.exec("whitelist add Alex")   # 任意 RCON 命令

# 多服务器
r = await mc.Api.Using("server2").exec("time set day")
```

### 事件监听（需 `enable_log_tail = true`）

```python
@sdk.adapter.on_message()
async def on_chat(event):
    if event["platform"] == "minecraft":
        # event["detail_type"] == "server"
        print(f"[MC] {event['user_id']}: {event['alt_message']}")

@sdk.adapter.on("notice")
async def on_notice(event):
    if event["platform"] == "minecraft":
        if event["detail_type"] == "server_joined":
            print(f"{event['user_id']} 加入了游戏")
        elif event["detail_type"] == "server_left":
            print(f"{event['user_id']} 退出了游戏")
```

## 平台事件映射关系

| 服务器日志行 | Adapter 事件 |
|--------------|--------------|
| `<Steve> 你好` | message（`detail_type: server`） |
| `Steve joined the game` | notice（`detail_type: server_joined`） |
| `Steve left the game` | notice（`detail_type: server_left`） |

原始日志行保留在 `minecraft_raw.line`。

## 注意事项：
1. **RCON 收不到聊天事件**——这是协议本身的限制（纯请求-响应）。事件接收依赖日志监听
2. 日志监听要求适配器与服务器同机运行，或日志目录已挂载
3. 日志格式依赖 vanilla / 主流服务端（Paper、Fabric 等）默认格式；自定义日志插件的格式可能解析不到
4. `say` / `tellraw` 的回显会写入日志——适配器已自动去重
5. 仅支持 `text` 段（tellraw 纯文本）；媒体段会返回说明性错误
6. 需要完整双向桥接：搭配服务端 WebSocket/HTTP 转发插件 + ErisPulse `WebhookAdapter`

---

### 参考链接
- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)
- [Minecraft RCON 协议](https://wiki.vg/RCON)
- [模块开发指南](https://www.erisdev.com/#docs/developer-guide/README.md)
