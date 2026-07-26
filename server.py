"""
Minecraft Panel - Backend Python
Requiere: pip install flask flask-socketio psutil
(ya NO necesita mcrcon)
"""

import os
import re
import time
import socket
import struct
import threading
import psutil
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

from typing import List, Dict, Tuple, Optional

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia-esto-en-produccion")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

RCON_HOST = os.environ.get("RCON_HOST", "127.0.0.1")
RCON_PORT = int(os.environ.get("RCON_PORT", 25575))
RCON_PASSWORD = os.environ.get("RCON_PASSWORD", "tu_password_rcon")
RCON_TIMEOUT = 5  # segundos

rcon_lock = threading.Lock()
server_online = False
last_error = None


# ---------------------------------------------------------------------------
# Implementación RCON sin señales (compatible con hilos secundarios)
# ---------------------------------------------------------------------------

RCON_AUTHENTICATE = 3
RCON_COMMAND = 2


def _rcon_packet(req_id: int, pkt_type: int, payload: str) -> bytes:
    """Construye un paquete RCON."""
    body = payload.encode("utf-8") + b"\x00\x00"
    length = 4 + 4 + len(body)
    return struct.pack("<iii", length, req_id, pkt_type) + body


def _read_rcon_packet(sock: socket.socket) -> Tuple[int, int, str]:
    """Lee un paquete RCON del socket. Devuelve (req_id, tipo, payload)."""
    raw_len = _recv_exact(sock, 4)
    length = struct.unpack("<i", raw_len)[0]
    data = _recv_exact(sock, length)
    req_id, pkt_type = struct.unpack("<ii", data[:8])
    payload = data[8:-2].decode("utf-8", errors="replace")
    return req_id, pkt_type, payload


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Lee exactamente n bytes del socket."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Conexión cerrada por el servidor")
        buf += chunk
    return buf


