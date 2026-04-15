# NextAura Dimensional Simulation

sim7 is now a backend-driven dimensional simulation instead of a single static HTML scene.

## Files

- `simulation_backend.py`: FastAPI backend with authoritative world state, WebSocket broadcasts, SSE script stream, and REST control endpoints.
- `static/index.html`: viewport shell and control layout.
- `static/styles.css`: simulation UI styling.
- `static/app.js`: browser orchestration, controls, sockets, and HUD updates.
- `static/renderer.js`: dependency-free 3D canvas renderer for layers, entities, and links.

## Run

```bash
pip install -r requirements.txt
python simulation_backend.py
```

Open `http://localhost:8787`

## Core Endpoints

- `GET /api/health`
- `GET /api/world`
- `POST /api/world/reset`
- `POST /api/avatars/{avatar_id}/shake`
- `POST /api/avatars/super-shake`
- `GET /api/script/stream`
- `POST /api/quantum/collapse/{label}`
- `POST /api/quantum/collapse-all`
- `GET /api/void/echo`
- `POST /api/camera/focus/{layer_id}`
- `POST /api/arcade/{cabinet_id}/play`
- `GET /api/events`
- `ws://localhost:8787/ws`

## Notes

- The frontend expects to be served by the backend at the same origin.
- Drag the canvas to orbit the camera.
- Use the mouse wheel to zoom.
- The renderer consumes the authoritative `world` snapshot rather than local decorative timers.
