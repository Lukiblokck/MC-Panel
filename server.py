"""
Minecraft Panel - Python Backend
Requires: pip install flask flask-socketio psutil
(mcrcon is NO LONGER needed)
"""

import os
import re
import time
import socket
import struct
import logging
import threading
from datetime import datetime
from typing import List, Dict, Tuple, Optional

import psutil
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mcpanel")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# SECURITY: no real-looking default secrets in source. If the env var isn't
# set, we generate a random throwaway value at startup instead of shipping
# a fixed secret in the code (which is unsafe the moment this file is
# committed to git, shared, or reused across deployments).

def _get_required_or_random(env_name: str, purpose: str) -> str:
    value = os.environ.get(env_name)
    if value:
        return value
    random_value = os.urandom(24).hex()
    log.warning(
        "%s is not set. Generated a random %s for this run only "
        "(it will change on every restart). Set %s in your environment "
        "or .env file for a stable value.",
        env_name, purpose, env_name,
    )
    return random_value


app = Flask(__name__)
app.config["SECRET_KEY"] = _get_required_or_random("SECRET_KEY", "Flask secret key")

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
socketio = SocketIO(app, cors_allowed_origins=CORS_ORIGINS, async_mode="threading")

RCON_HOST = os.environ.get("RCON_HOST", "127.0.0.1")
RCON_PORT = int(os.environ.get("RCON_PORT", 25575))
RCON_PASSWORD = os.environ.get("RCON_PASSWORD")  # must be set explicitly, no fallback
RCON_TIMEOUT = int(os.environ.get("RCON_TIMEOUT", 5))  # seconds
STATS_INTERVAL = int(os.environ.get("STATS_INTERVAL", 3))  # seconds

# Commands that must never be run from the panel (require direct server access)
BLOCKED_COMMANDS = ("stop", "restart")

if not RCON_PASSWORD:
    log.error(
        "RCON_PASSWORD is not set. Set it in your environment (matching "
        "server.properties) before starting the panel. Exiting."
    )
    raise SystemExit(1)

rcon_lock = threading.Lock()
server_online = False
last_error: Optional[str] = None


# ---------------------------------------------------------------------------
# RCON implementation without signals (compatible with worker threads)
# ---------------------------------------------------------------------------

RCON_AUTHENTICATE = 3
RCON_COMMAND = 2


def _rcon_packet(req_id: int, pkt_type: int, payload: str) -> bytes:
    """Builds an RCON packet."""
    body = payload.encode("utf-8") + b"\x00\x00"
    length = 4 + 4 + len(body)
    return struct.pack("<iii", length, req_id, pkt_type) + body


def _read_rcon_packet(sock: socket.socket) -> Tuple[int, int, str]:
    """Reads an RCON packet from the socket. Returns (req_id, type, payload)."""
    raw_len = _recv_exact(sock, 4)
    length = struct.unpack("<i", raw_len)[0]
    data = _recv_exact(sock, length)
    req_id, pkt_type = struct.unpack("<ii", data[:8])
    payload = data[8:-2].decode("utf-8", errors="replace")
    return req_id, pkt_type, payload


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Reads exactly n bytes from the socket."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed by server")
        buf += chunk
    return buf


