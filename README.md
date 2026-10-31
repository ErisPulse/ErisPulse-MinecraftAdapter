[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-MinecraftAdapter" />

# ErisPulse-MinecraftAdapter

**ErisPulse Minecraft adapter — RCON commands, messaging & log events**

<p>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-MinecraftAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-MinecraftAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## Introduction

MinecraftAdapter is a Minecraft Java Edition server adapter built on the RCON protocol. It executes commands, sends in-game messages, and (optionally) tails the server log to expose chat / join / leave events as standard events.

**Highlights:**
- **Full RCON command surface**: any command via `Api.exec()`, typed helpers for player list & status
- **Messaging**: `tellraw` to individual players (`To("user", player)`), `say` broadcast (`To("server", ...)`)
- **Optional log tail**: chat → message events, join/leave → notice events (zero plugin dependency)
- **Multi-server**: each account is one server, auto-reconnect with exponential backoff + keepalive
- **Zero third-party deps**: RCON protocol implemented in-tree (~150 lines)

## Installation

```bash
epsdk install MinecraftAdapter
```

or:

```bash
pip install ErisPulse-MinecraftAdapter
```

## Server Prerequisites

Enable RCON in `server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=your_rcon_password
```

## Configuration

```toml
[MinecraftAdapter.accounts.default]
host = "127.0.0.1"             # RCON server address
port = 25575                   # RCON port (rcon.port)
password = "your_rcon_password"
bot_id = ""                    # optional, defaults to account name
enable_log_tail = false        # enable log tailing (chat/join/leave events)
log_path = "logs/latest.log"   # log file path (same machine or mounted)
poll_interval = 1.0            # log scan interval (seconds)
enabled = true
```

**Configuration notes (per account):**
- `host` / `port` / `password`: RCON endpoint (required)
- `bot_id`: bot identity in events (defaults to account name)
- `enable_log_tail` / `log_path` / `poll_interval`: event source via server log; requires the adapter to run on the same machine as the server (or the log directory mounted)

## Usage

### Messaging

```python
from ErisPulse import sdk
mc = sdk.adapter.get("minecraft")

# Direct message to a player (tellraw)
await mc.Send.To("user", "Steve").Text("Hello Steve")

# Broadcast to the whole server (say)
await mc.Send.To("server", "myserver").Text("Server broadcast")

# Mentions are rendered inline
await mc.Send.To("server", "myserver").At("Steve").Text(" check this out")

# Multi-server
await mc.Send.Using("server2").To("server", "s2").Text("From the second server")
```

### Standard API actions

```python
r = await mc.Api.get_player_list()      # {"players": ["Steve", "Alex"], "raw": "..."}
r = await mc.Api.get_status()           # {"status": "ok", "connected": true}
r = await mc.Api.get_self_info()        # server identity
r = await mc.Api.exec("whitelist add Alex")   # any RCON command

# Multi-server
r = await mc.Api.Using("server2").exec("time set day")
```

### Event listening (requires `enable_log_tail = true`)

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
            print(f"{event['user_id']} joined")
        elif event["detail_type"] == "server_left":
            print(f"{event['user_id']} left")
```

## Platform event mapping

| Server log line | Adapter event |
|-----------------|---------------|
| `<Steve> hello` | message (`detail_type: server`) |
| `Steve joined the game` | notice (`detail_type: server_joined`) |
| `Steve left the game` | notice (`detail_type: server_left`) |

Raw log lines are preserved in `minecraft_raw.line`.

## Important notes:
1. **RCON cannot receive chat events** — this is a protocol limitation (pure request/response). Event receiving relies on log tailing
2. Log tailing requires the adapter to run on the same machine as the server, or the log directory mounted
3. Log format depends on vanilla / mainstream server software (Paper, Fabric, etc.); custom log plugins may not be parsed
4. `say` / `tellraw` echoes appear in the log — the adapter deduplicates them automatically
5. Only `text` segments are supported (tellraw plain text); media segments return a descriptive error
6. For full two-way bridging, pair a server-side WebSocket/HTTP forwarding plugin with the ErisPulse `WebhookAdapter`

---

### Reference links
- [ErisPulse main repository](https://github.com/ErisPulse/ErisPulse/)
- [Minecraft RCON protocol](https://wiki.vg/RCON)
- [Module development guide](https://www.erisdev.com/#docs/developer-guide/README.md)
