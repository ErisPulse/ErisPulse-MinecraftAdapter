[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-MinecraftAdapter" />

# ErisPulse-MinecraftAdapter

**ErisPulse Minecraft アダプタ — RCON コマンド、メッセージ送信、ログイベント**

<p>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-MinecraftAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-MinecraftAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## 概要

MinecraftAdapter は RCON プロトコルベースの Minecraft Java Edition サーバーアダプタです。コマンド実行、ゲーム内メッセージ送信、（オプションで）サーバーログのテイルによるチャット/参加/退出イベントの標準イベント化を提供します。

**ハイライト：**
- フル RCON コマンド面：`Api.exec()` で任意コマンド、プレイヤーリストと状態の型付きヘルパー
- メッセージ送信：`To("user", player)` 個人 tellraw、`To("server", ...)` 全体 say
- オプションのログテイル：チャット → message イベント、参加/退出 → notice イベント（プラグイン不要）
- マルチサーバー：アカウントごとに 1 サーバー、指数バックオフ再接続 + キープアライブ
- サードパーティ依存ゼロ：RCON プロトコルを内製（約 150 行）

## インストール

```bash
epsdk install MinecraftAdapter
```

или:

```bash
pip install ErisPulse-MinecraftAdapter
```

## サーバー事前設定

`server.properties` で RCON を有効化：

```properties
enable-rcon=true
rcon.port=25575
rcon.password=your_rcon_password
```

## 設定

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

**設定項目（アカウントごと）：**
- `host` / `port` / `password`：RCON エンドポイント（必須）
- `bot_id`：イベント内のボット識別子（既定はアカウント名）
- `enable_log_tail` / `log_path` / `poll_interval`：ログイベントソース；アダプタをサーバーと同一マシンで実行するかログディレクトリをマウントする必要があります

## 使い方

### メッセージ送信

```python
from ErisPulse import sdk
mc = sdk.adapter.get("minecraft")

# 個人メッセージ（tellraw）
await mc.Send.To("user", "Steve").Text("Hello Steve")

# 全体ブロードキャスト（say）
await mc.Send.To("server", "myserver").Text("サーバー放送")

# メンションはインライン表示
await mc.Send.To("server", "myserver").At("Steve").Text(" これを見て")

# マルチサーバー
await mc.Send.Using("server2").To("server", "s2").Text("2 台目から")
```

### 標準 Api アクション

```python
r = await mc.Api.get_player_list()      # {"players": ["Steve", "Alex"], ...}
r = await mc.Api.get_status()           # {"status": "ok", "connected": true}
r = await mc.Api.get_self_info()        # サーバー情報
r = await mc.Api.exec("whitelist add Alex")   # 任意の RCON コマンド

# マルチサーバー
r = await mc.Api.Using("server2").exec("time set day")
```

### イベント監視（`enable_log_tail = true` が必要）

```python
@sdk.adapter.on_message()
async def on_chat(event):
    if event["platform"] == "minecraft":
        print(f"[MC] {event['user_id']}: {event['alt_message']}")

@sdk.adapter.on("notice")
async def on_notice(event):
    if event["platform"] == "minecraft":
        if event["detail_type"] == "server_joined":
            print(f"{event['user_id']} が参加")
        elif event["detail_type"] == "server_left":
            print(f"{event['user_id']} が退出")
```

## イベントマッピング

| サーバーログ行 | アダプタイベント |
|----------------|------------------|
| `<Steve> hello` | message（`detail_type: server`） |
| `Steve joined the game` | notice（`detail_type: server_joined`） |
| `Steve left the game` | notice（`detail_type: server_left`） |

生ログ行は `minecraft_raw.line` に保持されます。

## 注意事項：
1. **RCON ではチャットイベントを受信できません** — プロトコル仕様上の制限（純粋なリクエスト/レスポンス）。イベント受信はログテイルに依存します
2. ログテイルはアダプタをサーバーと同一マシンで実行するか、ログディレクトリのマウントが必要です
3. ログ形式は vanilla / 主要サーバーソフト（Paper、Fabric など）の既定形式に依存；カスタム形式は解析できない場合があります
4. `say` / `tellraw` のエコーはログに書き込まれます — アダプタが自動重複排除
5. `text` セグメントのみ対応（tellraw 平文）；メディアセグメントは説明付きエラーを返します
6. 完全な双方向ブリッジには、サーバー側 WebSocket/HTTP 転送プラグイン + ErisPulse `WebhookAdapter` の併用を推奨

---

### 参考リンク
- [ErisPulse メインリポジトリ](https://github.com/ErisPulse/ErisPulse/)
- [Minecraft RCON プロトコル](https://wiki.vg/RCON)
- [モジュール開発ガイド](https://www.erisdev.com/#docs/developer-guide/README.md)
