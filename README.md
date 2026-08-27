<div align="center">

<img src="https://img.icons8.com/fluency/96/minecraft-creeper.png" width="90" alt="MC Panel Logo" />

# MC Panel

### A lightweight, real-time web panel to manage your Minecraft server via RCON

<img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
<img src="https://img.shields.io/badge/Flask-Backend-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask" />
<img src="https://img.shields.io/badge/Socket.IO-Realtime-010101?style=for-the-badge&logo=socket.io&logoColor=white" alt="Socket.IO" />
<img src="https://img.shields.io/badge/RCON-Enabled-3B7A57?style=for-the-badge" alt="RCON" />
<img src="https://img.shields.io/badge/License-Apache%202.0-D22128?style=for-the-badge&logo=apache&logoColor=white" alt="License" />

<br />

<img src="https://img.shields.io/badge/status-active-brightgreen?style=flat-square" alt="status" />
<img src="https://img.shields.io/badge/platform-web-blue?style=flat-square" alt="platform" />
<img src="https://img.shields.io/badge/made%20with-%E2%9D%A4-ff69b4?style=flat-square" alt="made with love" />

</div>

<br />

<br />

MC Panel is a compact control center for server administrators who want full RCON access, real-time monitoring, and player management without touching the console. It connects directly to your Minecraft server, exposes a clean REST API, and streams live stats straight to your browser.

## Requirements
- Python 3.10+
- Minecraft server with RCON enabled

## Installation
```bash
cd mcpanel
pip install -r requirements.txt
```

## Minecraft Server Configuration
In `server.properties`:
```
enable-rcon=true
rcon.port=25575
rcon.password=your_password_here
broadcast-rcon-to-ops=false
```

## Running the Panel
### Environment variables (optional, defaults provided):
```bash
export RCON_HOST=127.0.0.1
export RCON_PORT=25575
export RCON_PASSWORD=your_password_here
export SECRET_KEY=change-this-in-production
```
### Start:
```bash
python server.py
```
The panel will be available at: http://localhost:5000

## Structure
```
mcpanel/
├── server.py              # Flask backend + RCON + WebSocket
├── requirements.txt
├── templates/
│   └── index.html         # Panel HTML
└── static/
    ├── css/style.css       # Styles
    └── js/panel.js         # Frontend logic
```

## REST API
| Method | Route | Description |
|--------|------|-------------|
| GET | /api/status | Server status |
| GET | /api/players | Online players |
| POST | /api/command | Execute RCON command |
| POST | /api/kick | Kick player |
| POST | /api/ban | Ban player |
| POST | /api/say | Broadcast message |
| POST | /api/save | Save world |
| GET | /api/whitelist | View whitelist |
| POST | /api/whitelist/add | Add to whitelist |
| POST | /api/whitelist/remove | Remove from whitelist |
| POST | /api/op | Grant OP |
| POST | /api/deop | Revoke OP |
| POST | /api/time | Change world time |
| POST | /api/weather | Change weather |
| POST | /api/gamemode | Change gamemode |

## WebSocket
The frontend connects via Socket.IO and receives:
- `stats` every 3 seconds: players, TPS, CPU, RAM
- `log` every time a command is executed

## Security
- The backend blocks `stop` and `restart` commands from the console (these must be run directly on the server).
- Set `SECRET_KEY` to a random value in production.
- Do not expose the panel to the internet without additional authentication (nginx + htpasswd or similar).

<br />

<div align="center">

<sub>Built for server administrators who want speed, clarity, and control.</sub>

</div>
