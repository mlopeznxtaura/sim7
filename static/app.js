
import { DimensionalCollapseRenderer } from '/static/renderer.js';

const DIMENSION_BANDS = [1536, 1024, 768, 512, 384, 256, 128, 64];

const state = {
  world: null,
  ws: null,
  wsConnected: false,
  reconnectTimer: null,
  health: null,
  scriptLines: ['Signal feed idle.'],
  voidLines: ['Void membrane asleep.'],
};

const els = {
  canvas: document.getElementById('world-canvas'),
  loading: document.getElementById('loading-state'),
  wsStatus: document.getElementById('ws-status'),
  healthStatus: document.getElementById('health-status'),
  focusStatus: document.getElementById('focus-status'),
  focusChips: document.getElementById('focus-chips'),
  layerStack: document.getElementById('layer-stack'),
  scriptOutput: document.getElementById('script-output'),
  voidOutput: document.getElementById('void-output'),
  eventLog: document.getElementById('event-log'),
  metricUptime: document.getElementById('metric-uptime'),
  metricQuantum: document.getElementById('metric-quantum'),
  metricDream: document.getElementById('metric-dream'),
  metricVoid: document.getElementById('metric-void'),
  metricEvents: document.getElementById('metric-events'),
  metricCollapsed: document.getElementById('metric-collapsed'),
};

const renderer = new DimensionalCollapseRenderer(els.canvas);

function byId(a, b) { return Number(a.id || 0) - Number(b.id || 0); }
function safeNumber(value, fallback = 0) { return Number.isFinite(Number(value)) ? Number(value) : fallback; }
function formatName(name = '') { return name.replace(/-/g, ' '); }
function dimensionForDepth(depth = 0) { return DIMENSION_BANDS[Math.min(depth, DIMENSION_BANDS.length - 1)] || 64; }
function formatDimension(layer) { return `${safeNumber(layer?.meta?.embedding_dimension, 64)}d`; }
function setStatus(element, value, tone) { element.textContent = value; if (tone) element.style.color = tone; }

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function decorateLayer(rawLayer, index, total) {
  const depth = safeNumber(rawLayer.meta?.depth, rawLayer.id ?? index);
  const dim = dimensionForDepth(depth);
  const energy = safeNumber(rawLayer.meta?.energy, 0.25 + (1 - depth / Math.max(1, total - 1)) * 0.25);
  const resonance = safeNumber(rawLayer.meta?.resonance, 0.24 + depth * 0.05);
  const distortion = safeNumber(rawLayer.meta?.distortion, rawLayer.status === 'dreaming' ? 0.62 : 0.18 + depth * 0.03);
  return {
    ...rawLayer,
    id: safeNumber(rawLayer.id, index),
    meta: {
      ...(rawLayer.meta || {}),
      depth,
      energy,
      resonance,
      distortion,
      embedding_dimension: dim,
      band_ratio: dim / DIMENSION_BANDS[0],
      focus: false,
    },
  };
}

function synthesizeWorld(source = {}) {
  const rawLayers = Array.isArray(source.layers) ? source.layers : Object.values(source.layers || {}).sort(byId);
  const layers = rawLayers.length
    ? rawLayers.map((layer, index) => decorateLayer(layer, index, rawLayers.length))
    : Array.from({ length: 8 }, (_, id) => decorateLayer({
        id,
        name: `layer-${id}`,
        status: id === 5 ? 'dreaming' : id === 7 ? 'void' : 'online',
        uptime: safeNumber(source.uptime, 0),
        events: 0,
        meta: { depth: id, energy: 0.22 + (7 - id) * 0.04, resonance: 0.24 + id * 0.05, distortion: id === 5 ? 0.58 : 0.16 + id * 0.03 },
      }, id, 8));

  const focusLayer = safeNumber(source.camera?.focus_layer, layers.find((layer) => layer.meta.focus)?.id ?? 2);
  layers.forEach((layer) => { layer.meta.focus = layer.id === focusLayer; });

  const recentEvents = Array.isArray(source.recent_events) ? source.recent_events : Array.isArray(source.events) ? source.events : [];
  return {
    uptime: safeNumber(source.uptime, 0),
    camera: { ...(source.camera || {}), focus_layer: focusLayer },
    layers,
    entities: Array.isArray(source.entities) ? source.entities : [],
    links: Array.isArray(source.links) ? source.links : layers.slice(0, -1).map((layer, index) => ({ source_layer: layer.id, target_layer: layers[index + 1].id, flux: 0.3 })),
    metrics: {
      quantum_flux: safeNumber(source.metrics?.quantum_flux, 0.38),
      dream_flux: safeNumber(source.metrics?.dream_flux, 0.42),
      void_pressure: safeNumber(source.metrics?.void_pressure, 0.28),
      event_count: safeNumber(source.metrics?.event_count, recentEvents.length),
      collapsed_qubits: safeNumber(source.metrics?.collapsed_qubits, 0),
    },
    script_preview: source.script_preview || [],
    void_messages: source.void_messages || [],
    recent_events: recentEvents,
  };
}

