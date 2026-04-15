#!/usr/bin/env python3
"""
NextAura Simulation Backend v8.0.0

A dimensional simulation backend with an authoritative world model,
recursive layer metadata, and real-time broadcast updates for the
browser renderer.
"""

import asyncio
import json
import logging
import math
import os
import random
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Deque, Dict, List, Optional, Set

try:
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.gzip import GZipMiddleware
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sim7.backend")


class LayerStatus(str, Enum):
    BOOT = "boot"
    ONLINE = "online"
    DEGRADED = "degraded"
    DREAMING = "dreaming"
    COLLAPSED = "collapsed"
    VOID = "void"


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
    kind: str
    shake_count: int = 0
    is_shaking: bool = False
    watching: Optional[str] = None


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
    status: str = "running"


@dataclass
class EntityState:
    entity_id: str
    layer_id: int
    kind: str
    label: str
    position: dict
    rotation: dict
    scale: float = 1.0
    energy: float = 0.0
    color: str = "#ffffff"
    state: dict = field(default_factory=dict)


@dataclass
class LayerLink:
    source_layer: int
    target_layer: int
    kind: str = "containment"
    flux: float = 0.0


@dataclass
class CameraRig:
    focus_layer: int = 2
    orbit: float = 0.45
    elevation: float = 0.24
    distance: float = 18.0
    roll: float = 0.0


class SimulationFSM:
    LAYER_DEFS = [
        (0, "outer-cosmos", LayerStatus.ONLINE),
        (1, "avatar-room", LayerStatus.ONLINE),
        (2, "living-room", LayerStatus.ONLINE),
        (3, "tv-script", LayerStatus.ONLINE),
        (4, "arcade", LayerStatus.ONLINE),
        (5, "dream-sequence", LayerStatus.DREAMING),
        (6, "quantum-room", LayerStatus.ONLINE),
        (7, "void-terminal", LayerStatus.VOID),
    ]

    SCRIPT_LINES = [
        "Goliath... haha jk",
        "G-O-L-I-A-S",
        "(the gentle giant)",
        "He's big. He's kind.",
    ]

    VOID_RESPONSES = [
        "preserve_the_aura=true | extraction=false | depth=inf",
        "G-O-L-I-A-S | dimensional laughter cascade detected",
        "iteration cost accepted | more data incoming",
        "layer_depth=8 | resonance stable | dream flux rising",
        "flat_state=true | agents=0 | renderer=dimensional",
        "camera target descending toward the void terminal",
    ]

    QUBIT_LABELS = [
        "|0>", "|1>", "|+>", "|->", "|i>", "|-i>", "|Psi>", "|Phi>",
        "alpha", "beta", "gamma", "delta", "sigma-x", "sigma-y", "sigma-z", "H",
    ]

    ARCADE_CABINETS = {
        "wm-bounce": "WM-BOUNCE",
        "star-runner": "STAR-RUNNER",
        "golias-smash": "G-O-L-I-A-S SMASH",
    }

    def __init__(self):
        self._boot_time = time.time()
        self._last_tick = self._boot_time
        self.layers: Dict[int, SimLayer] = {}
        self.avatars: Dict[str, Avatar] = {}
        self.qubits: Dict[str, QuantumQubit] = {}
        self.script_runs: Dict[str, ScriptRun] = {}
        self.entities: Dict[str, EntityState] = {}
        self.links: List[LayerLink] = []
        self.event_log: Deque[dict] = deque(maxlen=800)
        self.void_messages: Deque[str] = deque(maxlen=24)
        self.last_script_output: List[str] = []
        self.camera = CameraRig()
        self.arcade_scores = {key: 0 for key in self.ARCADE_CABINETS}
        self.disturbance = 0.18
        self.script_activity = 0.15
        self.quantum_flux = 0.0
        self.dream_flux = 0.0
        self.void_pressure = 0.0
        self._void_index = 0
        self._init_layers()
        self._init_avatars()
        self._init_qubits()
        self._init_links()
        self._init_entities()
        self.tick(force=True)

    @staticmethod
    def _vec(x: float, y: float, z: float) -> dict:
        return {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)}

    @property
    def uptime(self) -> float:
        return round(time.time() - self._boot_time, 2)

    def reset(self):
        fresh = SimulationFSM()
        self.__dict__.update(fresh.__dict__)

    def _init_layers(self):
        for lid, name, status in self.LAYER_DEFS:
            self.layers[lid] = SimLayer(
                id=lid,
                name=name,
                status=status,
                meta={
                    "depth": lid,
                    "parent": lid - 1 if lid > 0 else None,
                    "children": [lid + 1] if lid < len(self.LAYER_DEFS) - 1 else [],
                },
            )

    def _init_avatars(self):
        self.avatars["buddy-001"] = Avatar("buddy-001", "Buddy", "buddy", watching="TV-CH03")
        self.avatars["wm-01"] = Avatar("wm-01", "Watermelon Head", "watermelon", watching="TV-CH03")

    def _init_qubits(self):
        for label in self.QUBIT_LABELS:
            self.qubits[label] = QuantumQubit(label=label, value=random.random())

    def _init_links(self):
        self.links = [LayerLink(source_layer=lid, target_layer=lid + 1) for lid in range(len(self.LAYER_DEFS) - 1)]

    def _init_entities(self):
        self.entities = {
            "cosmos-core": EntityState("cosmos-core", 0, "core", "Cosmos Core", self._vec(0.0, 0.0, 0.0), self._vec(0.0, 0.0, 0.0), 1.8, 0.45, "#ffd36e", {"glow": 0.4}),
            "buddy-001": EntityState("buddy-001", 1, "avatar", "Buddy", self._vec(-1.6, -0.1, -4.4), self._vec(0.0, 0.0, 0.0), 0.78, 0.4, "#54e1c1", {"impulse": 0.0}),
            "wm-01": EntityState("wm-01", 1, "avatar", "Watermelon Head", self._vec(1.6, -0.08, -4.6), self._vec(0.0, 0.0, 0.0), 0.92, 0.45, "#ff7b5c", {"impulse": 0.0}),
            "observation-bridge": EntityState("observation-bridge", 2, "bridge", "Observation Bridge", self._vec(0.0, -0.72, -8.8), self._vec(0.0, 0.0, 0.0), 1.4, 0.28, "#f4f0db", {}),
            "tv-core": EntityState("tv-core", 2, "screen", "Goliath TV", self._vec(0.0, 0.25, -9.2), self._vec(0.0, 0.0, 0.0), 1.1, 0.5, "#f6bf45", {"scan": 0.0}),
            "script-beam": EntityState("script-beam", 3, "glyph", "Script Beam", self._vec(0.0, 0.6, -13.4), self._vec(0.0, 0.0, 0.0), 0.95, 0.55, "#8ae0ff", {}),
            "gorilla-node": EntityState("gorilla-node", 3, "totem", "Gorilla Node", self._vec(2.4, 0.2, -12.9), self._vec(0.0, 0.0, 0.0), 0.65, 0.4, "#ff9c74", {}),
            "wm-bounce": EntityState("wm-bounce", 4, "cabinet", "WM-BOUNCE", self._vec(-2.2, -0.25, -17.1), self._vec(0.0, 0.0, 0.0), 0.86, 0.38, "#3bd28d", {"score": 0}),
            "star-runner": EntityState("star-runner", 4, "cabinet", "STAR-RUNNER", self._vec(0.0, -0.25, -17.3), self._vec(0.0, 0.0, 0.0), 0.86, 0.4, "#f2d15b", {"score": 0}),
            "golias-smash": EntityState("golias-smash", 4, "cabinet", "G-O-L-I-A-S SMASH", self._vec(2.2, -0.25, -17.5), self._vec(0.0, 0.0, 0.0), 0.86, 0.42, "#ff8d71", {"score": 0}),
            "void-terminal": EntityState("void-terminal", 7, "terminal", "Aura Terminal", self._vec(0.0, -0.1, -29.5), self._vec(0.0, 0.0, 0.0), 1.15, 0.5, "#f2f0ea", {}),
            "aura-core": EntityState("aura-core", 7, "aura", "Aura Core", self._vec(0.0, 1.25, -30.2), self._vec(0.0, 0.0, 0.0), 0.82, 0.52, "#8fd8ff", {}),
        }
        dream_colors = ["#ff8d71", "#f6bf45", "#54e1c1", "#8ae0ff", "#f7a8d5", "#f2f0ea"]
        for idx in range(6):
            key = f"dream-orb-{idx}"
            self.entities[key] = EntityState(key, 5, "orb", f"Dream Orb {idx + 1}", self._vec(0.0, 0.0, -21.0), self._vec(0.0, 0.0, 0.0), 0.45 + idx * 0.04, 0.28, dream_colors[idx], {"phase": idx * 0.7})
        for idx, label in enumerate(self.QUBIT_LABELS):
            entity_id = f"qubit-{idx:02d}"
            self.entities[entity_id] = EntityState(entity_id, 6, "qubit", label, self._vec(0.0, 0.0, -25.0), self._vec(0.0, 0.0, 0.0), 0.34, 0.36, "#9ee6ff", {"label": label, "flash": 0.0})

    def _log(self, event: str, data: dict):
        self.event_log.append({"ts": round(time.time(), 3), "event": event, "data": data})

    def _layer_anchor(self, layer_id: int, t: float) -> dict:
        drift = layer_id * 0.12
        return self._vec(math.sin(t * 0.18 + drift) * 0.28 * layer_id, math.cos(t * 0.12 + drift) * 0.14 * layer_id, -4.18 * layer_id)

    def _layer_dimensions(self, layer_id: int) -> dict:
        return self._vec(max(3.2, 9.8 - layer_id * 0.62), max(2.4, 6.6 - layer_id * 0.44), max(1.6, 3.9 - layer_id * 0.22))
    def tick(self, force: bool = False):
        now = time.time()
        dt = 0.2 if force else max(0.05, min(0.5, now - self._last_tick))
        self._last_tick = now
        t = now - self._boot_time
        up = self.uptime

        self.script_activity = max(0.08, self.script_activity * (0.986 if force else 0.978))
        self.disturbance = max(0.06, self.disturbance * (0.988 if force else 0.968))

        total_qubits = len(self.qubits)
        collapsed = 0
        qubit_values: List[float] = []

        for idx, qubit in enumerate(self.qubits.values()):
            phase = t * (0.7 + idx * 0.015) + idx * 0.33
            drift = math.sin(phase) * 0.006 + random.uniform(-0.004, 0.004)
            if qubit.collapsed:
                qubit.value = min(1.0, max(0.0, qubit.value + drift * 0.35))
                if random.random() < 0.018 * dt * 6:
                    qubit.collapsed = False
            else:
                qubit.value = min(1.0, max(0.0, qubit.value + drift))
            if qubit.collapsed:
                collapsed += 1
            qubit_values.append(qubit.value)

        collapsed_ratio = collapsed / total_qubits if total_qubits else 0.0
        self.quantum_flux = sum(qubit_values) / total_qubits if total_qubits else 0.0
        self.dream_flux = min(1.0, 0.32 + self.quantum_flux * 0.38 + collapsed_ratio * 0.3 + self.script_activity * 0.2)
        self.void_pressure = min(1.0, 0.2 + len(self.void_messages) * 0.04 + self.disturbance * 0.22)

        for layer in self.layers.values():
            depth = layer.id / (len(self.layers) - 1)
            layer.uptime = up
            layer_energy = min(1.0, 0.16 + (1.0 - depth) * 0.18 + self.script_activity * 0.15)
            layer_energy += self.quantum_flux * 0.08
            layer_energy += self.dream_flux * (0.18 if layer.id >= 5 else 0.03)
            layer_energy += self.void_pressure * (0.14 if layer.id == 7 else 0.02)
            resonance = min(1.0, 0.22 + self.quantum_flux * 0.46 + depth * 0.16)
            distortion = min(1.0, self.disturbance * 0.45 + self.dream_flux * (0.62 if layer.id >= 5 else 0.14))
            layer.meta.update(
                {
                    "depth": layer.id,
                    "anchor": self._layer_anchor(layer.id, t),
                    "dimensions": self._layer_dimensions(layer.id),
                    "energy": round(layer_energy, 4),
                    "resonance": round(resonance, 4),
                    "distortion": round(distortion, 4),
                    "focus": layer.id == self.camera.focus_layer,
                    "parent": layer.id - 1 if layer.id > 0 else None,
                    "children": [layer.id + 1] if layer.id < len(self.layers) - 1 else [],
                }
            )

        focus_anchor = self.layers[self.camera.focus_layer].meta["anchor"]
        self.camera.orbit += dt * (0.11 + self.layers[self.camera.focus_layer].meta["energy"] * 0.04)
        self.camera.elevation = 0.18 + math.sin(t * 0.15) * 0.05 + self.layers[5].meta["distortion"] * 0.04
        self.camera.distance = max(6.2, 19.4 - self.camera.focus_layer * 1.05 + self.layers[self.camera.focus_layer].meta["distortion"] * 1.2)
        self.camera.roll = math.sin(t * 0.07 + self.camera.focus_layer * 0.35) * 0.015

        for avatar_id, phase in (("buddy-001", 0.0), ("wm-01", 0.8)):
            entity = self.entities[avatar_id]
            impulse = float(entity.state.get("impulse", 0.0)) * 0.9
            if impulse < 0.02:
                impulse = 0.0
            entity.state["impulse"] = round(impulse, 4)
            entity.energy = round(min(1.2, 0.32 + impulse * 0.45 + self.script_activity * 0.12), 4)
            avatar = self.avatars[avatar_id]
            avatar.is_shaking = impulse > 0.08
            entity.position = self._vec(
                (-1.6 if avatar_id == "buddy-001" else 1.55) + math.sin(t * 1.2 + phase) * 0.12,
                -0.15 + math.sin(t * 3.0 + phase) * 0.16 + impulse * 0.75,
                -4.55 + math.cos(t * 1.8 + phase) * 0.18,
            )
            entity.rotation = self._vec(math.sin(t * 2.6 + phase) * 0.12, math.cos(t * 1.3 + phase) * 0.22, math.sin(t * 3.4 + phase) * 0.08 + impulse * 0.24)

        cosmos = self.entities["cosmos-core"]
        cosmos.energy = round(0.36 + self.quantum_flux * 0.22 + self.void_pressure * 0.18, 4)
        cosmos.position = self._vec(math.sin(t * 0.25) * 0.65, math.cos(t * 0.2) * 0.4, math.sin(t * 0.15) * 0.55)
        cosmos.rotation = self._vec(t * 0.04, t * 0.06, 0.0)

        bridge = self.entities["observation-bridge"]
        bridge.energy = round(0.24 + self.layers[2].meta["energy"] * 0.46, 4)
        bridge.position = self._vec(0.0, -0.84 + math.sin(t * 0.85) * 0.03, -8.8)
        bridge.rotation = self._vec(0.0, t * 0.03, 0.0)

        tv = self.entities["tv-core"]
        tv.energy = round(0.34 + self.script_activity * 0.62 + self.dream_flux * 0.18, 4)
        tv.position = self._vec(0.0, 0.22 + math.sin(t * 1.1) * 0.05, -9.18)
        tv.rotation = self._vec(math.sin(t * 0.5) * 0.03, math.cos(t * 0.4) * 0.08, 0.0)
        tv.state["scan"] = round((tv.state.get("scan", 0.0) + dt * (0.6 + self.script_activity)) % 1.0, 4)

        script_beam = self.entities["script-beam"]
        script_beam.energy = round(0.26 + self.script_activity * 0.82, 4)
        script_beam.position = self._vec(math.sin(t * 0.7) * 0.3, 0.58 + math.sin(t * 1.9) * 0.12 + self.script_activity * 0.14, -13.4)
        script_beam.rotation = self._vec(0.0, t * 0.16, math.sin(t * 0.8) * 0.08)

        gorilla = self.entities["gorilla-node"]
        gorilla.energy = round(0.24 + self.script_activity * 0.52, 4)
        gorilla.position = self._vec(2.2 + math.sin(t * 1.7) * 0.18, 0.18 + math.cos(t * 2.1) * 0.11, -12.95)
        gorilla.rotation = self._vec(0.0, t * 0.18, math.sin(t * 1.5) * 0.12)

        for index, cabinet_id in enumerate(self.ARCADE_CABINETS):
            entity = self.entities[cabinet_id]
            score = self.arcade_scores[cabinet_id]
            entity.state["score"] = score
            entity.energy = round(0.28 + min(0.65, score / 28000.0) + math.sin(t * 2.4 + index) * 0.04, 4)
            entity.position = self._vec(-2.25 + index * 2.25, -0.22 + math.sin(t * (1.0 + index * 0.2)) * 0.05, -17.3 - index * 0.14)
            entity.rotation = self._vec(0.0, math.sin(t * 0.6 + index) * 0.12, 0.0)

        for index in range(6):
            key = f"dream-orb-{index}"
            orb = self.entities[key]
            phase = t * (0.44 + index * 0.03) + float(orb.state.get("phase", 0.0))
            radius = 1.6 + index * 0.22 + self.dream_flux * 0.35
            orb.energy = round(0.18 + self.dream_flux * 0.72, 4)
            orb.position = self._vec(math.cos(phase) * radius, 0.2 + math.sin(phase * 1.3) * (0.65 + index * 0.06), -21.5 + math.sin(phase) * 1.05)
            orb.rotation = self._vec(phase * 0.1, phase * 0.12, phase * 0.08)

        qubit_items = list(self.qubits.items())
        ring_radius = 2.3 + self.quantum_flux * 0.8
        for index, (label, qubit) in enumerate(qubit_items):
            entity = self.entities[f"qubit-{index:02d}"]
            flash = float(entity.state.get("flash", 0.0)) * 0.86
            entity.state["flash"] = round(flash, 4)
            theta = (index / len(qubit_items)) * math.tau + t * 0.08
            height = (qubit.value - 0.5) * 3.2
            entity.energy = round(0.24 + qubit.value * 0.42 + flash * 0.4, 4)
            entity.position = self._vec(math.cos(theta) * ring_radius, height, -25.2 + math.sin(theta) * ring_radius * 0.45)
            entity.rotation = self._vec(t * 0.1 + index * 0.1, t * 0.12 + index * 0.08, 0.0)
            entity.state.update({"label": label, "value": round(qubit.value, 6), "collapsed": qubit.collapsed, "collapse_count": qubit.collapse_count})

        terminal = self.entities["void-terminal"]
        terminal.energy = round(0.35 + self.void_pressure * 0.72, 4)
        terminal.position = self._vec(0.0, -0.16 + math.sin(t * 0.6) * 0.04, -29.6)
        terminal.rotation = self._vec(0.0, math.sin(t * 0.18) * 0.08, 0.0)

        aura = self.entities["aura-core"]
        aura.energy = round(0.28 + self.void_pressure * 0.88 + self.quantum_flux * 0.08, 4)
        aura.position = self._vec(math.sin(t * 0.4) * 0.7, 1.18 + math.cos(t * 0.75) * 0.18, -30.25)
        aura.rotation = self._vec(t * 0.05, t * 0.11, t * 0.03)

        for link in self.links:
            source_energy = self.layers[link.source_layer].meta.get("energy", 0.0)
            target_energy = self.layers[link.target_layer].meta.get("energy", 0.0)
            link.flux = round((source_energy + target_energy + self.quantum_flux * 0.2 + self.dream_flux * 0.15) / 2.0, 4)

        self.camera.focus_layer = int(min(max(self.camera.focus_layer, 0), len(self.layers) - 1))
        self.layers[self.camera.focus_layer].meta["focus"] = True
        self.layers[self.camera.focus_layer].meta["focus_anchor"] = focus_anchor

    def world_snapshot(self) -> dict:
        self.tick()
        return {
            "uptime": self.uptime,
            "layers": [asdict(layer) for layer in self.layers.values()],
            "entities": [asdict(entity) for entity in self.entities.values()],
            "links": [asdict(link) for link in self.links],
            "camera": asdict(self.camera),
            "metrics": {
                "quantum_flux": round(self.quantum_flux, 4),
                "dream_flux": round(self.dream_flux, 4),
                "void_pressure": round(self.void_pressure, 4),
                "script_activity": round(self.script_activity, 4),
                "disturbance": round(self.disturbance, 4),
                "collapsed_qubits": sum(1 for q in self.qubits.values() if q.collapsed),
                "event_count": len(self.event_log),
            },
            "void_messages": list(self.void_messages)[-8:],
            "script_preview": self.last_script_output[-8:],
            "recent_events": list(self.event_log)[-14:],
        }

    def snapshot(self) -> dict:
        self.tick()
        return {
            "uptime": self.uptime,
            "layers": {str(k): asdict(v) for k, v in self.layers.items()},
            "avatar_count": len(self.avatars),
            "qubit_count": len(self.qubits),
            "script_runs": len(self.script_runs),
            "event_log_size": len(self.event_log),
            "world": self.world_snapshot(),
        }

    def shake_avatar(self, avatar_id: str) -> dict:
        avatar = self.avatars.get(avatar_id)
        entity = self.entities.get(avatar_id)
        if not avatar or not entity:
            return {"error": "avatar not found"}
        avatar.shake_count += 1
        avatar.is_shaking = True
        entity.state["impulse"] = min(2.6, float(entity.state.get("impulse", 0.0)) + 1.0)
        entity.energy = min(1.2, entity.energy + 0.28)
        self.script_activity = min(1.5, self.script_activity + 0.07)
        self.disturbance = min(2.0, self.disturbance + 0.22)
        self.layers[1].events += 1
        self._log("avatar.shake", {"avatar_id": avatar_id, "shake_count": avatar.shake_count})
        self.tick()
        return {"avatar_id": avatar_id, "shake_count": avatar.shake_count, "status": "shaking", "world": self.world_snapshot()}

    def super_shake(self) -> dict:
        shaken = [self.shake_avatar(avatar_id) for avatar_id in self.avatars]
        self.layers[1].events += 1
        self._log("avatar.super_shake", {"count": len(shaken)})
        return {"shaken": shaken, "burst": True, "world": self.world_snapshot()}

    def collapse_qubit(self, label: str) -> dict:
        qubit = self.qubits.get(label)
        if not qubit:
            return {"error": "qubit not found"}
        qubit.value = random.random()
        qubit.collapsed = True
        qubit.collapse_count += 1
        self.script_activity = min(1.5, self.script_activity + 0.04)
        self.disturbance = min(2.0, self.disturbance + 0.35)
        self.layers[6].events += 1
        self.layers[5].events += 1
        qubit_index = self.QUBIT_LABELS.index(label)
        self.entities[f"qubit-{qubit_index:02d}"].state["flash"] = 1.0
        self._log("quantum.collapse", {"label": label, "value": round(qubit.value, 6), "collapse_count": qubit.collapse_count})
        self.tick()
        return {"label": label, "value": round(qubit.value, 6), "collapsed": True, "collapse_count": qubit.collapse_count, "world": self.world_snapshot()}

    def collapse_all_qubits(self) -> List[dict]:
        return [self.collapse_qubit(label) for label in self.qubits]

    def play_arcade(self, cabinet_id: str) -> dict:
        if cabinet_id not in self.arcade_scores or cabinet_id not in self.entities:
            return {"error": "cabinet not found"}
        gain = random.randint(900, 5200)
        self.arcade_scores[cabinet_id] += gain
        entity = self.entities[cabinet_id]
        entity.energy = min(1.5, entity.energy + 0.25)
        entity.state["score"] = self.arcade_scores[cabinet_id]
        self.script_activity = min(1.5, self.script_activity + 0.03)
        self.layers[4].events += 1
        self._log("arcade.play", {"cabinet_id": cabinet_id, "score": self.arcade_scores[cabinet_id], "gain": gain})
        self.tick()
        return {"cabinet_id": cabinet_id, "label": self.ARCADE_CABINETS[cabinet_id], "score": self.arcade_scores[cabinet_id], "gain": gain, "world": self.world_snapshot()}

    def focus_layer(self, layer_id: int, reason: str = "manual") -> dict:
        if layer_id not in self.layers:
            return {"error": "layer not found"}
        self.camera.focus_layer = layer_id
        self.layers[layer_id].events += 1
        self._log("camera.focus", {"layer_id": layer_id, "reason": reason})
        self.tick()
        return {"camera": asdict(self.camera), "world": self.world_snapshot()}

    def new_script_run(self) -> ScriptRun:
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        run = ScriptRun(run_id=run_id, started_at=time.time())
        self.script_runs[run_id] = run
        self.script_activity = min(1.5, self.script_activity + 0.45)
        self.layers[3].events += 1
        self._log("script.start", {"run_id": run_id})
        return run

    def complete_script_run(self, run_id: str, output: List[str]):
        run = self.script_runs.get(run_id)
        if not run:
            return
        run.output = output
        run.completed_at = time.time()
        run.status = "complete"
        self.last_script_output = output[-8:]
        self.script_activity = min(1.5, self.script_activity + 0.2)
        self._log("script.complete", {"run_id": run_id, "lines": len(output)})

    def next_void_response(self) -> str:
        response = self.VOID_RESPONSES[self._void_index % len(self.VOID_RESPONSES)]
        self._void_index += 1
        self.void_messages.append(response)
        self.void_pressure = min(1.0, self.void_pressure + 0.12)
        self.layers[7].events += 1
        self._log("void.echo", {"message": response})
        self.tick()
        return response


class WSHub:
    def __init__(self):
        self._clients: Set[Any] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: Any):
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info("WS client connected | total=%s", len(self._clients))

    async def disconnect(self, ws: Any):
        async with self._lock:
            self._clients.discard(ws)
        log.info("WS client disconnected | total=%s", len(self._clients))

    async def broadcast(self, payload: dict):
        message = json.dumps(payload)
        dead: Set[Any] = set()
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                self._clients -= dead

    @property
    def client_count(self) -> int:
        return len(self._clients)

async def script_stream_generator(fsm: SimulationFSM, hub: Optional[WSHub], run_id: str) -> AsyncGenerator[str, None]:
    output: List[str] = []
    for index, line in enumerate(fsm.SCRIPT_LINES):
        fsm.script_activity = min(1.5, fsm.script_activity + 0.12)
        payload = {"run_id": run_id, "line_index": index, "line": line, "total": len(fsm.SCRIPT_LINES)}
        output.append(line)
        if hub:
            await hub.broadcast({"event": "script.line", "payload": payload})
        yield f"data: {json.dumps(payload)}\n\n"
        await asyncio.sleep(0.35)
    fsm.complete_script_run(run_id, output)
    if hub:
        await hub.broadcast({"event": "script.run", "payload": {"run_id": run_id, "output": output, "world": fsm.world_snapshot()}})
    yield f"data: {json.dumps({'run_id': run_id, 'line_index': -1, 'line': 'EOF', 'total': len(fsm.SCRIPT_LINES)})}\n\n"

