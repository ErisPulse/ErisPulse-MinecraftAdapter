import asyncio
import json
import os
import re
import struct
import time as _time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ErisPulse import sdk
from ErisPulse.Core.Bases import BaseConfig, BotAccountConfig, BaseAdapter
try:
    from ErisPulse.runtime.tasks import spawn_background
except ImportError:  # pragma: no cover
    spawn_background = None

__version__ = "0.1.2"

MIN_FRAMEWORK_VERSION = (2, 7, 1)


def _forward_node_text(node: Dict) -> str:
    """提取合并转发节点 content 中全部 text 段文本（段间直接连接）"""
    data = node.get("data") or {}
    return "".join(
        str(seg.get("data", {}).get("text") or "")
        for seg in (data.get("content") or [])
        if isinstance(seg, dict) and seg.get("type") == "text"
    )


def _forward_nodes_plain(nodes, separator: str = "\n") -> str:
    """合并转发节点降级纯文本：每条「昵称: 正文」（Minecraft 无富文本能力）"""
    lines = []
    for node in nodes if isinstance(nodes, list) else [nodes]:
        if not isinstance(node, dict):
            continue
        data = node.get("data") or {}
        nickname = str(data.get("nickname") or "").strip()
        text = _forward_node_text(node).strip()
        if nickname and text:
            lines.append(f"{nickname}: {text}")
        elif text:
            lines.append(text)
    return separator.join(lines)


def _escape_mc_say(text: str) -> str:
    """say 命令文本转义：反斜杠翻倍，换行替换为空格"""
    escaped = str(text).replace("\\", "\\\\")
    escaped = escaped.replace("\r", " ").replace("\n", " ")
    return escaped


def _parse_version(version_str: str):
    try:
        parts = []
        for part in version_str.split("."):
            digits = ""
            for ch in part:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            parts.append(int(digits or 0))
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])
    except Exception:
        return (0, 0, 0)


def _check_framework_version() -> bool:
    try:
        raw = sdk.__version__ if hasattr(sdk, "__version__") else sdk.version
        if callable(raw):
            raw = raw()
        current = _parse_version(str(raw))
        if current < MIN_FRAMEWORK_VERSION:
            print(
                f"警告: ErisPulse 版本过低 (当前 {current}，需要 >= "
                f"{MIN_FRAMEWORK_VERSION})，MinecraftAdapter 可能无法正常工作"
            )
            return False
        return True
    except Exception:
        return True


@dataclass
class MinecraftAccountConfig(BotAccountConfig):
    """Minecraft 服务器账户配置"""

    host: str = field(
        default="127.0.0.1",
        metadata={
            "description": "RCON 服务器地址",
            "required": True,
            "ui": {"widget": "text", "group": "connection", "order": 1},
        },
    )
    port: int = field(
        default=25575,
        metadata={
            "description": "RCON 端口（server.properties 的 rcon.port，需 enable-rcon=true）",
            "required": True,
            "ui": {"widget": "number", "min": 1, "max": 65535, "group": "connection", "order": 2},
        },
    )
    password: str = field(
        default="",
        metadata={
            "description": "RCON 密码（server.properties 的 rcon.password）",
            "required": True,
            "secret": True,
            "ui": {"widget": "password", "group": "connection", "order": 3},
        },
    )
    bot_id: str = field(
        default="",
        metadata={
            "description": "机器人 ID（留空默认为账户名）",
            "required": False,
            "ui": {"widget": "text", "group": "basic", "order": 4},
        },
    )
    enable_log_tail: bool = field(
        default=False,
        metadata={
            "description": "启用日志监听（tail server.log 解析聊天/加入/退出事件，需与本机服务器同机或挂载日志）",
            "required": False,
            "ui": {"widget": "switch", "group": "events", "order": 5},
        },
    )
    log_path: str = field(
        default="logs/latest.log",
        metadata={
            "description": "日志文件路径（latest.log 或带日期滚动时指向最新文件）",
            "required": False,
            "ui": {
                "widget": "text",
                "group": "events",
                "order": 6,
                "show_if": {"field": "enable_log_tail", "op": "eq", "value": True},
            },
        },
    )
    poll_interval: float = field(
        default=1.0,
        metadata={
            "description": "日志扫描间隔（秒）",
            "required": False,
            "ui": {
                "widget": "number",
                "min": 0.2,
                "step": 0.1,
                "group": "events",
                "order": 7,
                "show_if": {"field": "enable_log_tail", "op": "eq", "value": True},
            },
        },
    )