function extractWorld(payload) {
  if (!payload) return null;
  if (payload.world) return synthesizeWorld(payload.world);
  if (payload.layers || payload.metrics || payload.entities) return synthesizeWorld(payload);
  return null;
}

function currentFocusLayer() {
  if (!state.world) return null;
  return state.world.layers.find((layer) => layer.id === state.world.camera.focus_layer) || state.world.layers[0] || null;
}

function applyWorld(world) {
  const nextWorld = synthesizeWorld(world);
  state.world = nextWorld;
  renderer.setWorld(nextWorld);
  if (nextWorld.script_preview.length) state.scriptLines = [...nextWorld.script_preview].reverse();
  if (nextWorld.void_messages.length) state.voidLines = [...nextWorld.void_messages].reverse();
  els.loading.classList.add('ready');
  renderUI();
}

function addLine(target, text, fallback) {
  target.unshift(text || fallback);
  while (target.length > 10) target.pop();
}

function renderFocusChips() {
  if (!state.world) return;
  els.focusChips.innerHTML = '';
  state.world.layers.forEach((layer) => {
    const chip = document.createElement('button');
    chip.className = `focus-chip${layer.meta.focus ? ' active' : ''}`;
    chip.innerHTML = `L${layer.id}<small>${formatDimension(layer)}</small>`;
    chip.addEventListener('click', () => focusLayer(layer.id));
    els.focusChips.appendChild(chip);
  });
}

function renderLayerStack() {
  if (!state.world) return;
  els.layerStack.innerHTML = '';
  state.world.layers.forEach((layer) => {
    const card = document.createElement('article');
    card.className = 'layer-card';
    const fill = `${Math.max(8, safeNumber(layer.meta.band_ratio, 0.1) * 100)}%`;
    card.innerHTML = `
      <div class="layer-topline">
        <span class="layer-name">L${layer.id} ${formatName(layer.name)}</span>
        <span class="layer-meta">${layer.status}</span>
      </div>
      <div class="layer-bandline">
        <div class="layer-band"><span class="layer-band-fill" style="width:${fill}"></span></div>
        <span class="layer-band-label">${formatDimension(layer)}</span>
      </div>
      <div class="layer-detail">
        <span>E ${safeNumber(layer.meta.energy).toFixed(2)}</span>
        <span>R ${safeNumber(layer.meta.resonance).toFixed(2)}</span>
        <span>D ${safeNumber(layer.meta.distortion).toFixed(2)}</span>
      </div>
    `;
    els.layerStack.appendChild(card);
  });
}

function renderMetrics() {
  if (!state.world) return;
  const metrics = state.world.metrics;
  const focus = currentFocusLayer();
  els.metricUptime.textContent = `${safeNumber(state.world.uptime).toFixed(1)}s`;
  els.metricQuantum.textContent = safeNumber(metrics.quantum_flux).toFixed(3);
  els.metricDream.textContent = safeNumber(metrics.dream_flux).toFixed(3);
  els.metricVoid.textContent = safeNumber(metrics.void_pressure).toFixed(3);
  els.metricEvents.textContent = String(safeNumber(metrics.event_count));
  els.metricCollapsed.textContent = String(safeNumber(metrics.collapsed_qubits));
  els.focusStatus.textContent = focus ? `L${focus.id} / ${formatDimension(focus)}` : 'offline';
}

function renderEvents() {
  if (!state.world) return;
  els.eventLog.innerHTML = '';
  const events = [...state.world.recent_events].reverse().slice(0, 12);
  if (!events.length) {
    els.eventLog.innerHTML = '<div class="event-item"><span class="event-name">No wreckage yet</span><span class="event-detail">Trigger the dock controls to stress the dimensional stack.</span></div>';
    return;
  }
  events.forEach((event) => {
    const detail = Object.entries(event.data || {}).slice(0, 3).map(([key, value]) => `${key}=${value}`).join(' · ');
    const item = document.createElement('div');
    item.className = 'event-item';
    item.innerHTML = `
      <span class="event-name">${event.event}</span>
      <span class="event-time">${event.ts ? new Date(event.ts * 1000).toLocaleTimeString() : 'recent'}</span>
      <span class="event-detail">${detail || 'state change'}</span>
    `;
    els.eventLog.appendChild(item);
  });
}

function renderConsoles() {
  els.scriptOutput.textContent = state.scriptLines.join('\n');
  els.voidOutput.textContent = state.voidLines.join('\n');
}

function renderUI() {
  renderFocusChips();
  renderLayerStack();
  renderMetrics();
  renderEvents();
  renderConsoles();
}

