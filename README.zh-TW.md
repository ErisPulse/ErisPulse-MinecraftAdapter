[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-MinecraftAdapter" />

# ErisPulse-MinecraftAdapter

**ErisPulse Minecraft 適配器 — RCON 命令、訊息傳送與日誌事件**

<p>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-MinecraftAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-MinecraftAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## 簡介

MinecraftAdapter 是基於 RCON 協定的 Minecraft Java 版伺服器適配器，支援命令執行、遊戲內訊息傳送，並（可選）透過監聽伺服器日誌將聊天 / 加入 / 退出事件轉成標準事件。

**亮點：**
- 全量 RCON 命令面：`Api.exec()` 執行任意命令，玩家列表與狀態類型化方法
- 訊息傳送：`To("user", player)` 單人 tellraw，`To("server", ...)` 全服 say
- 可選日誌監聽：聊天 → message 事件、加入/退出 → notice 事件（零外掛依賴）
- 多伺服器：每帳戶一台伺服器，斷線指數重連 + 保活
- 零第三方依賴：RCON 協定內建實作（約 150 行）

## 安裝

```bash
epsdk install MinecraftAdapter
```

или:

```bash
pip install ErisPulse-MinecraftAdapter
```

## 伺服器前置配置

在 `server.properties` 中啟用 RCON：

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
bot_id = ""
enable_log_tail = false
log_path = "logs/latest.log"
poll_interval = 1.0
enabled = true
```

**配置項說明（每帳戶）：**
- `host` / `port` / `password`：RCON 端點（必填）
- `bot_id`：事件中的機器人標識（預設為帳戶名）
- `enable_log_tail` / `log_path` / `poll_interval`：日誌事件源；要求適配器與伺服器同機執行或日誌目錄已掛載

## 使用

### 訊息傳送

```python
from ErisPulse import sdk
mc = sdk.adapter.get("minecraft")

# 單人訊息（tellraw）
await mc.Send.To("user", "Steve").Text("Hello Steve")

# 全服廣播（say）
await mc.Send.To("server", "myserver").Text("伺服器廣播")

# @玩家 內聯渲染
await mc.Send.To("server", "myserver").At("Steve").Text(" 看看這個")

# 多伺服器
await mc.Send.Using("server2").To("server", "s2").Text("來自第二台伺服器")
```

### 標準 API 動作

```python
r = await mc.Api.get_player_list()
r = await mc.Api.get_status()
r = await mc.Api.get_self_info()
r = await mc.Api.exec("whitelist add Alex")

r = await mc.Api.Using("server2").exec("time set day")
```

### 事件監聽（需 `enable_log_tail = true`）

```python
@sdk.adapter.on_message()
async def on_chat(event):
    if event["platform"] == "minecraft":
        print(f"[MC] {event['user_id']}: {event['alt_message']}")

@sdk.adapter.on("notice")
async def on_notice(event):
    if event["platform"] == "minecraft":
        if event["detail_type"] == "server_joined":
            print(f"{event['user_id']} 加入")
        elif event["detail_type"] == "server_left":
            print(f"{event['user_id']} 離開")
```

## 平台事件映射關係

| 伺服器日誌行 | Adapter 事件 |
|--------------|--------------|
| `<Steve> 你好` | message（`detail_type: server`） |
| `Steve joined the game` | notice（`detail_type: server_joined`） |
| `Steve left the game` | notice（`detail_type: server_left`） |

原始日誌行保留在 `minecraft_raw.line`。

## 注意事項：
1. **RCON 收不到聊天事件**——協定本身的限制（純請求-回應）。事件接收依賴日誌監聽
2. 日誌監聽要求適配器與伺服器同機執行，或日誌目錄已掛載
3. 日誌格式依賴 vanilla / 主流伺服器端（Paper、Fabric 等）預設格式；自訂格式可能解析不到
4. `say` / `tellraw` 的回顯會寫入日誌——適配器已自動去重
5. 僅支援 `text` 段（tellraw 純文字）；媒體段會返回說明性錯誤
6. 需要完整雙向橋接：搭配伺服器端 WebSocket/HTTP 轉發外掛 + ErisPulse `WebhookAdapter`

---

### 參考連結
- [ErisPulse 主庫](https://github.com/ErisPulse/ErisPulse/)
- [Minecraft RCON 協定](https://wiki.vg/RCON)
- [模組開發指南](https://www.erisdev.com/#docs/developer-guide/README.md)