MinecraftAccountConfig._schema_meta = {
    "group_labels": {
        "basic": {"i18n": "minecraft.group.basic", "default": "基本设置"},
        "connection": {"i18n": "minecraft.group.connection", "default": "RCON 连接"},
        "events": {"i18n": "minecraft.group.events", "default": "事件监听"},
    }
}


# ══════════════════════════════════════════════════════════════
# RCON 协议（Minecraft Server RCON，Source RCON 同构）
# 包结构: [length:i32][id:i32][type:i32][body bytes][null][null]
# ══════════════════════════════════════════════════════════════

SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


class RconError(Exception):
    pass


class RconClient:
    """异步 RCON 客户端（单连接，串行请求）"""

    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._req_id = 0
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self):
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=10
        )
        # 认证
        rid = self._next_id()
        await self._send_packet(rid, SERVERDATA_AUTH, self.password)
        ptype, payload = await self._recv_packet()
        # 部分实现先回一个空的 RESPONSE_VALUE，再回 AUTH_RESPONSE
        if ptype == SERVERDATA_RESPONSE_VALUE:
            ptype, payload = await self._recv_packet()
        if ptype != SERVERDATA_AUTH_RESPONSE:
            raise RconError(f"RCON 认证响应异常: type={ptype}")
        if rid == -1:
            raise RconError("RCON 认证失败：密码错误")
        return True

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def _send_packet(self, rid: int, ptype: int, body: str):
        body_bytes = body.encode("utf-8")
        length = 4 + 4 + len(body_bytes) + 2
        data = struct.pack("<iii", length, rid, ptype) + body_bytes + b"\x00\x00"
        self._writer.write(data)
        await self._writer.drain()

    async def _recv_packet(self) -> Tuple[int, int, str]:
        header = await self._reader.readexactly(4)
        (length,) = struct.unpack("<i", header)
        body = await self._reader.readexactly(length)
        rid, ptype = struct.unpack("<ii", body[:8])
        text = body[8:-2].decode("utf-8", errors="replace")
        return rid, ptype, text

    async def exec(self, command: str, timeout: float = 30.0) -> str:
        if not self.connected:
            raise RconError("RCON 连接未建立")
        async with self._lock:
            rid = self._next_id()
            try:
                await asyncio.wait_for(self._send_packet(rid, SERVERDATA_EXECCOMMAND, command), timeout)
                _, _, text = await asyncio.wait_for(self._recv_packet(), timeout)
                return text
            except (asyncio.TimeoutError, ConnectionError, OSError) as e:
                self._writer = None
                self._reader = None
                raise RconError(f"RCON 命令执行失败: {e}") from e

    async def close(self):
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._writer = None
        self._reader = None


class _AccountRuntime:
    """单个服务器运行时状态"""

    __slots__ = (
        "name", "config", "bot_id", "rcon", "connected", "log_offset",
        "log_inode", "_echo_seen",
    )

    def __init__(self, name: str, config):
        self.name = name
        self.config = config
        self.bot_id = config.bot_id or name
        self.rcon: Optional[RconClient] = None
        self.connected = False
        self.log_offset = 0
        self.log_inode = None
        self._echo_seen: List[Tuple[str, float]] = []

    def remember_echo(self, key: str):
        now = _time.time()
        self._echo_seen.append((key, now))
        self._echo_seen = [(k, t) for k, t in self._echo_seen if now - t < 30]

    def is_echo(self, key: str) -> bool:
        return any(k == key for k, _ in self._echo_seen)


