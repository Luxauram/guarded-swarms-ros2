# Web Dashboard

A lightweight real-time dashboard for monitoring the Guarded Swarms coordination system. It bridges ROS 2 token topics to a browser-based UI via WebSocket, so you can watch agents request and receive zone access live without touching the terminal.

## What it shows

- **Event stream** - live geometry and authorization token events, color-coded by outcome (approved / rejected / revoked).
- **Statistics** - total requests, approval rate, and per-agent breakdowns, updated automatically.
- **Charts** - approval timeline and priority distribution histogram.
- **Control panel** - start/stop the coordination demo directly from the browser, run whitelisted Makefile targets, reset statistics.

## Stack

| Layer     | Technology                        |
| --------- | --------------------------------- |
| Backend   | FastAPI + uvicorn                 |
| Transport | WebSocket (no polling)            |
| ROS 2     | rclpy subscriber in daemon thread |
| Frontend  | Typescript + Tailwind + Chart.js  |

## Quick start

```bash
# 1 - install Python dependencies
cd /workspace/src/web_dashboard/backend
pip3 install -r requirements.txt --break-system-packages

# 2 - start the dashboard server
python3 -m app

# 3 - open the browser
http://localhost:8765
```

The ROS 2 system (demo.launch.py) can be started and stopped directly from the dashboard's control panel, or manually from a separate terminal:

```bash
ros2 launch /workspace/src/tools/launch/demo.launch.py
```

## Project layout

```
web_dashboard/
├── README.md
├── backend/
│   ├── app.py                  # FastAPI entry point and lifecycle
│   ├── config.py               # All settings (env-overridable)
│   ├── requirements.txt
│   ├── models/
│   │   └── token.py            # Pydantic schemas
│   ├── routers/
│   │   ├── websocket.py        # /ws endpoint and connection manager
│   │   ├── system.py           # /api/system - stats, events, health
│   │   ├── makefile.py         # /api/makefile - whitelisted build commands
│   │   └── demo.py             # /api/demo - demo process lifecycle
│   └── services/
│       ├── ros2_bridge.py      # ROS 2 subscriber → async bridge
│       └── token_processor.py  # Event aggregation and statistics
└── frontend/
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    ├── constants/
    │   ├── charts.constants.ts
    │   ├── main.constants.ts
    │   └── websocket.constants.ts
    ├── src/
    │   ├── charts.ts           # Chart.js initialization and updates
    │   ├── main.ts             # Token handlers and UI interactions
    │   └── websocket.ts        # WebSocket client and reconnection logic
    ├── types/
    │   ├── charts.types.ts
    │   ├── main.types.ts
    │   └── websocket.types.ts
    └── dist/                   # Compiled JS output (gitignored)
        ├── charts.js
        ├── main.js
        └── websocket.js
```

## Key API endpoints

| Method | Path                    | Description                       |
| ------ | ----------------------- | --------------------------------- |
| WS     | `/ws`                   | Real-time event stream            |
| GET    | `/api/system/stats`     | Current coordination statistics   |
| GET    | `/api/system/events`    | Recent token event history        |
| GET    | `/api/system/health`    | Service health check              |
| POST   | `/api/demo/start`       | Launch coordination demo          |
| POST   | `/api/demo/stop`        | Terminate coordination demo       |
| GET    | `/api/demo/status`      | Check whether demo is running     |
| POST   | `/api/makefile/execute` | Run a whitelisted Makefile target |

## Security note

This is a development tool - there is no authentication, CORS is open, and Makefile commands run with container permissions. Do not expose it publicly without a reverse proxy, HTTPS, and proper access controls.

## License

Apache-2.0 - Copyright 2026 Luca D'Aurizio