def _rcon_execute(cmd: str) -> str:
    """
    Opens an RCON connection, authenticates, and executes a command.
    Uses socket.settimeout() instead of signals -> safe in any thread.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(RCON_TIMEOUT)
        sock.connect((RCON_HOST, RCON_PORT))

        # Authentication
        sock.sendall(_rcon_packet(1, RCON_AUTHENTICATE, RCON_PASSWORD))
        req_id, pkt_type, _ = _read_rcon_packet(sock)
        if req_id == -1:
            raise PermissionError("Incorrect RCON password")

        # Command
        sock.sendall(_rcon_packet(2, RCON_COMMAND, cmd))
        _, _, response = _read_rcon_packet(sock)
        return response


# ---------------------------------------------------------------------------
# Wrapper with error handling and global state
# ---------------------------------------------------------------------------

def rcon_command(cmd: str) -> Tuple[bool, str]:
    """Executes an RCON command and returns (success, response)."""
    global server_online, last_error
    try:
        with rcon_lock:
            response = _rcon_execute(cmd)
            server_online = True
            last_error = None
            return True, response or "(no response)"
    except PermissionError as e:
        last_error = str(e)
        server_online = False
        log.error("RCON auth failed: %s", e)
        return False, f"RCON error: {e}"
    except ConnectionRefusedError:
        last_error = "Connection refused"
        server_online = False
        return False, "Could not connect to the Minecraft server"
    except socket.timeout:
        last_error = "Connection timeout"
        server_online = False
        return False, "Timed out connecting to the Minecraft server"
    except OSError as e:
        # Covers host-unreachable, network-down, and similar low-level socket errors
        last_error = str(e)
        server_online = False
        log.error("RCON socket error: %s", e)
        return False, f"Network error: {e}"
    except Exception as e:
        last_error = str(e)
        server_online = False
        log.exception("Unexpected RCON error")
        return False, f"Error: {e}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_players() -> List[Dict]:
    """Gets the list of online players."""
    ok, resp = rcon_command("list")
    if not ok:
        return []
    players = []
    match = re.search(r"online: (.+)", resp)
    if match and match.group(1).strip():
        names = [n.strip() for n in match.group(1).split(",") if n.strip()]
        for name in names:
            players.append({"name": name, "ping": None})
    return players


def get_tps() -> Optional[float]:
    """Attempts to read the server's TPS (requires a plugin like EssentialsX or similar)."""
    ok, resp = rcon_command("tps")
    if not ok:
        return None
    match = re.search(r"(\d+\.?\d*)", resp)
    if match:
        return float(match.group(1))
    return None


def get_system_stats() -> dict:
    """Stats for the system running the server."""
    return {
        "cpu": round(psutil.cpu_percent(interval=None), 1),
        "ram_used": round(psutil.virtual_memory().used / (1024**3), 2),
        "ram_total": round(psutil.virtual_memory().total / (1024**3), 2),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_used": round(psutil.disk_usage("/").used / (1024**3), 1),
        "disk_total": round(psutil.disk_usage("/").total / (1024**3), 1),
    }


def is_command_blocked(cmd: str) -> bool:
    """Checks whether a command's first word matches a blocked command exactly
    (so 'stop' is blocked but 'stopwatch' or similar is not)."""
    first_word = cmd.strip().lower().split(" ", 1)[0]
    return first_word in BLOCKED_COMMANDS


def broadcast_stats():
    """Background thread that emits stats over WebSocket every STATS_INTERVAL seconds."""
    while True:
        try:
            stats = get_system_stats()
            tps = get_tps() if server_online else None
            players = get_players() if server_online else []

            payload = {
                "online": server_online,
                "players": players,
                "player_count": len(players),
                "tps": tps,
                "system": stats,
                "timestamp": datetime.now().isoformat(),
            }
            socketio.emit("stats", payload)
        except Exception:
            log.exception("Error in broadcast_stats")
        time.sleep(STATS_INTERVAL)


# ---------------------------------------------------------------------------
# HTTP Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    rcon_command("list")
    return jsonify({
        "online": server_online,
        "host": RCON_HOST,
        "port": RCON_PORT,
        "error": last_error,
    })


@app.route("/api/players")
def api_players():
    players = get_players()
    return jsonify({"players": players, "count": len(players)})


@app.route("/api/command", methods=["POST"])
def api_command():
    data = request.get_json(force=True) or {}
    cmd = (data.get("command") or "").strip()
    if not cmd:
        return jsonify({"ok": False, "response": "Empty command"}), 400

    if is_command_blocked(cmd):
        return jsonify({
            "ok": False,
            "response": f"Command '{cmd}' is blocked from the panel. Use the control buttons instead.",
        }), 403

    ok, resp = rcon_command(cmd)
    log_entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "cmd": cmd,
        "response": resp,
        "ok": ok,
    }
    socketio.emit("log", log_entry)
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/kick", methods=["POST"])
def api_kick():
    data = request.get_json(force=True) or {}
    player = data.get("player", "").strip()
    reason = data.get("reason", "Kicked by admin").strip()
    if not player:
        return jsonify({"ok": False, "response": "Player name required"}), 400
    ok, resp = rcon_command(f"kick {player} {reason}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/ban", methods=["POST"])