def _rcon_execute(cmd: str) -> str:
    """
    Abre conexión RCON, autentica y ejecuta un comando.
    Usa socket.settimeout() en lugar de señales → seguro en cualquier hilo.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(RCON_TIMEOUT)
        sock.connect((RCON_HOST, RCON_PORT))

        # Autenticación
        sock.sendall(_rcon_packet(1, RCON_AUTHENTICATE, RCON_PASSWORD))
        req_id, pkt_type, _ = _read_rcon_packet(sock)
        if req_id == -1:
            raise PermissionError("Contraseña RCON incorrecta")

        # Comando
        sock.sendall(_rcon_packet(2, RCON_COMMAND, cmd))
        _, _, response = _read_rcon_packet(sock)
        return response


# ---------------------------------------------------------------------------
# Wrapper con manejo de errores y estado global
# ---------------------------------------------------------------------------

def rcon_command(cmd: str) -> Tuple[bool, str]:
    """Ejecuta un comando RCON y devuelve (éxito, respuesta)."""
    global server_online, last_error
    try:
        with rcon_lock:
            response = _rcon_execute(cmd)
            server_online = True
            last_error = None
            return True, response or "(sin respuesta)"
    except PermissionError as e:
        last_error = str(e)
        server_online = False
        return False, f"RCON error: {e}"
    except ConnectionRefusedError:
        last_error = "Conexión rechazada"
        server_online = False
        return False, "No se pudo conectar al servidor Minecraft"
    except socket.timeout:
        last_error = "Timeout de conexión"
        server_online = False
        return False, "Timeout al conectar con el servidor Minecraft"
    except Exception as e:
        last_error = str(e)
        server_online = False
        return False, f"Error: {e}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_players() -> List[Dict]:
    """Obtiene lista de jugadores online."""
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
    """Intenta leer TPS del servidor (requiere plugin como EssentialsX o similar)."""
    ok, resp = rcon_command("tps")
    if not ok:
        return None
    match = re.search(r"(\d+\.?\d*)", resp)
    if match:
        return float(match.group(1))
    return None


def get_system_stats() -> dict:
    """Estadísticas del sistema donde corre el servidor."""
    return {
        "cpu": round(psutil.cpu_percent(interval=None), 1),
        "ram_used": round(psutil.virtual_memory().used / (1024**3), 2),
        "ram_total": round(psutil.virtual_memory().total / (1024**3), 2),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_used": round(psutil.disk_usage("/").used / (1024**3), 1),
        "disk_total": round(psutil.disk_usage("/").total / (1024**3), 1),
    }


def broadcast_stats():
    """Hilo que emite stats por WebSocket cada 3 segundos."""
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
        except Exception as e:
            print(f"[broadcast_stats] error: {e}")
        time.sleep(3)


# ---------------------------------------------------------------------------
# Rutas HTTP
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    ok, _ = rcon_command("list")
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
    data = request.get_json(force=True)
    cmd = (data.get("command") or "").strip()
    if not cmd:
        return jsonify({"ok": False, "response": "Comando vacío"}), 400

    blocked = ["stop", "restart"]
    if any(cmd.lower().startswith(b) for b in blocked):
        return jsonify({"ok": False, "response": f"Comando '{cmd}' bloqueado desde el panel. Usa los botones de control."}), 403

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
    data = request.get_json(force=True)
    player = data.get("player", "").strip()
    reason = data.get("reason", "Kicked by admin").strip()
    if not player:
        return jsonify({"ok": False, "response": "Nombre de jugador requerido"}), 400
    ok, resp = rcon_command(f"kick {player} {reason}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/ban", methods=["POST"])
def api_ban():
    data = request.get_json(force=True)
    player = data.get("player", "").strip()
    reason = data.get("reason", "Banned by admin").strip()
    if not player:
        return jsonify({"ok": False, "response": "Nombre de jugador requerido"}), 400
    ok, resp = rcon_command(f"ban {player} {reason}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/say", methods=["POST"])
def api_say():
    data = request.get_json(force=True)
    msg = data.get("message", "").strip()
    if not msg:
        return jsonify({"ok": False, "response": "Mensaje vacío"}), 400
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
    data = request.get_json(force=True)
    player = data.get("player", "").strip()
    ok, resp = rcon_command(f"whitelist add {player}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/whitelist/remove", methods=["POST"])
def api_whitelist_remove():
    data = request.get_json(force=True)
    player = data.get("player", "").strip()
    ok, resp = rcon_command(f"whitelist remove {player}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/op", methods=["POST"])
def api_op():
    data = request.get_json(force=True)
    player = data.get("player", "").strip()
    ok, resp = rcon_command(f"op {player}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/deop", methods=["POST"])
def api_deop():
    data = request.get_json(force=True)
    player = data.get("player", "").strip()
    ok, resp = rcon_command(f"deop {player}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/time", methods=["POST"])
def api_time():
    data = request.get_json(force=True)
    value = data.get("value", "day")
    ok, resp = rcon_command(f"time set {value}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/weather", methods=["POST"])
def api_weather():
    data = request.get_json(force=True)
    value = data.get("value", "clear")
    ok, resp = rcon_command(f"weather {value}")
    return jsonify({"ok": ok, "response": resp})


@app.route("/api/gamemode", methods=["POST"])
def api_gamemode():
    data = request.get_json(force=True)
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
    print(f"[WS] Cliente conectado: {request.sid}")


@socketio.on("disconnect")
def on_disconnect():
    print(f"[WS] Cliente desconectado: {request.sid}")


@socketio.on("command")
def on_ws_command(data):
    cmd = (data.get("command") or "").strip()
    if not cmd:
        return
    ok, resp = rcon_command(cmd)
    log_entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "cmd": cmd,
        "response": resp,
        "ok": ok,
    }
    emit("log", log_entry)


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"[Panel] Conectando a RCON en {RCON_HOST}:{RCON_PORT}")

    socketio.start_background_task(broadcast_stats)

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )