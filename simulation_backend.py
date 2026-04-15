#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║   NextAura Simulation Backend  ·  v7.0.0                           ║
║   1ARCHIT3CT1 · 7-Layer Simulation Stack                           ║
║                                                                      ║
║   Stack:                                                            ║
║   · FastAPI (async, production-grade)                               ║
║   · WebSocket hub (real-time layer state broadcast)                 ║
║   · Server-Sent Events (SSE streaming for script output)            ║
║   · Full REST API (health, layers, avatars, quantum, script)        ║
║   · Middleware: CORS, GZip, RequestID, Timing, RateLimit            ║
║   · State machine: 7-layer simulation FSM                           ║
║   · In-memory event bus                                             ║
║   · Graceful shutdown                                               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import os
import random
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import AsyncGenerator, Dict, List, Optional, Set

# ── Conditional FastAPI import ────────────────────────────────────────────────
# Falls back to stdlib if FastAPI not installed, so the file is always valid.
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.gzip import GZipMiddleware
    from fastapi.responses import (
        JSONResponse, StreamingResponse, HTMLResponse, FileResponse
    )
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s · %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sim.backend")

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class LayerStatus(str, Enum):
    BOOT      = "boot"
    ONLINE    = "online"
    DEGRADED  = "degraded"
    DREAMING  = "dreaming"
    COLLAPSED = "collapsed"  # quantum layers only
    VOID      = "void"       # layer 7 only

@dataclass
class SimLayer:
    id: int
    name: str
    status: LayerStatus = LayerStatus.BOOT
    uptime: float = 0.0
    events: int = 0
    meta: dict = field(default_factory=dict)

@dataclass
class Avatar:
    avatar_id: str
    name: str
    kind: str          # "buddy" | "watermelon"
    shake_count: int = 0
    is_shaking: bool = False
    watching: Optional[str] = None   # what they're watching

@dataclass
class QuantumQubit:
    label: str
    value: float = 0.0
    collapsed: bool = False
    collapse_count: int = 0

@dataclass
class ScriptRun:
    run_id: str
    started_at: float
    completed_at: Optional[float] = None
    output: List[str] = field(default_factory=list)
    status: str = "running"   # running | complete | error

# ═══════════════════════════════════════════════════════════════════════════════
#  SIMULATION STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════════════