def api_ban():
    data = request.get_json(force=True) or {}
    player = data.get("player", "").strip()
    reason = data.get("reason", "Banned by admin").strip()
    if not player:
        return jsonify({"ok": False, "response": "Player name required"}), 400
    ok, resp = rcon_command(f"ban {player} {reason}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/say", methods=["POST"])
def api_say():
    data = request.get_json(force=True) or {}
    msg = data.get("message", "").strip()
    if not msg:
        return jsonify({"ok": False, "response": "Empty message"}), 400
    ok, resp = rcon_command(f"say {msg}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/save", methods=["POST"])
def api_save():
    ok, resp = rcon_command("save-all")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/whitelist", methods=["GET"])
def api_whitelist():
    ok, resp = rcon_command("whitelist list")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/whitelist/add", methods=["POST"])
def api_whitelist_add():
    data = request.get_json(force=True) or {}
    player = data.get("player", "").strip()
    if not player:
        return jsonify({"ok": False, "response": "Player name required"}), 400
    ok, resp = rcon_command(f"whitelist add {player}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/whitelist/remove", methods=["POST"])
def api_whitelist_remove():
    data = request.get_json(force=True) or {}
    player = data.get("player", "").strip()
    if not player:
        return jsonify({"ok": False, "response": "Player name required"}), 400
    ok, resp = rcon_command(f"whitelist remove {player}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/op", methods=["POST"])
def api_op():
    data = request.get_json(force=True) or {}
    player = data.get("player", "").strip()
    if not player:
        return jsonify({"ok": False, "response": "Player name required"}), 400
    ok, resp = rcon_command(f"op {player}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/deop", methods=["POST"])
def api_deop():
    data = request.get_json(force=True) or {}
    player = data.get("player", "").strip()
    if not player:
        return jsonify({"ok": False, "response": "Player name required"}), 400
    ok, resp = rcon_command(f"deop {player}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/time", methods=["POST"])
def api_time():
    data = request.get_json(force=True) or {}
    value = data.get("value", "day")
    ok, resp = rcon_command(f"time set {value}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/weather", methods=["POST"])
def api_weather():
    data = request.get_json(force=True) or {}
    value = data.get("value", "clear")
    ok, resp = rcon_command(f"weather {value}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/gamemode", methods=["POST"])
def api_gamemode():
    data = request.get_json(force=True) or {}
    mode = data.get("mode", "survival")
    player = data.get("player", "")
    cmd = f"gamemode {mode} {player}".strip()
    ok, resp = rcon_command(cmd)
    return jsonify({"ok": ok, "response": resp})


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@socketio.on("connect")
def on_connect():
    log.info("Client connected: %s", request.sid)


@socketio.on("disconnect")
def on_disconnect():
    log.info("Client disconnected: %s", request.sid)


@socketio.on("command")
def on_ws_command(data):
    """Handles a command sent over the WebSocket connection."""
    cmd = (data.get("command") or "").strip()
    if not cmd:
        return

    if is_command_blocked(cmd):
        emit("log", {
            "time": datetime.now().strftime("%H:%M:%S"),
            "cmd": cmd,
            "response": f"Command '{cmd}' is blocked from the panel.",
            "ok": False,
        })
        return

    # BUG FIX: the command was validated but never actually executed.
    ok, resp = rcon_command(cmd)
    socketio.emit("log", {
        "time": datetime.now().strftime("%H:%M:%S"),
        "cmd": cmd,
        "response": resp,
        "ok": ok,
    })


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
# BUG FIX: this block used to be nested inside on_ws_command(), so the app
# never actually started listening — it just reached end-of-file and exited
# with status 0 the moment the module finished loading.

if __name__ == "__main__":
    socketio.start_background_task(broadcast_stats)
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