class MinecraftAdapter(BaseAdapter):
    """
    Minecraft RCON 适配器

    通过 RCON 执行命令与发送消息；可选 tail server.log 解析聊天/加入/退出事件。

    {!--< tips >!--}
    1. RCON 是纯命令协议（收不到聊天事件），事件面依赖日志监听
    2. 发送：To("user", player) → /tellraw 单人；To("server"/"group", id) → /say 全服
    3. 任意命令：await adapter.Api.exec("whitelist add Steve")
    {!--< /tips >!--}
    """

    _platform = "minecraft"
    ConfigClass = None
    AccountConfigClass = MinecraftAccountConfig

    def __init__(self, sdk_ref=None):
        super().__init__(sdk_ref)
        _check_framework_version()
        self._runtimes: Dict[str, _AccountRuntime] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def _get_config_key(self) -> str:
        return "MinecraftAdapter"

    # ==================== 生命周期 ====================

    async def start(self):
        for name, account in self.enabled_accounts.items():
            rt = self._runtimes.get(name)
            if rt is None:
                rt = _AccountRuntime(name, account)
                self._runtimes[name] = rt
            rt.config = account
            rt.bot_id = account.bot_id or name

            task = asyncio.create_task(self._run_account(rt))
            self._tasks[name] = task

        self.logger.info(f"Minecraft 适配器已启动，共 {len(self.enabled_accounts)} 个服务器")

    async def _run_account(self, rt: _AccountRuntime):
        """RCON 常驻连接（断线指数重连）+ 可选日志监听"""
        backoff = 5
        while True:
            try:
                rt.rcon = RconClient(rt.config.host, rt.config.port, rt.config.password)
                await rt.rcon.connect()
                rt.connected = True
                backoff = 5
                self.logger.info(f"账户 {rt.name} RCON 已连接 {rt.config.host}:{rt.config.port}")
                await self.emit_meta("connect", rt.bot_id, user_name=rt.name)

                tasks = [asyncio.create_task(self._rcon_keepalive(rt))]
                if rt.config.enable_log_tail and rt.config.log_path:
                    tasks.append(asyncio.create_task(self._log_tail(rt)))
                try:
                    await asyncio.gather(*tasks)
                finally:
                    for t in tasks:
                        t.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.warning(f"账户 {rt.name} RCON 连接失败: {e}，{backoff} 秒后重试")
            finally:
                if rt.connected:
                    rt.connected = False
                    try:
                        await self.emit_meta("disconnect", rt.bot_id)
                    except Exception:
                        pass
                if rt.rcon:
                    await rt.rcon.close()
                    rt.rcon = None
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)

    async def _rcon_keepalive(self, rt: _AccountRuntime):
        """每 30 秒空命令保活，维持连接并快速感知断线"""
        while True:
            await asyncio.sleep(30)
            if rt.rcon and rt.rcon.connected:
                try:
                    await rt.rcon.exec("list")
                except RconError:
                    raise ConnectionError("keepalive 失败")

    async def call_api(self, endpoint: str, _account_id: Optional[str] = None, **params):
        """API 动作统一入口（send_message / get_player_list / exec）"""
        # 标准字段 account_id 与旧名 _account_id 双兼容（ApiDSL.Using 传标准名）
        account_id = params.pop("account_id", None) or _account_id
        rt = self._runtimes.get(account_id) if account_id else next(iter(self._runtimes.values()), None)
        if rt is None:
            return self.make_error(retcode=10003, message="账户不存在")
        if rt.rcon is None or not rt.rcon.connected:
            return self.make_error(retcode=33001, message="RCON 未连接")
        if endpoint == "send_message":
            target_type = params.get("target_type") or "server"
            target_id = str(params.get("target_id") or "")
            message = params.get("message") or []
            texts = "".join(str(seg.get("data", {}).get("text", "")) for seg in message if seg.get("type") == "text").strip()
            if not texts:
                return self.make_error(retcode=10002, message="空消息（Minecraft 仅支持 text 段）")
            try:
                if target_type == "user":
                    if re.search(r'[\s"\'\\]', target_id):
                        return self.make_error(retcode=10002, message="target_id 含非法字符（空白/引号/反斜杠）")
                    component = json.dumps({"text": texts}, ensure_ascii=False)
                    out = await rt.rcon.exec(f"tellraw {target_id} {component}")
                    rt.remember_echo(f"tellraw:{target_id}:{texts}")
                else:
                    safe_text = _escape_mc_say(texts)
                    out = await rt.rcon.exec(f"say {safe_text}")
                    rt.remember_echo(f"say:{rt.bot_id}:{safe_text}")
                return self.make_response(data={"command_output": out}, message_id=str(uuid.uuid4()))
            except RconError as e:
                return self.make_error(retcode=33001, message=str(e))
        if endpoint in ("get_player_list", "minecraft.get_player_list"):
            out = await rt.rcon.exec("list")
            players = []
            m = re.search(r"players online:\s*(.*)$", out)
            if m and m.group(1):
                players = [p.strip() for p in m.group(1).split(",") if p.strip()]
            return self.make_response(data={"players": players, "raw": out})
        if endpoint in ("exec", "minecraft.exec"):
            try:
                out = await rt.rcon.exec(str(params.get("command", "")))
                return self.make_response(data={"command_output": out})
            except RconError as e:
                return self.make_error(retcode=33001, message=str(e))
        return self.make_error(retcode=10002, message=f"不支持的动作: {endpoint}")

    async def shutdown(self):
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        for rt in self._runtimes.values():
            if rt.rcon:
                await rt.rcon.close()
                rt.rcon = None
            if rt.connected:
                rt.connected = False
                try:
                    await self.emit_meta("disconnect", rt.bot_id)
                except Exception:
                    pass
        self.logger.info("Minecraft 适配器已关闭")

    # ==================== 日志事件 ====================

    _CHAT_RE = re.compile(r"^\[[\d:]+\] \[[^]]*/?\w*\]: <([^>]+)> (.*)$")
    _JOIN_RE = re.compile(r"^\[[\d:]+\] \[[^]]*/?\w*\]: (\S+) (?:joined|加入) (?:the game|了游戏|游戏)?")
    _LEFT_RE = re.compile(r"^\[[\d:]+\] \[[^]]*/?\w*\]: (\S+) (?:left|退出) (?:the game|了游戏|游戏)?")

    async def _log_tail(self, rt: _AccountRuntime):
        path = rt.config.log_path
        if not os.path.isfile(path):
            self.logger.warning(f"账户 {rt.name} 日志文件不存在: {path}，日志监听停用")
            return
        rt.log_offset = os.path.getsize(path)
        try:
            rt.log_inode = os.stat(path).st_ino
        except OSError:
            rt.log_inode = None
        self.logger.info(f"账户 {rt.name} 日志监听已启动: {path}")

        interval = max(0.2, float(rt.config.poll_interval or 1.0))
        while True:
            try:
                await asyncio.sleep(interval)
                if not os.path.isfile(path):
                    continue
                try:
                    inode = os.stat(path).st_ino
                except OSError:
                    continue
                if rt.log_inode is not None and inode != rt.log_inode:
                    # 日志滚动：重置到新文件开头
                    self.logger.info(f"账户 {rt.name} 检测到日志滚动，重置读取位置")
                    rt.log_offset = 0
                    rt.log_inode = inode
                size = os.path.getsize(path)
                if size < rt.log_offset:
                    rt.log_offset = 0
                if size == rt.log_offset:
                    continue
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(rt.log_offset)
                    new_text = f.read()
                    rt.log_offset = f.tell()
                for line in new_text.splitlines():
                    self._process_log_line(rt, line)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.error(f"账户 {rt.name} 日志监听异常: {e}")

    def _process_log_line(self, rt: _AccountRuntime, line: str):
        line = line.rstrip("\r\n")
        if not line:
            return
        m = self._CHAT_RE.match(line)
        if m:
            player, message = m.group(1), m.group(2)
            # 回环去重：RCON say/tellraw 的内容也会进日志
            if rt.is_echo(f"say:{player}:{message}"):
                return
            self._emit_log_event(rt, "message", "server", player, message, line=line)
            return
        m = self._JOIN_RE.match(line)
        if m:
            self._emit_log_event(rt, "notice", "group_member_increase", m.group(1), "", line=line, operator_id=m.group(1), sub_type="server_joined")
            return
        m = self._LEFT_RE.match(line)
        if m:
            self._emit_log_event(rt, "notice", "group_member_decrease", m.group(1), "", line=line, operator_id=m.group(1), sub_type="server_left")

    def _emit_log_event(
        self, rt: _AccountRuntime, etype: str, detail_type: str,
        user_id: str, text: str, line: str = "", operator_id: str = None,
        sub_type: str = "",
    ):
        ev = {
            "id": str(uuid.uuid4()),
            "time": int(_time.time()),
            "type": etype,
            "detail_type": detail_type,
            "platform": "minecraft",
            "self": {
                "platform": "minecraft",
                "user_id": rt.bot_id,
                "user_name": rt.name,
                "account_id": rt.name,
            },
            "user_id": user_id,
            "minecraft_raw": {"line": line},
            "minecraft_raw_type": "log_line",
        }
        if sub_type:
            ev["sub_type"] = sub_type
        if etype == "message":
            ev["message_id"] = str(uuid.uuid4())
            ev["message"] = [{"type": "text", "data": {"text": text}}]
            ev["alt_message"] = text
        if operator_id is not None:
            ev["operator_id"] = operator_id
        if etype == "notice":
            ev["group_id"] = rt.bot_id
        try:
            asyncio.create_task(self.emit_event(ev))
        except Exception as e:
            self.logger.error(f"发射 MC 事件失败: {e}")

    # ==================== 发送 ====================

    class Send(BaseAdapter.Send):
        """Minecraft 消息发送（text；tellraw 单人 / say 全服）"""

        def Raw_ob12(self, message, **kwargs):
            ctx = self.send_context

            async def _send():
                adapter = self._adapter
                rt = adapter._runtimes.get(ctx.get("account_id") or next(iter(adapter._runtimes)))
                if rt is None:
                    return adapter.make_error(retcode=10003, message="账户不存在")
                if rt.rcon is None or not rt.rcon.connected:
                    return adapter.make_error(retcode=33001, message="RCON 未连接")

                segments = self._apply_modifiers(message)
                # 纯 node 列表整体转为「昵称: 正文」文本；混合列表中 node 文本并入 texts
                if segments and all(
                    isinstance(seg, dict) and seg.get("type") == "node"
                    for seg in segments
                ):
                    texts, unsupported = [_forward_nodes_plain(segments)], []
                else:
                    texts, unsupported = [], []
                    for seg in segments:
                        stype = seg.get("type")
                        data = seg.get("data", {}) or {}
                        if stype == "text":
                            texts.append(str(data.get("text", "")))
                        elif stype == "mention":
                            texts.append(str(data.get("user_id", "")))
                        elif stype == "node":
                            texts.append(_forward_nodes_plain(seg))
                        elif stype in ("image", "audio", "video", "file"):
                            unsupported.append(stype)
                        elif stype == "reply":
                            adapter.logger.debug("Minecraft 跳过 reply 段")
                        elif stype == "mention_all":
                            adapter.logger.warning("Minecraft 不支持 mention_all 段，已跳过")
                        elif isinstance(stype, str) and stype.startswith("minecraft_"):
                            adapter.logger.warning(f"Minecraft 扩展段不支持发送，已跳过: {stype}")
                        else:
                            adapter.logger.warning(f"Minecraft 未知段类型已跳过: {stype}")

                content = "".join(texts).strip()
                if not content:
                    return adapter.make_error(
                        retcode=10002,
                        message="Minecraft 仅支持 text 段"
                        + (f"（收到不支持段: {unsupported}）" if unsupported else "，且消息为空"),
                    )
                if unsupported:
                    adapter.logger.warning(f"Minecraft 不支持的段已丢弃: {unsupported}")

                target_type = ctx.get("target_type") or "server"
                target_id = str(ctx.get("target_id") or "")
                try:
                    if target_type == "user":
                        if re.search(r'[\s"\'\\]', target_id):
                            return adapter.make_error(
                                retcode=10002,
                                message="target_id 含非法字符（空白/引号/反斜杠）",
                            )
                        component = json.dumps({"text": content}, ensure_ascii=False)
                        out = await rt.rcon.exec(f"tellraw {target_id} {component}")
                        rt.remember_echo(f"tellraw:{target_id}:{content}")
                    elif target_type in ("server", "group"):
                        safe_text = _escape_mc_say(content)
                        out = await rt.rcon.exec(f"say {safe_text}")
                        rt.remember_echo(f"say:{rt.bot_id}:{safe_text}")
                    else:
                        return adapter.make_error(
                            retcode=10003,
                            message=f"不支持的目标类型: {target_type}（user=玩家 / server=全服）",
                        )
                    return adapter.make_response(
                        data={"command_output": out},
                        message_id=str(uuid.uuid4()),
                        message=f"已跳过不支持的段: {', '.join(unsupported)}" if unsupported else "",
                        raw={"output": out},
                    )
                except RconError as e:
                    return adapter.make_error(retcode=33001, message=str(e))

            return asyncio.create_task(_send())

    # ==================== Api ====================

    class Api(BaseAdapter.Api):
        """Minecraft RCON API 动作"""

        async def _rt(self):
            ad = self._adapter
            name = self._account_id or self.api_context.get("account_id")
            return ad._runtimes.get(name) if name else next(iter(ad._runtimes.values()), None)

        async def get_status(self) -> dict:
            rt = await self._rt()
            if rt is None or rt.rcon is None or not rt.rcon.connected:
                return self._adapter.make_response(data={"status": "offline", "connected": False})
            return self._adapter.make_response(data={"status": "ok", "connected": True})

        async def get_self_info(self) -> dict:
            rt = await self._rt()
            if rt is None:
                return self._adapter.make_error(retcode=10003, message="账户不存在")
            return self._adapter.make_response(
                data={
                    "user_id": rt.bot_id,
                    "user_name": rt.name,
                    "user_displayname": rt.name,
                    "host": f"{rt.config.host}:{rt.config.port}",
                }
            )

        async def get_version(self) -> dict:
            from . import __version__

            return self._adapter.make_response(
                data={
                    "impl": "ErisPulse-MinecraftAdapter",
                    "version": __version__,
                    "onebot_version": "12",
                }
            )

        async def get_supported_actions(self) -> dict:
            return self._adapter.make_response(
                data=[
                    "get_self_info", "get_status", "get_version",
                    "get_supported_actions", "get_player_list", "exec",
                    "minecraft.get_player_list", "minecraft.exec",
                ]
            )

        async def get_player_list(self) -> dict:
            rt = await self._rt()
            if rt is None or rt.rcon is None or not rt.rcon.connected:
                return self._adapter.make_error(retcode=33001, message="RCON 未连接")
            out = await rt.rcon.exec("list")
            players = []
            m = re.search(r"players online:\s*(.*)$", out)
            if m and m.group(1):
                players = [p.strip() for p in m.group(1).split(",") if p.strip()]
            return self._adapter.make_response(data={"players": players, "raw": out})

        async def exec(self, command: str) -> dict:
            """执行任意 RCON 命令"""
            rt = await self._rt()
            if rt is None or rt.rcon is None or not rt.rcon.connected:
                return self._adapter.make_error(retcode=33001, message="RCON 未连接")
            try:
                out = await rt.rcon.exec(command)
                return self._adapter.make_response(data={"command_output": out}, raw={"output": out})
            except RconError as e:
                return self._adapter.make_error(retcode=33001, message=str(e))