function handleSocketEvent(message) {
  const { event, payload } = message;
  const world = extractWorld(payload);
  if (world) applyWorld(world);
  if (event === 'script.line') { addLine(state.scriptLines, payload.line, 'stream'); renderConsoles(); }
  if (event === 'script.run' && payload?.output) { state.scriptLines = [...payload.output].reverse(); renderConsoles(); }
  if (event === 'void.echo') { addLine(state.voidLines, payload?.void || payload?.message, 'void'); renderConsoles(); }
}

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  state.ws = new WebSocket(`${protocol}//${location.host}/ws`);
  state.ws.addEventListener('open', () => { state.wsConnected = true; setStatus(els.wsStatus, 'online', '#7df1df'); });
  state.ws.addEventListener('close', () => {
    state.wsConnected = false;
    setStatus(els.wsStatus, 'offline', '#ff8a6c');
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = setTimeout(connectWS, 2500);
  });
  state.ws.addEventListener('message', (entry) => {
    try { handleSocketEvent(JSON.parse(entry.data)); } catch (_error) { }
  });
}

async function refreshHealth() {
  try {
    const health = await fetchJSON('/api/health');
    state.health = health;
    setStatus(els.healthStatus, `v${health.version} / ${health.ws_clients} ws`, '#ffd37d');
  } catch (_error) {
    setStatus(els.healthStatus, 'degraded', '#ff756a');
  }
}

async function loadBestWorld() {
  try {
    applyWorld(await fetchJSON('/api/world'));
    return;
  } catch (_error) { }
  try {
    const snapshot = await fetchJSON('/api/snapshot');
    applyWorld(extractWorld(snapshot) || synthesizeWorld(snapshot));
    return;
  } catch (_error) { }
  if (state.health) applyWorld(synthesizeWorld({ uptime: state.health.uptime, camera: { focus_layer: state.health.focus_layer } }));
}

function requestOrFallback(socketPayload, fallbackFn) {
  if (state.wsConnected && state.ws?.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(socketPayload));
    return Promise.resolve();
  }
  return fallbackFn();
}

function shakeAvatar(avatarId) {
  return requestOrFallback({ event: 'shake', avatar_id: avatarId }, () => fetchJSON(`/api/avatars/${avatarId}/shake`, { method: 'POST' }).then((payload) => applyWorld(extractWorld(payload) || state.world || {})));
}

function superShake() {
  return fetchJSON('/api/avatars/super-shake', { method: 'POST' }).then((payload) => applyWorld(extractWorld(payload) || state.world || {}));
}

function runScript() {
  state.scriptLines = ['Streaming script beam...'];
  renderConsoles();
  const source = new EventSource('/api/script/stream');
  const lines = [];
  source.onmessage = (entry) => {
    const data = JSON.parse(entry.data);
    if (data.line_index === -1) { source.close(); return; }
    lines.unshift(data.line);
    state.scriptLines = lines.slice(0, 10);
    renderConsoles();
  };
  source.onerror = () => source.close();
}

function collapseAll() {
  return fetchJSON('/api/quantum/collapse-all', { method: 'POST' }).then((payload) => applyWorld(extractWorld(payload) || state.world || {}));
}

function wakeVoid() {
  return fetchJSON('/api/void/echo').then((payload) => {
    addLine(state.voidLines, payload.void, 'void');
    renderConsoles();
    applyWorld(extractWorld(payload) || state.world || {});
  });
}

function focusLayer(layerId) {
  if (state.world) {
    const local = { ...state.world, camera: { ...state.world.camera, focus_layer: layerId }, layers: state.world.layers.map((layer) => ({ ...layer, meta: { ...layer.meta, focus: layer.id === layerId } })) };
    applyWorld(local);
  }
  return requestOrFallback({ event: 'focus', layer_id: layerId }, () => fetchJSON(`/api/camera/focus/${layerId}`, { method: 'POST' }).then((payload) => applyWorld(extractWorld(payload) || state.world || {})).catch(() => Promise.resolve()));
}

function playCabinet(cabinetId) {
  return requestOrFallback({ event: 'play', cabinet_id: cabinetId }, () => fetchJSON(`/api/arcade/${cabinetId}/play`, { method: 'POST' }).then((payload) => applyWorld(extractWorld(payload) || state.world || {})).catch(() => { addLine(state.scriptLines, `arcade.local ${cabinetId}`, 'arcade'); renderConsoles(); }));
}

function resetWorld() {
  return fetchJSON('/api/world/reset', { method: 'POST' }).then((payload) => applyWorld(extractWorld(payload) || payload)).catch(loadBestWorld);
}

function bindButtons() {
  document.querySelectorAll('[data-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const { action, avatar, cabinet } = button.dataset;
      if (action === 'shake') shakeAvatar(avatar);
      if (action === 'super-shake') superShake();
      if (action === 'run-script') runScript();
      if (action === 'collapse-all') collapseAll();
      if (action === 'void') wakeVoid();
      if (action === 'play') playCabinet(cabinet);
      if (action === 'reset-world') resetWorld();
    });
  });
}

async function bootstrap() {
  bindButtons();
  renderer.start();
  await refreshHealth();
  await loadBestWorld();
  connectWS();
  setInterval(refreshHealth, 8000);
  setInterval(() => { loadBestWorld().catch(() => {}); }, 10000);
}

bootstrap().catch((error) => {
  console.error(error);
  setStatus(els.healthStatus, 'boot failed', '#ff756a');
  applyWorld(synthesizeWorld({ uptime: 0, camera: { focus_layer: 2 } }));
});