class SimulationFSM:
    """
    7-layer flat-file-equivalent in-memory state machine.
    Ground truth: self.layers dict.
    No self-orchestrating agents. LLM is a stateless worker.
    """

    LAYER_DEFS = [
        (0, "outer-cosmos",    LayerStatus.ONLINE),
        (1, "avatar-room",     LayerStatus.ONLINE),
        (2, "living-room",     LayerStatus.ONLINE),
        (3, "tv-script",       LayerStatus.ONLINE),
        (4, "arcade",          LayerStatus.ONLINE),
        (5, "dream-sequence",  LayerStatus.DREAMING),
        (6, "quantum-room",    LayerStatus.ONLINE),
        (7, "void-terminal",   LayerStatus.VOID),
    ]

    def __init__(self):
        self._boot_time = time.time()
        self.layers: Dict[int, SimLayer] = {}
        self.avatars: Dict[str, Avatar] = {}
        self.qubits: Dict[str, QuantumQubit] = {}
        self.script_runs: Dict[str, ScriptRun] = {}
        self.event_log: deque = deque(maxlen=500)
        self._init_layers()
        self._init_avatars()
        self._init_qubits()

    def _init_layers(self):
        for lid, name, status in self.LAYER_DEFS:
            self.layers[lid] = SimLayer(id=lid, name=name, status=status,
                                        uptime=0.0, meta={"depth": lid})

    def _init_avatars(self):
        self.avatars["buddy-001"] = Avatar(
            avatar_id="buddy-001", name="Buddy", kind="buddy",
            watching="TV-CH03"
        )
        self.avatars["wm-01"] = Avatar(
            avatar_id="wm-01", name="Watermelon Head", kind="watermelon",
            watching="TV-CH03"
        )

    def _init_qubits(self):
        labels = ['|0⟩','|1⟩','|+⟩','|-⟩','|i⟩','|-i⟩','|Ψ⟩','|Φ⟩',
                  'α','β','γ','δ','σx','σy','σz','H']
        for lbl in labels:
            self.qubits[lbl] = QuantumQubit(label=lbl, value=random.random())

    @property
    def uptime(self) -> float:
        return round(time.time() - self._boot_time, 2)

    def tick(self):
        """Called every second by the background task."""
        up = self.uptime
        for layer in self.layers.values():
            layer.uptime = up
        # probabilistic qubit drift (quantum noise)
        for q in self.qubits.values():
            if not q.collapsed:
                q.value = abs(q.value + random.gauss(0, 0.01)) % 1.0

    def shake_avatar(self, avatar_id: str) -> dict:
        av = self.avatars.get(avatar_id)
        if not av:
            return {"error": "avatar not found"}
        av.shake_count += 1
        av.is_shaking = True
        self._log("avatar.shake", {"id": avatar_id, "count": av.shake_count})
        return {"avatar_id": avatar_id, "shake_count": av.shake_count, "status": "shaking"}

    def collapse_qubit(self, label: str) -> dict:
        q = self.qubits.get(label)
        if not q:
            return {"error": "qubit not found"}
        q.value = random.random()
        q.collapsed = True
        q.collapse_count += 1
        self.layers[6].events += 1
        self._log("quantum.collapse", {"label": label, "value": q.value})
        return {"label": label, "value": round(q.value, 6), "collapsed": True,
                "collapse_count": q.collapse_count}

    def collapse_all_qubits(self) -> List[dict]:
        results = []
        for lbl in self.qubits:
            results.append(self.collapse_qubit(lbl))
        return results

    def new_script_run(self) -> ScriptRun:
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        run = ScriptRun(run_id=run_id, started_at=time.time())
        self.script_runs[run_id] = run
        self.layers[3].events += 1
        self._log("script.start", {"run_id": run_id})
        return run

    def complete_script_run(self, run_id: str, output: List[str]):
        run = self.script_runs.get(run_id)
        if run:
            run.output = output
            run.completed_at = time.time()
            run.status = "complete"
            self._log("script.complete", {"run_id": run_id})

    def _log(self, event: str, data: dict):
        self.event_log.append({
            "ts": time.time(),
            "event": event,
            "data": data,
        })

    def snapshot(self) -> dict:
        return {
            "uptime": self.uptime,
            "layers": {k: asdict(v) for k, v in self.layers.items()},
            "avatar_count": len(self.avatars),
            "qubit_count": len(self.qubits),
            "script_runs": len(self.script_runs),
            "event_log_size": len(self.event_log),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  WEBSOCKET HUB
# ═══════════════════════════════════════════════════════════════════════════════

class WSHub:
    """Broadcast hub — fans out messages to all connected WebSocket clients."""

    def __init__(self):
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info(f"WS client connected · total={len(self._clients)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._clients.discard(ws)
        log.info(f"WS client disconnected · total={len(self._clients)}")

    async def broadcast(self, payload: dict):
        msg = json.dumps(payload)
        dead = set()
        for ws in list(self._clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                self._clients -= dead

    @property
    def client_count(self) -> int:
        return len(self._clients)


# ═══════════════════════════════════════════════════════════════════════════════
#  THE GOLIATH SCRIPT — Source of Truth
# ═══════════════════════════════════════════════════════════════════════════════

def introduce_giant() -> List[str]:
    """
    The canonical Goliath show script.
    Emojis are IN the source. This is intentional. 😂😂😂😂😂
    """
    name_fake  = "Goliath"           # 😂 haha jk
    name_real  = "G-O-L-I-A-S"      # 😂😂😂😂😂
    title      = "the gentle giant"  # 🥹

    lines: List[str] = []
    lines.append(f"Goliath... haha jk 😂")
    lines.append(f"{name_real} 😂😂😂😂😂")
    lines.append(f"({title}) 🥰")
    lines.append("He's big. He's kind. 💪🤍")
    return lines

async def stream_script() -> AsyncGenerator[str, None]:
    """SSE-stream the Goliath script line by line."""
    lines = introduce_giant()
    for i, line in enumerate(lines):
        payload = json.dumps({"line_index": i, "line": line, "total": len(lines)})
        yield f"data: {payload}\n\n"
        await asyncio.sleep(0.7)
    yield f"data: {json.dumps({'line_index': -1, 'line': 'EOF', 'total': len(lines)})}\n\n"


# ═══════════════════════════════════════════════════════════════════════════════
#  MIDDLEWARE — RequestID + Timing
# ═══════════════════════════════════════════════════════════════════════════════

if HAS_FASTAPI:
    from starlette.middleware.base import BaseHTTPMiddleware

    class RequestIDMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            rid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
            request.state.request_id = rid
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response

    class TimingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            t0 = time.perf_counter()
            response = await call_next(request)
            ms = round((time.perf_counter() - t0) * 1000, 2)
            response.headers["X-Response-Time"] = f"{ms}ms"
            return response

    class RateLimitMiddleware(BaseHTTPMiddleware):
        """Simple in-memory token bucket — 60 req/min per IP."""
        def __init__(self, app, rpm: int = 60):
            super().__init__(app)
            self._buckets: Dict[str, List[float]] = defaultdict(list)
            self._rpm = rpm

        async def dispatch(self, request: Request, call_next):
            ip = request.client.host if request.client else "unknown"
            now = time.time()
            bucket = self._buckets[ip]
            # prune entries older than 60s
            self._buckets[ip] = [t for t in bucket if now - t < 60]
            if len(self._buckets[ip]) >= self._rpm:
                return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)
            self._buckets[ip].append(now)
            return await call_next(request)


# ═══════════════════════════════════════════════════════════════════════════════
#  APP FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

def build_app() -> "FastAPI":
    if not HAS_FASTAPI:
        raise RuntimeError("FastAPI not installed. Run: pip install fastapi uvicorn")

    fsm = SimulationFSM()
    hub = WSHub()

    # ── lifespan ──────────────────────────────────────────────────────────────
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("🚀 Simulation backend starting up · layers=7")
        task = asyncio.create_task(_background_tick(fsm, hub))
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("👋 Simulation backend shut down cleanly")

    app = FastAPI(
        title="NextAura Simulation API",
        version="7.0.0",
        description="7-layer simulation backend · 1ARCHIT3CT1",
        lifespan=lifespan,
    )

    # ── middleware stack ───────────────────────────────────────────────────────
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware, rpm=120)

    # ── static files ──────────────────────────────────────────────────────────
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # ══════════════════════════════════════════
    #  REST ROUTES
    # ══════════════════════════════════════════

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def root():
        idx = os.path.join(static_dir, "index.html")
        if os.path.isfile(idx):
            return FileResponse(idx)
        return HTMLResponse("<h1>Simulation backend online. GUI at /static/index.html</h1>")

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "version": "7.0.0",
            "uptime": fsm.uptime,
            "layers": len(fsm.layers),
            "ws_clients": hub.client_count,
            "avatars": len(fsm.avatars),
            "qubits": len(fsm.qubits),
            "script_runs": len(fsm.script_runs),
            "timestamp": time.time(),
        }

    @app.get("/api/snapshot")
    async def snapshot():
        return fsm.snapshot()

    # ── LAYERS ────────────────────────────────────────────────────────────────

    @app.get("/api/layers")
    async def get_layers():
        return {k: asdict(v) for k, v in fsm.layers.items()}

    @app.get("/api/layers/{layer_id}")
    async def get_layer(layer_id: int):
        layer = fsm.layers.get(layer_id)
        if not layer:
            return JSONResponse({"error": "layer not found"}, status_code=404)
        return asdict(layer)

    # ── AVATARS ───────────────────────────────────────────────────────────────

    @app.get("/api/avatars")
    async def get_avatars():
        return {k: asdict(v) for k, v in fsm.avatars.items()}

    @app.post("/api/avatars/{avatar_id}/shake")
    async def shake_avatar(avatar_id: str):
        result = fsm.shake_avatar(avatar_id)
        await hub.broadcast({"event": "avatar.shake", "payload": result})
        return result

    @app.post("/api/avatars/super-shake")
    async def super_shake():
        results = [fsm.shake_avatar(aid) for aid in fsm.avatars]
        await hub.broadcast({"event": "avatar.super_shake", "payload": results})
        return {"shaken": results, "burst": True}

    # ── SCRIPT ────────────────────────────────────────────────────────────────

    @app.get("/api/run-script")
    async def run_script():
        run = fsm.new_script_run()
        output = introduce_giant()
        fsm.complete_script_run(run.run_id, output)
        await hub.broadcast({"event": "script.run", "payload": {"run_id": run.run_id, "output": output}})
        return {
            "run_id": run.run_id,
            "status": "complete",
            "output": output,
            "duration_ms": round((run.completed_at - run.started_at) * 1000, 2),
        }

    @app.get("/api/script/stream")
    async def script_stream():
        """Server-Sent Events — stream Goliath script line by line."""
        return StreamingResponse(
            stream_script(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            }
        )

    @app.get("/api/script/runs")
    async def script_runs():
        return {k: asdict(v) for k, v in fsm.script_runs.items()}

    # ── QUANTUM ───────────────────────────────────────────────────────────────

    @app.get("/api/quantum/qubits")
    async def get_qubits():
        return {k: asdict(v) for k, v in fsm.qubits.items()}

    @app.post("/api/quantum/collapse/{label}")
    async def collapse_qubit(label: str):
        result = fsm.collapse_qubit(label)
        await hub.broadcast({"event": "quantum.collapse", "payload": result})
        return result

    @app.post("/api/quantum/collapse-all")
    async def collapse_all():
        results = fsm.collapse_all_qubits()
        await hub.broadcast({"event": "quantum.collapse_all", "payload": results})
        return {"collapsed": results, "count": len(results)}

    # ── EVENT LOG ─────────────────────────────────────────────────────────────

    @app.get("/api/events")
    async def get_events(limit: int = 50):
        events = list(fsm.event_log)[-limit:]
        return {"events": events, "total": len(fsm.event_log)}

    # ── VOID TERMINAL ─────────────────────────────────────────────────────────

    VOID_RESPONSES = [
        "preserve_the_aura=true · extraction=false · depth=∞",
        "G-O-L-I-A-S 😂😂😂😂😂 · (the gentle giant) 🥰",
        "ITERATION IS THE COST OF MORE DATA — BOTH SYNTHETIC + REAL",
        "layer_depth=7 · all_online · dreaming=true",
        "corpus=50k · comp=$1 · T$=corpus_budget · 1ARCHIT3CT1",
        "flat_file_state=true · no_agents · llm=stateless_worker",
    ]
    _void_idx = 0

    @app.get("/api/void/echo")
    async def void_echo():
        nonlocal _void_idx
        resp = VOID_RESPONSES[_void_idx % len(VOID_RESPONSES)]
        _void_idx += 1
        await hub.broadcast({"event": "void.echo", "payload": {"message": resp}})
        return {"void": resp, "depth": 7, "ts": time.time()}

    # ── WEBSOCKET ─────────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await hub.connect(ws)
        try:
            # Send initial state on connect
            await ws.send_text(json.dumps({
                "event": "init",
                "payload": fsm.snapshot(),
            }))
            # Keep alive — handle incoming messages
            while True:
                try:
                    data = await asyncio.wait_for(ws.receive_text(), timeout=30)
                    msg = json.loads(data)
                    event = msg.get("event", "")
                    if event == "ping":
                        await ws.send_text(json.dumps({"event": "pong", "ts": time.time()}))
                    elif event == "shake":
                        aid = msg.get("avatar_id", "wm-01")
                        result = fsm.shake_avatar(aid)
                        await hub.broadcast({"event": "avatar.shake", "payload": result})
                    elif event == "collapse":
                        label = msg.get("label", "|0⟩")
                        result = fsm.collapse_qubit(label)
                        await hub.broadcast({"event": "quantum.collapse", "payload": result})
                except asyncio.TimeoutError:
                    # Send heartbeat
                    await ws.send_text(json.dumps({"event": "heartbeat", "ts": time.time()}))
        except WebSocketDisconnect:
            pass
        finally:
            await hub.disconnect(ws)

    return app, fsm, hub


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND TICK
# ═══════════════════════════════════════════════════════════════════════════════

