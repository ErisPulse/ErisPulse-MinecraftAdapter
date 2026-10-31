[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-MinecraftAdapter" />

# ErisPulse-MinecraftAdapter

**ErisPulse адаптер Minecraft — команды RCON, отправка сообщений и события логов**

<p>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-MinecraftAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-MinecraftAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-MinecraftAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## Введение

MinecraftAdapter — адаптер сервера Minecraft Java Edition на протоколе RCON: выполнение команд, отправка игровых сообщений и (опционально) отслеживание лога сервера для превращения чата / входов / выходов в стандартные события.

**Возможности:**
- Полная командная поверхность RCON: любые команды через `Api.exec()`, типизированные хелперы списка игроков и статуса
- Отправка сообщений: `tellraw` игроку (`To("user", player)`), `say` на весь сервер (`To("server", ...)`)
- Опциональное слежение за логом: чат → message события, вход/выход → notice события (без плагинов)
- Мультисервер: аккаунт = сервер, авто-переподключение с экспоненциальной задержкой + keepalive
- Ноль сторонних зависимостей: протокол RCON реализован внутри (~150 строк)

## Установка

```bash
epsdk install MinecraftAdapter
```

или:

```bash
pip install ErisPulse-MinecraftAdapter
```

## Предварительная настройка сервера

Включите RCON в `server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=your_rcon_password
```

## Настройка

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

**Параметры (на аккаунт):**
- `host` / `port` / `password`: конечная точка RCON (обязательны)
- `bot_id`: идентификатор бота в событиях (по умолчанию имя аккаунта)
- `enable_log_tail` / `log_path` / `poll_interval`: источник событий через лог; адаптер должен работать на той же машине, что и сервер (или лог смонтирован)

## Использование

### Отправка сообщений

```python
from ErisPulse import sdk
mc = sdk.adapter.get("minecraft")

# Личное сообщение игроку (tellraw)
await mc.Send.To("user", "Steve").Text("Hello Steve")

Broadcast на весь сервер (say)
await mc.Send.To("server", "myserver").Text("Серверное оповещение")

# Упоминания встраиваются в строку
await mc.Send.To("server", "myserver").At("Steve").Text(" посмотри")

# Мультисервер
await mc.Send.Using("server2").To("server", "s2").Text("Со второго сервера")
```

### Стандартные действия Api

```python
r = await mc.Api.get_player_list()      # {"players": ["Steve", "Alex"], "raw": "..."}
r = await mc.Api.get_status()           # {"status": "ok", "connected": true}
r = await mc.Api.get_self_info()        # идентификация сервера
r = await mc.Api.exec("whitelist add Alex")   # любая команда RCON

# Мультисервер
r = await mc.Api.Using("server2").exec("time set day")
```

### Прослушивание событий (нужно `enable_log_tail = true`)

```python
@sdk.adapter.on_message()
async def on_chat(event):
    if event["platform"] == "minecraft":
        print(f"[MC] {event['user_id']}: {event['alt_message']}")

@sdk.adapter.on("notice")
async def on_notice(event):
    if event["platform"] == "minecraft":
        if event["detail_type"] == "server_joined":
            print(f"{event['user_id']} вошёл")
        elif event["detail_type"] == "server_left":
            print(f"{event['user_id']} вышел")
```

## Соответствие событий

| Строка лога сервера | Событие адаптера |
|---------------------|------------------|
| `<Steve> привет` | message (`detail_type: server`) |
| `Steve joined the game` | notice (`detail_type: server_joined`) |
| `Steve left the game` | notice (`detail_type: server_left`) |

Исходные строки лога сохраняются в `minecraft_raw.line`.

## Важные замечания:
1. **RCON не получает события чата** — это ограничение протокола (чистый запрос/ответ). Приём событий основан на слежении за логом
2. Слежение требует, чтобы адаптер работал на той же машине, что и сервер, либо лог был смонтирован
3. Формат лога зависит от vanilla / популярного серверного ПО (Paper, Fabric и т.д.); кастомные форматы могут не разбираться
4. Эхо `say` / `tellraw` попадает в лог — адаптер автоматически дедуплицирует их
5. Поддерживаются только `text` сегменты (tellraw plain text); медиасегменты возвращают поясняющую ошибку
6. Для полного двустороннего моста используйте серверный плагин WebSocket/HTTP пересылки вместе с ErisPulse `WebhookAdapter`

---

### Ссылки
- [Основной репозиторий ErisPulse](https://github.com/ErisPulse/ErisPulse/)
- [Протокол Minecraft RCON](https://wiki.vg/RCON)
- [Руководство по разработке модулей](https://www.erisdev.com/#docs/developer-guide/README.md)
