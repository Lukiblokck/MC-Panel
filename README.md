# MC Panel

Panel web para gestionar un servidor de Minecraft vía RCON.

## Requisitos

- Python 3.10+
- Servidor Minecraft con RCON habilitado

## Instalación

```bash
cd mcpanel
pip install -r requirements.txt
```

## Configuración del servidor Minecraft

En `server.properties`:

```
enable-rcon=true
rcon.port=25575
rcon.password=tu_password_aqui
broadcast-rcon-to-ops=false
```

## Ejecutar el panel

### Variables de entorno (opcional, hay valores por defecto):

```bash
export RCON_HOST=127.0.0.1
export RCON_PORT=25575
export RCON_PASSWORD=tu_password_aqui
export SECRET_KEY=cambia-esto-produccion
```

### Iniciar:

```bash
python server.py
```

El panel queda disponible en: http://localhost:5000

## Estructura

```
mcpanel/
├── server.py              # Backend Flask + RCON + WebSocket
├── requirements.txt
├── templates/
│   └── index.html         # HTML del panel
└── static/
    ├── css/style.css       # Estilos
    └── js/panel.js         # Lógica frontend
```

## API REST

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /api/status | Estado del servidor |
| GET | /api/players | Jugadores online |
| POST | /api/command | Ejecutar comando RCON |
| POST | /api/kick | Kickear jugador |
| POST | /api/ban | Banear jugador |
| POST | /api/say | Mensaje broadcast |
| POST | /api/save | Guardar mundo |
| GET | /api/whitelist | Ver whitelist |
| POST | /api/whitelist/add | Añadir a whitelist |
| POST | /api/whitelist/remove | Quitar de whitelist |
| POST | /api/op | Dar OP |
| POST | /api/deop | Quitar OP |
| POST | /api/time | Cambiar hora del mundo |
| POST | /api/weather | Cambiar clima |
| POST | /api/gamemode | Cambiar gamemode |

## WebSocket

El frontend se conecta por Socket.IO y recibe:

- `stats` cada 3 segundos: jugadores, TPS, CPU, RAM
- `log` cada vez que se ejecuta un comando

## Seguridad

- El backend bloquea los comandos `stop` y `restart` desde la consola (deben ejecutarse en el servidor directamente).
- Configura `SECRET_KEY` con un valor aleatorio en producción.
- No expongas el panel a internet sin autenticación adicional (nginx + htpasswd o similar).
