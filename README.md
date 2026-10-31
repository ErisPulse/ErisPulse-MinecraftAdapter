# ErisPulse MinecraftAdapter

**Minecraft RCON 适配器 —— 命令执行、say/tellraw 发送、日志事件监听。**

## 特性

- **RCON 全量命令面**：任意命令执行（`Api.exec`）、类型化方法（玩家列表/状态）
- **消息发送**：`.Text()` → 单人 `tellraw`（`To("user", player)`）或全服 `say`（`To("server", ...)`）
- **日志事件监听**（可选）：tail `server.log`，聊天 → message 事件、加入/退出 → notice 事件，零插件依赖
- **多服务器**：`accounts` 下每个账户一台服务器，断线自动指数重连 + 保活
- **RCON 协议自实现**：零第三方依赖

## 安装

```bash
epsdk install MinecraftAdapter
```

或：

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
host = "127.0.0.1"
port = 25575
password = "your_rcon_password"
bot_id = ""                    # 留空默认为账户名
enable_log_tail = false        # 启用日志监听（聊天/加入/退出事件）
log_path = "logs/latest.log"   # 日志文件（与本机服务器同机或已挂载）
poll_interval = 1.0            # 日志扫描间隔（秒）
enabled = true
```

## 使用

```python
from ErisPulse import sdk
mc = sdk.adapter.get("minecraft")

# 发送消息
await mc.Send.To("user", "Steve").Text("你好 Steve")     # tellraw 单人
await mc.Send.To("server", "myserver").Text("服务器广播")  # say 全服

# 玩家列表
r = await mc.Api.get_player_list()
print(r["data"]["players"])

# 任意命令
r = await mc.Api.exec("whitelist add Alex")
print(r["data"]["command_output"])

# 接收游戏内聊天/加入事件（enable_log_tail = true 时）
@sdk.adapter.on_message()
async def on_msg(event):
    if event["platform"] == "minecraft":
        print(f"[MC] {event['user_id']}: {event['alt_message']}")
```

## ⚠️ 能力边界（RCON 协议限制）

- **RCON 无法接收聊天事件**——这是协议本身的限制（纯请求-响应，服务器不推送）。事件接收依赖日志监听：
  - 适配器与服务器**同机部署**或日志目录已挂载（`enable_log_tail + log_path`）
  - 日志格式依赖 vanilla/主流服务端（Paper/Fabric 等）默认格式；自定义日志插件格式可能解析不到
- 需要完整的双向聊天桥接？推荐搭配服务端插件（WebSocket/HTTP 推送类）将聊天事件转发到 ErisPulse `WebhookAdapter`
- `say` 命令的回显会进日志，适配器已做回环去重

## License

MIT