if HAS_FASTAPI:
    from starlette.middleware.base import BaseHTTPMiddleware

    class RequestIDMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
            request.state.request_id = request_id
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

    class TimingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            started = time.perf_counter()
            response = await call_next(request)
            response.headers["X-Response-Time"] = f"{round((time.perf_counter() - started) * 1000, 2)}ms"
            return response

    class RateLimitMiddleware(BaseHTTPMiddleware):
        def __init__(self, app, rpm: int = 120):
            super().__init__(app)
            self._rpm = rpm
            self._buckets: Dict[str, List[float]] = defaultdict(list)

        async def dispatch(self, request: Request, call_next):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            bucket = [stamp for stamp in self._buckets[client_ip] if now - stamp < 60]
            if len(bucket) >= self._rpm:
                return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)
            bucket.append(now)
            self._buckets[client_ip] = bucket
            return await call_next(request)

def build_app():
    fsm = SimulationFSM()
    hub = WSHub()
    ticker: Optional[asyncio.Task] = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal ticker
        ticker = asyncio.create_task(_background_tick(fsm, hub))
        try:
            yield
        finally:
            if ticker:
                ticker.cancel()
                try:
                    await ticker
                except asyncio.CancelledError:
                    pass
            log.info("Simulation backend shut down cleanly")

    app = FastAPI(
        title="NextAura Dimensional Simulation API",
        version="8.0.0",
        description="Authoritative world state for the sim7 dimensional renderer.",
        lifespan=lifespan,
    )

    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware, rpm=180)

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def root():
        index_path = os.path.join(static_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return HTMLResponse("<h1>Simulation backend online.</h1>")

    @app.get("/api/health")
    async def health():
        fsm.tick()
        return {
            "status": "ok",
            "version": "8.0.0",
            "uptime": fsm.uptime,
            "layers": len(fsm.layers),
            "ws_clients": hub.client_count,
            "avatars": len(fsm.avatars),
            "qubits": len(fsm.qubits),
            "script_runs": len(fsm.script_runs),
            "timestamp": time.time(),
            "focus_layer": fsm.camera.focus_layer,
        }

    @app.get("/api/snapshot")
    async def snapshot():
        return fsm.snapshot()

    @app.get("/api/world")
    async def world():
        return fsm.world_snapshot()

    @app.post("/api/world/reset")
    async def reset_world():
        fsm.reset()
        payload = fsm.world_snapshot()
        await hub.broadcast({"event": "world.reset", "payload": payload})
        return payload

    @app.get("/api/layers")
    async def get_layers():
        fsm.tick()
        return {str(k): asdict(v) for k, v in fsm.layers.items()}

    @app.get("/api/layers/{layer_id}")
    async def get_layer(layer_id: int):
        fsm.tick()
        layer = fsm.layers.get(layer_id)
        if not layer:
            return JSONResponse({"error": "layer not found"}, status_code=404)
        return asdict(layer)

    @app.get("/api/avatars")
    async def get_avatars():
        fsm.tick()
        return {str(k): asdict(v) for k, v in fsm.avatars.items()}

    @app.post("/api/avatars/{avatar_id}/shake")
    async def shake_avatar(avatar_id: str):
        result = fsm.shake_avatar(avatar_id)
        await hub.broadcast({"event": "avatar.shake", "payload": result})
        return result

    @app.post("/api/avatars/super-shake")
    async def super_shake():
        result = fsm.super_shake()
        await hub.broadcast({"event": "avatar.super_shake", "payload": result})
        return result

    @app.get("/api/run-script")
    async def run_script():
        run = fsm.new_script_run()
        output = list(fsm.SCRIPT_LINES)
        fsm.complete_script_run(run.run_id, output)
        payload = {
            "run_id": run.run_id,
            "status": "complete",
            "output": output,
            "duration_ms": round((run.completed_at - run.started_at) * 1000, 2) if run.completed_at else 0.0,
            "world": fsm.world_snapshot(),
        }
        await hub.broadcast({"event": "script.run", "payload": payload})
        return payload

    @app.get("/api/script/stream")
    async def stream_script():
        run = fsm.new_script_run()
        return StreamingResponse(
            script_stream_generator(fsm, hub, run.run_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/script/runs")
    async def script_runs():
        return {str(k): asdict(v) for k, v in fsm.script_runs.items()}

    @app.get("/api/quantum/qubits")
    async def qubits():
        fsm.tick()
        return {str(k): asdict(v) for k, v in fsm.qubits.items()}

    @app.post("/api/quantum/collapse/{label}")
    async def collapse_qubit(label: str):
        result = fsm.collapse_qubit(label)
        await hub.broadcast({"event": "quantum.collapse", "payload": result})
        return result

    @app.post("/api/quantum/collapse-all")
    async def collapse_all():
        collapsed = fsm.collapse_all_qubits()
        payload = {"collapsed": collapsed, "count": len(collapsed), "world": fsm.world_snapshot()}
        await hub.broadcast({"event": "quantum.collapse_all", "payload": payload})
        return payload

    @app.get("/api/events")
    async def events(limit: int = 80):
        return {"events": list(fsm.event_log)[-limit:], "total": len(fsm.event_log)}

    @app.get("/api/void/echo")
    async def void_echo():
        message = fsm.next_void_response()
        payload = {"void": message, "depth": 7, "ts": time.time(), "world": fsm.world_snapshot()}
        await hub.broadcast({"event": "void.echo", "payload": payload})
        return payload

    @app.post("/api/camera/focus/{layer_id}")
    async def focus_layer(layer_id: int):
        result = fsm.focus_layer(layer_id)
        await hub.broadcast({"event": "camera.focus", "payload": result})
        return result

    @app.post("/api/arcade/{cabinet_id}/play")
    async def play_arcade(cabinet_id: str):
        result = fsm.play_arcade(cabinet_id)
        await hub.broadcast({"event": "arcade.play", "payload": result})
        return result

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await hub.connect(ws)
        try:
            await ws.send_text(json.dumps({"event": "world.init", "payload": fsm.world_snapshot()}))
            await ws.send_text(json.dumps({"event": "init", "payload": fsm.snapshot()}))
            while True:
                try:
                    raw = await asyncio.wait_for(ws.receive_text(), timeout=20)
                    message = json.loads(raw)
                    event = message.get("event")
                    if event == "ping":
                        await ws.send_text(json.dumps({"event": "pong", "ts": time.time()}))
                    elif event == "shake":
                        avatar_id = message.get("avatar_id", "wm-01")
                        await hub.broadcast({"event": "avatar.shake", "payload": fsm.shake_avatar(avatar_id)})
                    elif event == "collapse":
                        label = message.get("label", "|0>")
                        await hub.broadcast({"event": "quantum.collapse", "payload": fsm.collapse_qubit(label)})
                    elif event == "focus":
                        layer_id = int(message.get("layer_id", fsm.camera.focus_layer))
                        await hub.broadcast({"event": "camera.focus", "payload": fsm.focus_layer(layer_id, reason="ws")})
                    elif event == "play":
                        cabinet_id = message.get("cabinet_id", "wm-bounce")
                        await hub.broadcast({"event": "arcade.play", "payload": fsm.play_arcade(cabinet_id)})
                    elif event == "void.echo":
                        payload = {"void": fsm.next_void_response(), "depth": 7, "ts": time.time(), "world": fsm.world_snapshot()}
                        await hub.broadcast({"event": "void.echo", "payload": payload})
                    elif event == "reset":
                        fsm.reset()
                        await hub.broadcast({"event": "world.reset", "payload": fsm.world_snapshot()})
                except asyncio.TimeoutError:
                    await ws.send_text(json.dumps({"event": "heartbeat", "ts": time.time()}))
        except WebSocketDisconnect:
            pass
        finally:
            await hub.disconnect(ws)

    return app, fsm, hub

async def _background_tick(fsm: SimulationFSM, hub: WSHub):
    while True:
        await asyncio.sleep(0.35)
        fsm.tick()
        if hub.client_count:
            await hub.broadcast({"event": "world.tick", "payload": fsm.world_snapshot()})


def _run_stdlib_fallback():
    import json as json_lib
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    fsm = SimulationFSM()

    class FallbackHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=static_dir, **kwargs)

        def do_GET(self):
            if self.path in ("", "/"):
                self.path = "/index.html"
            elif self.path == "/api/health":
                fsm.tick()
                self._json({"status": "ok", "mode": "stdlib-fallback", "uptime": fsm.uptime})
                return
            elif self.path == "/api/world":
                self._json(fsm.world_snapshot())
                return
            elif self.path == "/api/run-script":
                self._json({"status": "complete", "output": list(fsm.SCRIPT_LINES)})
                return
            super().do_GET()

        def _json(self, payload: dict):
            body = json_lib.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            log.info(fmt, *args)

    port = int(os.getenv("PORT", "8787"))
    server = HTTPServer(("0.0.0.0", port), FallbackHandler)
    log.info("[stdlib fallback] http://localhost:%s", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutdown requested")
    finally:
        server.server_close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8787"))
    if HAS_FASTAPI:
        app, _, _ = build_app()
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", access_log=True, loop="asyncio")
    else:
        log.warning("FastAPI not available. Running stdlib fallback server.")
        _run_stdlib_fallback()
