# MC Panel

Web panel to manage a Minecraft server via RCON.

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