async def _background_tick(fsm: SimulationFSM, hub: WSHub):
    """1-second tick: updates FSM state + broadcasts to all WS clients."""
    while True:
        await asyncio.sleep(1)
        fsm.tick()
        if hub.client_count > 0:
            await hub.broadcast({
                "event": "tick",
                "payload": {
                    "uptime": fsm.uptime,
                    "ws_clients": hub.client_count,
                    "qubit_sample": {
                        k: round(v.value, 4)
                        for k, v in list(fsm.qubits.items())[:4]
                    },
                }
            })


# ═══════════════════════════════════════════════════════════════════════════════
#  FALLBACK STDLIB SERVER (no FastAPI)
# ═══════════════════════════════════════════════════════════════════════════════

def _run_stdlib_fallback():
    """If FastAPI/uvicorn aren't installed, serve with stdlib http.server."""
    import json as _json
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    static_dir = os.path.join(os.path.dirname(__file__), "static")

    class FallbackHandler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=static_dir, **kw)

        def do_GET(self):
            if self.path == "/" or self.path == "":
                self.path = "/index.html"
            elif self.path == "/api/health":
                self._json({"status": "ok", "mode": "stdlib-fallback",
                            "uptime": round(time.time() - _boot, 2)})
                return
            elif self.path == "/api/run-script":
                self._json({"status": "complete", "output": introduce_giant()})
                return
            super().do_GET()

        def _json(self, payload):
            body = _json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            log.info(fmt % args)

    _boot = time.time()
    PORT = int(os.getenv("PORT", "8787"))
    server = HTTPServer(("0.0.0.0", PORT), FallbackHandler)
    log.info(f"[stdlib fallback] http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutdown.")
        server.server_close()


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    PORT = int(os.getenv("PORT", "8787"))

    print("""
╔══════════════════════════════════════════════════════════════════════╗
║   🌀  NextAura Simulation Backend  ·  v7.0.0  ·  1ARCHIT3CT1       ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║   GUI:            http://localhost:{port}                              ║
║   Health:         http://localhost:{port}/api/health                   ║
║   All Layers:     http://localhost:{port}/api/layers                   ║
║   Avatars:        http://localhost:{port}/api/avatars                  ║
║   Goliath Script: http://localhost:{port}/api/run-script               ║
║   SSE Stream:     http://localhost:{port}/api/script/stream            ║
║   Quantum:        http://localhost:{port}/api/quantum/qubits           ║
║   Event Log:      http://localhost:{port}/api/events                   ║
║   Void Echo:      http://localhost:{port}/api/void/echo                ║
║   WebSocket:      ws://localhost:{port}/ws                             ║
║   API Docs:       http://localhost:{port}/docs                         ║
║                                                                      ║
║   install deps:  pip install fastapi uvicorn                         ║
╚══════════════════════════════════════════════════════════════════════╝
    """.replace("{port}", str(PORT)))

    if HAS_FASTAPI:
        app, fsm, hub = build_app()
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=PORT,
            log_level="info",
            access_log=True,
            loop="asyncio",
        )
    else:
        log.warning("FastAPI not found. Running stdlib fallback. Install: pip install fastapi uvicorn")
        _run_stdlib_fallback()
