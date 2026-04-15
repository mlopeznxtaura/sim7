# 🌀 7-Layer Simulation · 1ARCHIT3CT1 · NextAura

---

## Stack

```
sim7/
├── static/
│   └── index.html          ← Full 7-layer GUI (open this directly)
├── simulation_backend.py   ← FastAPI backend (production-grade)
└── README.md
```

---

## The 7 Layers

| # | Layer | Vibe |
|---|-------|------|
| 0 | **Outer Cosmos** | Dark void, particle starfield, root container |
| 1 | **Avatar Room** | Buddy ⭐ + Watermelon Head 🍉 (bobbleheads) |
| 2 | **Living Room** | Sofa + TV cabinet (retro CRT) |
| 3 | **TV / Python Script** | The Goliath joke — `G-O-L-I-A-S 😂😂😂😂😂` |
| 4 | **Pixel Arcade** | 3 cabinets: WM-BOUNCE, STAR-RUNNER, G-O-L-I-A-S SMASH |
| 5 | **Dream Sequence** | Logic dissolves, floating orbs, dream fragments |
| 6 | **Quantum Data Room** | 16 qubits, collapse events, live state stream |
| 7 | **The Void Terminal** | Aura terminal, deepest layer, `1ARCHIT3CT1` |

---

## Quick Start — No Install Needed

Just open `static/index.html` in any modern browser. Fully self-contained.

---

## Full Backend (FastAPI)

```bash
pip install fastapi uvicorn
python simulation_backend.py
```

Open **http://localhost:8787**

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check + uptime |
| `/api/snapshot` | GET | Full FSM state snapshot |
| `/api/layers` | GET | All 7 layer states |
| `/api/layers/{id}` | GET | Single layer |
| `/api/avatars` | GET | All avatars |
| `/api/avatars/{id}/shake` | POST | Shake an avatar |
| `/api/avatars/super-shake` | POST | Shake everyone + burst |
| `/api/run-script` | GET | Run Goliath script, return JSON |
| `/api/script/stream` | GET | **SSE** — stream script line by line |
| `/api/script/runs` | GET | All script run history |
| `/api/quantum/qubits` | GET | All 16 qubits + values |
| `/api/quantum/collapse/{label}` | POST | Collapse single qubit |
| `/api/quantum/collapse-all` | POST | Collapse all 16 |
| `/api/events` | GET | Event log (last N entries) |
| `/api/void/echo` | GET | Void terminal responses |
| `ws://localhost:8787/ws` | WS | Real-time broadcast hub |
| `/docs` | GET | Auto-generated OpenAPI docs |

### WebSocket Protocol

Connect to `ws://localhost:8787/ws`

**Receive:**
```json
{ "event": "tick", "payload": { "uptime": 42.1, "qubit_sample": {...} } }
{ "event": "avatar.shake", "payload": { "avatar_id": "wm-01", "shake_count": 5 } }
{ "event": "quantum.collapse", "payload": { "label": "|Ψ⟩", "value": 0.7312 } }
```

**Send:**
```json
{ "event": "ping" }
{ "event": "shake", "avatar_id": "wm-01" }
{ "event": "collapse", "label": "|0⟩" }
```

### Middleware Stack

1. `GZipMiddleware` — compress responses ≥ 500 bytes
2. `CORSMiddleware` — allow all origins
3. `TimingMiddleware` — adds `X-Response-Time` header
4. `RequestIDMiddleware` — adds `X-Request-ID` header
5. `RateLimitMiddleware` — token bucket, 120 req/min per IP

---

## Backend Architecture Notes

- **State machine**: `SimulationFSM` — flat dict ground truth, no agents
- **LLM = stateless worker** (per NextAura arch constants)
- **WebSocket hub**: fan-out broadcast to all connected clients
- **SSE**: streaming script output line-by-line
- **Background tick**: 1s interval, quantum noise + WS broadcast
- **Graceful shutdown**: via FastAPI lifespan context manager
- **Fallback**: if FastAPI not installed, stdlib `http.server` activates automatically

---

*ITERATION IS THE COST OF MORE DATA — BOTH SYNTHETIC + REAL · Cubed 3D*  
*1ARCHIT3CT1 · NextAura, Inc.*
