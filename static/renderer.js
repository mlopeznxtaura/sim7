
import * as THREE from '/static/vendor/three.module.js';

const DIMENSION_BANDS = [1536, 1024, 768, 512, 384, 256, 128, 64];
const LAYER_PALETTE = [0x8fd8ff, 0x74ffd1, 0xffcb79, 0xff8a6c, 0x90d8ff, 0xe3a7ff, 0xacb6ff, 0xf3f0e4];
const STATUS_TONES = { online: 0x8fd8ff, dreaming: 0xffab78, void: 0xcab8ff, boot: 0xffd67f };

function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
function normalized(value, min, max) { return max === min ? 0 : clamp((value - min) / (max - min), 0, 1); }
function safeNumber(value, fallback = 0) { return Number.isFinite(Number(value)) ? Number(value) : fallback; }
function dimensionForLayer(layer, index) { return safeNumber(layer?.meta?.embedding_dimension, DIMENSION_BANDS[Math.min(index, DIMENSION_BANDS.length - 1)]); }
function layerColor(layer, index) {
  const base = new THREE.Color(STATUS_TONES[layer?.status] ?? LAYER_PALETTE[index % LAYER_PALETTE.length]);
  const accent = new THREE.Color(LAYER_PALETTE[index % LAYER_PALETTE.length]);
  return base.lerp(accent, 0.45);
}
function createCanvasTexture(width, height, draw) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  draw(ctx, width, height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}
function createGlowTexture() {
  return createCanvasTexture(256, 256, (ctx, width, height) => {
    const gradient = ctx.createRadialGradient(width * 0.5, height * 0.5, 0, width * 0.5, height * 0.5, width * 0.5);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(0.18, 'rgba(255,255,255,0.95)');
    gradient.addColorStop(0.38, 'rgba(160,212,255,0.55)');
    gradient.addColorStop(0.68, 'rgba(58,102,170,0.12)');
    gradient.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
  });
}
function createSeamTexture() {
  return createCanvasTexture(32, 512, (ctx, width, height) => {
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, 'rgba(255,187,108,0)');
    gradient.addColorStop(0.32, 'rgba(255,187,108,0.26)');
    gradient.addColorStop(0.52, 'rgba(255,250,242,0.95)');
    gradient.addColorStop(0.68, 'rgba(116, 226, 255, 0.24)');
    gradient.addColorStop(1, 'rgba(116, 226, 255, 0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
  });
}
function createSkyTexture() {
  return createCanvasTexture(64, 1024, (ctx, width, height) => {
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, '#02040a');
    gradient.addColorStop(0.22, '#080d17');
    gradient.addColorStop(0.46, '#111b30');
    gradient.addColorStop(0.5, '#402125');
    gradient.addColorStop(0.55, '#0f3043');
    gradient.addColorStop(0.74, '#082334');
    gradient.addColorStop(1, '#030c14');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
  });
}
function createMaterial(color) {
  const tone = new THREE.Color(color);
  return new THREE.MeshStandardMaterial({ color: tone.clone().lerp(new THREE.Color(0x09101a), 0.35), emissive: tone, emissiveIntensity: 0.85, roughness: 0.28, metalness: 0.24 });
}
function disposeObject(object) {
  object.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (!child.material) return;
    if (Array.isArray(child.material)) child.material.forEach((material) => material.dispose());
    else child.material.dispose();
  });
}

export class DimensionalCollapseRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x06101a, 0.025);
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.18;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8));
    this.camera = new THREE.PerspectiveCamera(46, window.innerWidth / window.innerHeight, 0.1, 240);
    this.camera.position.set(0, 2.8, 15);
    this.clock = new THREE.Clock();
    this.world = null;
    this.layerViews = new Map();
    this.entityViews = new Map();
    this.linkViews = new Map();
    this.frameHandle = false;
    this.pointer = new THREE.Vector2();
    this.pointerDrift = new THREE.Vector2();
    this.dragState = { active: false, x: 0, y: 0 };
    this.cameraState = { yaw: -0.2, targetYaw: -0.2, pitch: 0.32, targetPitch: 0.32, distance: 16, targetDistance: 16 };
    this.focusCurrent = new THREE.Vector3(-1.8, 1.5, -10);
    this.focusTarget = this.focusCurrent.clone();
    this.motion = { time: 0 };
    this.glowTexture = createGlowTexture();
    this.seamTexture = createSeamTexture();
    this.skyTexture = createSkyTexture();
    this.worldGroup = new THREE.Group();
    this.linkGroup = new THREE.Group();
    this.architectureGroup = new THREE.Group();
    this.freeEntityGroup = new THREE.Group();
    this.scene.add(this.worldGroup);
    this.worldGroup.add(this.linkGroup, this.architectureGroup, this.freeEntityGroup);
    this.createEnvironment();
    this.bindEvents();
    this.resize();
  }

  bindEvents() {
    this.resize = this.resize.bind(this);
    window.addEventListener('resize', this.resize);
    this.canvas.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      this.dragState.active = true;
      this.dragState.x = event.clientX;
      this.dragState.y = event.clientY;
      this.canvas.setPointerCapture?.(event.pointerId);
    });
    window.addEventListener('pointermove', (event) => {
      const x = (event.clientX / window.innerWidth) * 2 - 1;
      const y = (event.clientY / window.innerHeight) * 2 - 1;
      this.pointer.set(x, y);
      if (!this.dragState.active) return;
      const deltaX = event.clientX - this.dragState.x;
      const deltaY = event.clientY - this.dragState.y;
      this.dragState.x = event.clientX;
      this.dragState.y = event.clientY;
      this.cameraState.targetYaw -= deltaX * 0.0048;
      this.cameraState.targetPitch = clamp(this.cameraState.targetPitch - deltaY * 0.0038, -0.1, 0.88);
    });
    window.addEventListener('pointerup', () => { this.dragState.active = false; });
    this.canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      this.cameraState.targetDistance = clamp(this.cameraState.targetDistance + event.deltaY * 0.012, 8, 28);
    }, { passive: false });
  }

  createEnvironment() {
    this.scene.add(new THREE.AmbientLight(0x8ca6c8, 0.7));
    const keyLight = new THREE.DirectionalLight(0xb6dbff, 1.45);
    keyLight.position.set(-12, 12, 12);
    this.scene.add(keyLight);
    const seamLight = new THREE.PointLight(0xffc17f, 2.4, 80, 2);
    seamLight.position.set(0, -0.3, -16);
    this.scene.add(seamLight);
    this.blackHoleLight = new THREE.PointLight(0x6b8fff, 3.6, 42, 2);
    this.blackHoleLight.position.set(9.5, 4.8, -27);
    this.scene.add(this.blackHoleLight);
    this.dwarfStarLight = new THREE.PointLight(0xf3fbff, 3.2, 44, 2);
    this.dwarfStarLight.position.set(-11.2, 8.4, -18);
    this.scene.add(this.dwarfStarLight);
    this.skyDome = new THREE.Mesh(new THREE.SphereGeometry(140, 48, 32), new THREE.MeshBasicMaterial({ map: this.skyTexture, side: THREE.BackSide, depthWrite: false }));
    this.scene.add(this.skyDome);
    this.createStarField();
    this.createBlackHole();
    this.createDwarfStar();
    this.createOcean();
    this.createSeam();
    this.createDebris();
  }

  createStarField() {
    const count = 1800;
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      const radius = 55 + Math.random() * 60;
      const angle = Math.random() * Math.PI * 2;
      const spread = Math.random() * 0.9;
      positions[index * 3] = Math.cos(angle) * radius;
      positions[index * 3 + 1] = Math.abs(Math.sin(angle * 1.8)) * 26 + spread * 26 + 2;
      positions[index * 3 + 2] = -10 - Math.random() * 110;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    this.starField = new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xdcecff, size: 0.24, map: this.glowTexture, transparent: true, opacity: 0.95, sizeAttenuation: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.scene.add(this.starField);
  }

  createBlackHole() {
    this.blackHoleGroup = new THREE.Group();
    this.blackHoleGroup.position.set(9.5, 4.8, -27);
    this.blackHoleGroup.add(new THREE.Mesh(new THREE.SphereGeometry(2.2, 40, 40), new THREE.MeshBasicMaterial({ color: 0x030305 })));
    this.blackHoleHalo = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glowTexture, color: 0x5c7eff, transparent: true, opacity: 0.3, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.blackHoleHalo.scale.set(18, 18, 18);
    this.blackHoleGroup.add(this.blackHoleHalo);
    this.accretionRings = [];
    [4.4, 5.3, 6.4].forEach((radius, index) => {
      const torus = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.18 + index * 0.04, 18, 96), new THREE.MeshStandardMaterial({ color: 0xffb56d, emissive: 0xff9c5d, emissiveIntensity: 1.3 - index * 0.2, roughness: 0.28, metalness: 0.18, transparent: true, opacity: 0.42 - index * 0.08 }));
      torus.rotation.x = 1.05 + index * 0.1;
      torus.rotation.y = index * 0.18;
      this.blackHoleGroup.add(torus);
      this.accretionRings.push(torus);
    });
    this.blackHoleLens = new THREE.Mesh(new THREE.PlaneGeometry(18, 18), new THREE.MeshBasicMaterial({ map: this.glowTexture, color: 0xf6a54f, transparent: true, opacity: 0.16, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.blackHoleLens.rotation.x = -0.35;
    this.blackHoleGroup.add(this.blackHoleLens);
    this.blackHoleParticles = [];
    for (let index = 0; index < 36; index += 1) {
      const spark = new THREE.Mesh(new THREE.SphereGeometry(0.05 + Math.random() * 0.06, 8, 8), new THREE.MeshBasicMaterial({ color: 0xffe7ae }));
      spark.userData = { radius: 4.2 + Math.random() * 2.5, height: (Math.random() - 0.5) * 0.8, angle: Math.random() * Math.PI * 2, speed: 0.3 + Math.random() * 0.7 };
      this.blackHoleParticles.push(spark);
      this.blackHoleGroup.add(spark);
    }
    this.scene.add(this.blackHoleGroup);
  }
  createDwarfStar() {
    this.dwarfStarGroup = new THREE.Group();
    this.dwarfStarGroup.position.set(-11.2, 8.4, -18);
    const coreMaterial = new THREE.MeshStandardMaterial({ color: 0xf4fbff, emissive: 0xdff4ff, emissiveIntensity: 2.4, roughness: 0.18, metalness: 0.08 });
    this.dwarfStarCore = new THREE.Mesh(new THREE.SphereGeometry(1.05, 28, 28), coreMaterial);
    this.dwarfStarGroup.add(this.dwarfStarCore);
    this.dwarfStarAura = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glowTexture, color: 0xb5ecff, transparent: true, opacity: 0.42, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.dwarfStarAura.scale.set(8.5, 8.5, 8.5);
    this.dwarfStarGroup.add(this.dwarfStarAura);
    this.atomicRings = [];
    [2.2, 3.2, 4.4].forEach((radius, index) => {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.028, 10, 96), new THREE.MeshBasicMaterial({ color: 0x95d8ff, transparent: true, opacity: 0.45 - index * 0.08 }));
      ring.rotation.x = 0.7 + index * 0.55;
      ring.rotation.y = index * 0.9;
      this.atomicRings.push(ring);
      this.dwarfStarGroup.add(ring);
    });
    this.electrons = [];
    for (let index = 0; index < 4; index += 1) {
      const electron = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 10), new THREE.MeshBasicMaterial({ color: 0xeff9ff }));
      electron.userData = { radius: 2.2 + (index % 3) * 1.05, speed: 0.6 + index * 0.18, phase: index * 1.2, tilt: index * 0.7 };
      this.electrons.push(electron);
      this.dwarfStarGroup.add(electron);
    }
    this.scene.add(this.dwarfStarGroup);
  }

  createOcean() {
    const geometry = new THREE.PlaneGeometry(200, 170, 140, 140);
    geometry.rotateX(-Math.PI / 2);
    this.ocean = new THREE.Mesh(geometry, new THREE.MeshPhysicalMaterial({ color: 0x0b3142, emissive: 0x071a25, emissiveIntensity: 0.6, roughness: 0.16, metalness: 0.38, clearcoat: 0.42, transparent: true, opacity: 0.96, side: THREE.DoubleSide }));
    this.ocean.position.set(0, -5.6, -28);
    this.scene.add(this.ocean);
    this.oceanBase = Float32Array.from(geometry.attributes.position.array);
    this.oceanTrench = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 22, 55, 48, 1, true), new THREE.MeshBasicMaterial({ color: 0x04090d, transparent: true, opacity: 0.34, side: THREE.BackSide }));
    this.oceanTrench.position.set(0, -21, -32);
    this.scene.add(this.oceanTrench);
  }

  createSeam() {
    this.seamPlane = new THREE.Mesh(new THREE.PlaneGeometry(64, 18), new THREE.MeshBasicMaterial({ map: this.seamTexture, transparent: true, opacity: 0.36, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.seamPlane.position.set(0, -0.6, -18);
    this.scene.add(this.seamPlane);
  }

  createDebris() {
    this.debris = [];
    const baseMaterial = new THREE.MeshStandardMaterial({ color: 0x88b7d9, emissive: 0x102237, emissiveIntensity: 0.25, roughness: 0.44, metalness: 0.18, transparent: true, opacity: 0.28 });
    for (let index = 0; index < 42; index += 1) {
      const geometry = new THREE.BoxGeometry(0.12 + Math.random() * 0.55, 0.02 + Math.random() * 0.08, 0.2 + Math.random() * 0.6);
      const mesh = new THREE.Mesh(geometry, baseMaterial.clone());
      mesh.userData = { radius: 4 + Math.random() * 10, depth: -8 - Math.random() * 28, height: -0.8 + Math.random() * 4.2, speed: 0.18 + Math.random() * 0.36, offset: Math.random() * Math.PI * 2, wobble: 0.4 + Math.random() * 1.6 };
      this.debris.push(mesh);
      this.scene.add(mesh);
    }
  }

  createLayerView(layer, index) {
    const anchorGroup = new THREE.Group();
    const structureGroup = new THREE.Group();
    const entityRoot = new THREE.Group();
    anchorGroup.add(structureGroup, entityRoot);
    const shell = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshPhysicalMaterial({ color: 0x0c1521, roughness: 0.18, metalness: 0.24, transmission: 0.14, transparent: true, opacity: 0.08, side: THREE.DoubleSide }));
    structureGroup.add(shell);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1)), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.55 }));
    structureGroup.add(edges);
    const portal = new THREE.Mesh(new THREE.TorusGeometry(0.92, 0.035, 16, 96), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.24 }));
    portal.rotation.x = 1.12;
    structureGroup.add(portal);
    const innerShells = [];
    for (let innerIndex = 0; innerIndex < 4; innerIndex += 1) {
      const inner = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1)), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.22 - innerIndex * 0.03 }));
      structureGroup.add(inner);
      innerShells.push(inner);
    }
    const slabs = [];
    for (let slabIndex = 0; slabIndex < 5; slabIndex += 1) {
      const slab = new THREE.Mesh(new THREE.BoxGeometry(0.88, 0.03, 0.88), new THREE.MeshStandardMaterial({ color: 0xf2efe7, emissive: 0x102033, emissiveIntensity: 0.18, transparent: true, opacity: 0.09 }));
      structureGroup.add(slab);
      slabs.push(slab);
    }
    const columns = [];
    for (let columnIndex = 0; columnIndex < 4; columnIndex += 1) {
      const column = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.94, 0.04), new THREE.MeshStandardMaterial({ color: 0xd8eaff, emissive: 0x0f2436, emissiveIntensity: 0.18, transparent: true, opacity: 0.12 }));
      structureGroup.add(column);
      columns.push(column);
    }
    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.18, 0), new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x8fd8ff, emissiveIntensity: 1.2, roughness: 0.18, metalness: 0.2 }));
    structureGroup.add(core);
    const aura = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glowTexture, color: 0x8fd8ff, transparent: true, opacity: 0.26, depthWrite: false, blending: THREE.AdditiveBlending }));
    aura.scale.set(1.8, 1.8, 1.8);
    structureGroup.add(aura);
    return { layerId: layer.id, anchorGroup, structureGroup, entityRoot, shell, edges, portal, innerShells, slabs, columns, core, aura, lastPosition: this.layerPosition(layer, index) };
  }

  layerPosition(layer, index) {
    const anchor = layer?.meta?.anchor || {};
    const depth = safeNumber(layer?.meta?.depth, index);
    return new THREE.Vector3(-4.6 + safeNumber(anchor.x, 0) * 2.3 + depth * 0.26, 3.6 - depth * 0.82 + safeNumber(anchor.y, 0) * 3.3, safeNumber(anchor.z, -depth * 4.2) - 1.5);
  }

  updateLayerView(view, layer, index) {
    const meta = layer.meta || {};
    const dimensions = meta.dimensions || {};
    const energy = safeNumber(meta.energy, 0.3);
    const resonance = safeNumber(meta.resonance, 0.4);
    const distortion = safeNumber(meta.distortion, 0.16);
    const dimension = dimensionForLayer(layer, index);
    const focus = this.world?.camera?.focus_layer === layer.id;
    const position = this.layerPosition(layer, index);
    view.lastPosition.copy(position);
    view.anchorGroup.position.copy(position);
    view.anchorGroup.rotation.x = 0.08 + distortion * 0.08;
    view.anchorGroup.rotation.y = Math.sin(this.motion.time * 0.18 + index * 0.5) * 0.08 + distortion * 0.14;
    view.anchorGroup.rotation.z = Math.sin(this.motion.time * 0.36 + index * 0.9) * 0.03 + distortion * 0.12 - (focus ? 0.06 : 0);
    const width = safeNumber(dimensions.x, 9.6 - index * 0.58) * 0.62;
    const height = safeNumber(dimensions.y, 6.4 - index * 0.42) * 0.64;
    const depth = safeNumber(dimensions.z, 4 - index * 0.22) * 0.7;
    view.structureGroup.scale.set(width, height, depth);
    const tone = layerColor(layer, index);
    view.shell.material.color.copy(tone).lerp(new THREE.Color(0x060a0f), 0.76);
    view.shell.material.opacity = 0.08 + energy * 0.09;
    view.edges.material.color.copy(tone);
    view.edges.material.opacity = 0.44 + resonance * 0.34 + (focus ? 0.12 : 0);
    view.portal.material.color.copy(tone.clone().lerp(new THREE.Color(0xffffff), 0.24));
    view.portal.material.opacity = 0.18 + energy * 0.14 + (focus ? 0.14 : 0);
    view.portal.rotation.z = this.motion.time * (0.14 + index * 0.03);
    view.portal.scale.setScalar(1.16 + normalized(dimension, 64, 1536) * 0.9 + (focus ? 0.12 : 0));
    const detailBands = Math.max(1, Math.round(normalized(dimension, 64, 1536) * 4));
    view.innerShells.forEach((inner, innerIndex) => {
      const enabled = innerIndex < detailBands;
      inner.visible = enabled;
      if (!enabled) return;
      inner.scale.setScalar(0.82 - innerIndex * 0.12);
      inner.material.color.copy(tone).lerp(new THREE.Color(0xffffff), innerIndex * 0.15);
      inner.material.opacity = 0.23 - innerIndex * 0.03 + energy * 0.08;
      inner.rotation.y = this.motion.time * (0.1 + innerIndex * 0.05) * (innerIndex % 2 === 0 ? 1 : -1);
    });
    view.slabs.forEach((slab, slabIndex) => {
      slab.visible = slabIndex <= detailBands;
      slab.material.color.copy(tone).lerp(new THREE.Color(0xf4efe3), 0.62);
      slab.material.opacity = 0.08 + energy * 0.08;
      slab.position.set(0, -0.42 + slabIndex * (0.18 + distortion * 0.04), Math.sin(this.motion.time * 0.6 + slabIndex + index) * 0.05);
      slab.rotation.z = (slabIndex - 2) * 0.026 + Math.sin(this.motion.time * 0.7 + slabIndex) * 0.02 + distortion * 0.06;
    });
    const corners = [[-0.46, 0, -0.46], [0.46, 0, -0.46], [-0.46, 0, 0.46], [0.46, 0, 0.46]];
    view.columns.forEach((column, columnIndex) => {
      const [x, y, z] = corners[columnIndex];
      column.position.set(x, y, z);
      column.material.color.copy(tone).lerp(new THREE.Color(0xf6f2ea), 0.45);
      column.material.opacity = 0.08 + resonance * 0.08;
    });
    view.core.material.color.copy(tone.clone().lerp(new THREE.Color(0xffffff), 0.28));
    view.core.material.emissive.copy(tone);
    view.core.material.emissiveIntensity = 0.88 + energy * 1.2 + (focus ? 0.8 : 0);
    view.core.position.y = Math.sin(this.motion.time * 0.8 + index) * 0.08;
    view.core.scale.setScalar(0.18 + resonance * 0.24 + (focus ? 0.08 : 0));
    view.aura.material.color.copy(tone);
    view.aura.material.opacity = 0.14 + energy * 0.16 + (focus ? 0.18 : 0);
    view.aura.scale.setScalar(1.8 + resonance * 1.1 + (focus ? 0.6 : 0));
  }
  createEntityView(entity, layer) {
    const group = new THREE.Group();
    const tone = new THREE.Color(entity.color || '#9fd8ff');
    let mesh;
    switch (entity.kind) {
      case 'avatar': mesh = new THREE.Mesh(new THREE.SphereGeometry(0.24, 18, 18), createMaterial(tone)); break;
      case 'qubit': mesh = new THREE.Mesh(new THREE.OctahedronGeometry(0.24, 0), createMaterial(tone)); break;
      case 'orb':
      case 'aura': mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(0.22, 1), createMaterial(tone)); break;
      case 'cabinet':
      case 'terminal':
      case 'screen': mesh = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.58, 0.18), createMaterial(tone)); break;
      case 'bridge': mesh = new THREE.Mesh(new THREE.BoxGeometry(0.92, 0.06, 0.22), createMaterial(tone)); break;
      case 'glyph': mesh = new THREE.Mesh(new THREE.TorusKnotGeometry(0.15, 0.035, 48, 8), createMaterial(tone)); break;
      case 'totem': mesh = new THREE.Mesh(new THREE.ConeGeometry(0.22, 0.58, 12), createMaterial(tone)); break;
      case 'core': mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(0.34, 1), createMaterial(tone)); break;
      default: mesh = new THREE.Mesh(new THREE.DodecahedronGeometry(0.18, 0), createMaterial(tone)); break;
    }
    group.add(mesh);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glowTexture, color: tone, transparent: true, opacity: 0.25, depthWrite: false, blending: THREE.AdditiveBlending }));
    glow.scale.set(1.2, 1.2, 1.2);
    group.add(glow);
    let ring = null;
    if (entity.kind === 'qubit' || entity.kind === 'avatar') {
      ring = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.012, 8, 48), new THREE.MeshBasicMaterial({ color: tone, transparent: true, opacity: 0.3 }));
      ring.rotation.x = 1.1;
      group.add(ring);
    }
    return { entityId: entity.entity_id, group, mesh, glow, ring, layerId: layer?.id ?? null };
  }

  entityLocalPosition(entity, layer) {
    const anchor = layer?.meta?.anchor || { x: 0, y: 0, z: 0 };
    return new THREE.Vector3((safeNumber(entity.position?.x, 0) - safeNumber(anchor.x, 0)) * 0.82, (safeNumber(entity.position?.y, 0) - safeNumber(anchor.y, 0)) * 0.82, (safeNumber(entity.position?.z, 0) - safeNumber(anchor.z, 0)) * 0.94);
  }

  updateEntityView(view, entity, layer) {
    const tone = new THREE.Color(entity.color || '#9fd8ff');
    const position = layer ? this.entityLocalPosition(entity, layer) : new THREE.Vector3(safeNumber(entity.position?.x, 0), safeNumber(entity.position?.y, 0), safeNumber(entity.position?.z, 0));
    view.group.position.copy(position);
    view.group.rotation.set(THREE.MathUtils.degToRad(safeNumber(entity.rotation?.x, 0)), THREE.MathUtils.degToRad(safeNumber(entity.rotation?.y, 0)), THREE.MathUtils.degToRad(safeNumber(entity.rotation?.z, 0)));
    const scale = safeNumber(entity.scale, 1) * 0.54;
    view.group.scale.setScalar(scale);
    view.mesh.material.color.copy(tone.clone().lerp(new THREE.Color(0x0a1119), 0.26));
    view.mesh.material.emissive.copy(tone);
    view.mesh.material.emissiveIntensity = 0.65 + safeNumber(entity.energy, 0.25) * 1.35;
    view.glow.material.color.copy(tone);
    view.glow.material.opacity = 0.18 + safeNumber(entity.energy, 0.25) * 0.26;
    view.glow.scale.setScalar(1.2 + safeNumber(entity.energy, 0.25) * 1.2);
    if (view.ring) {
      const flash = safeNumber(entity.state?.flash, 0);
      const collapsed = entity.state?.collapsed ? 1 : 0;
      view.ring.material.color.copy(tone.clone().lerp(new THREE.Color(0xffffff), 0.2));
      view.ring.material.opacity = 0.16 + flash * 0.45 + collapsed * 0.22;
      view.ring.rotation.z = this.motion.time * (0.35 + scale * 0.2);
      view.ring.scale.setScalar(1 + flash * 0.3 + collapsed * 0.1);
    }
    if (entity.kind === 'qubit') {
      view.mesh.rotation.y += this.motion.time * 0.55;
    }
  }

  syncLayers() {
    if (!this.world) return;
    const liveIds = new Set();
    this.world.layers.forEach((layer, index) => {
      liveIds.add(layer.id);
      let view = this.layerViews.get(layer.id);
      if (!view) {
        view = this.createLayerView(layer, index);
        this.layerViews.set(layer.id, view);
        this.architectureGroup.add(view.anchorGroup);
      }
      this.updateLayerView(view, layer, index);
    });
    for (const [layerId, view] of this.layerViews.entries()) {
      if (liveIds.has(layerId)) continue;
      this.architectureGroup.remove(view.anchorGroup);
      disposeObject(view.anchorGroup);
      this.layerViews.delete(layerId);
    }
    this.updateFocusTarget();
  }

  syncEntities() {
    if (!this.world) return;
    const layersById = new Map(this.world.layers.map((layer) => [layer.id, layer]));
    const liveIds = new Set();
    this.world.entities.forEach((entity) => {
      liveIds.add(entity.entity_id);
      const parentLayer = layersById.get(entity.layer_id);
      let view = this.entityViews.get(entity.entity_id);
      if (!view) {
        view = this.createEntityView(entity, parentLayer);
        this.entityViews.set(entity.entity_id, view);
      }
      const layerView = this.layerViews.get(parentLayer?.id);
      const intendedParent = layerView?.entityRoot || this.freeEntityGroup;
      if (view.group.parent !== intendedParent) intendedParent.add(view.group);
      this.updateEntityView(view, entity, parentLayer);
    });
    for (const [entityId, view] of this.entityViews.entries()) {
      if (liveIds.has(entityId)) continue;
      view.group.parent?.remove(view.group);
      disposeObject(view.group);
      this.entityViews.delete(entityId);
    }
  }

  syncLinks() {
    if (!this.world) return;
    const liveIds = new Set();
    this.world.links.forEach((link, index) => {
      const id = `${link.source_layer}->${link.target_layer}`;
      liveIds.add(id);
      const source = this.layerViews.get(link.source_layer);
      const target = this.layerViews.get(link.target_layer);
      if (!source || !target) return;
      let mesh = this.linkViews.get(id);
      const start = source.lastPosition.clone();
      const end = target.lastPosition.clone();
      const arc = start.clone().lerp(end, 0.5);
      arc.y += 0.65 + index * 0.05;
      const curve = new THREE.CatmullRomCurve3([start, arc, end]);
      const geometry = new THREE.TubeGeometry(curve, 28, 0.03 + safeNumber(link.flux, 0.2) * 0.04, 10, false);
      if (!mesh) {
        mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: 0x8ed7ff, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false }));
        this.linkGroup.add(mesh);
        this.linkViews.set(id, mesh);
      } else {
        mesh.geometry.dispose();
        mesh.geometry = geometry;
      }
      mesh.material.opacity = 0.15 + safeNumber(link.flux, 0.2) * 0.4;
    });
    for (const [id, mesh] of this.linkViews.entries()) {
      if (liveIds.has(id)) continue;
      this.linkGroup.remove(mesh);
      disposeObject(mesh);
      this.linkViews.delete(id);
    }
  }

  updateFocusTarget() {
    if (!this.world?.layers?.length) return;
    const targetLayerId = this.world.camera?.focus_layer;
    const focusedIndex = this.world.layers.findIndex((layer) => layer.id === targetLayerId);
    const index = focusedIndex >= 0 ? focusedIndex : Math.min(2, this.world.layers.length - 1);
    const view = this.layerViews.get(this.world.layers[index].id);
    if (!view) return;
    this.focusTarget.copy(view.lastPosition);
    this.focusTarget.y += 0.16;
    this.cameraState.targetDistance = clamp(safeNumber(this.world.camera?.distance, 12.5) + 3.2, 8, 23);
  }

  setWorld(world) {
    this.world = world;
    this.syncLayers();
    this.syncEntities();
    this.syncLinks();
  }

  start() {
    if (this.frameHandle) return;
    this.frameHandle = true;
    this.renderer.setAnimationLoop(() => this.renderFrame());
  }

  resize() {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8));
    this.renderer.setSize(window.innerWidth, window.innerHeight, false);
  }
  updateOcean(time, delta) {
    const metrics = this.world?.metrics || {};
    const dreamFlux = safeNumber(metrics.dream_flux, 0.34);
    const voidPressure = safeNumber(metrics.void_pressure, 0.2);
    const attr = this.ocean.geometry.attributes.position;
    const array = attr.array;
    for (let index = 0; index < array.length; index += 3) {
      const baseX = this.oceanBase[index];
      const baseZ = this.oceanBase[index + 2];
      array[index + 1] =
        Math.sin(baseX * 0.085 + time * 0.88) * (0.22 + dreamFlux * 0.18) +
        Math.cos(baseZ * 0.06 - time * 0.62) * (0.12 + voidPressure * 0.12) +
        Math.sin((baseX + baseZ) * 0.03 + time * 0.55) * 0.12;
    }
    attr.needsUpdate = true;
    this.ocean.geometry.computeVertexNormals();
    this.ocean.position.y = -5.55 + Math.sin(time * 0.2) * 0.08;
    this.ocean.material.emissiveIntensity = 0.52 + dreamFlux * 0.36;
    this.ocean.material.color.setHSL(0.55, 0.62, 0.18 + dreamFlux * 0.06);
    this.oceanTrench.rotation.y += delta * 0.02;
  }

  updateBackdrop(time, delta) {
    const metrics = this.world?.metrics || {};
    const quantumFlux = safeNumber(metrics.quantum_flux, 0.38);
    const dreamFlux = safeNumber(metrics.dream_flux, 0.42);
    const voidPressure = safeNumber(metrics.void_pressure, 0.26);
    const collapsed = safeNumber(metrics.collapsed_qubits, 0);
    this.scene.fog.density = 0.018 + voidPressure * 0.02;
    this.starField.rotation.y += delta * 0.004;
    this.starField.rotation.x = Math.sin(time * 0.03) * 0.04;
    this.starField.material.opacity = 0.82 + quantumFlux * 0.28;
    this.blackHoleGroup.rotation.z += delta * 0.03;
    this.blackHoleHalo.material.opacity = 0.18 + quantumFlux * 0.24 + voidPressure * 0.12;
    this.blackHoleHalo.scale.setScalar(16 + quantumFlux * 6 + collapsed * 0.3);
    this.blackHoleLens.lookAt(this.camera.position);
    this.accretionRings.forEach((ring, index) => {
      ring.rotation.z += delta * (0.18 + index * 0.08);
      ring.material.emissiveIntensity = 1 + quantumFlux * 1.2 - index * 0.18;
      ring.material.opacity = 0.34 + quantumFlux * 0.12 - index * 0.05;
      ring.scale.setScalar(1 + Math.sin(time * (0.4 + index * 0.12)) * 0.01);
    });
    this.blackHoleParticles.forEach((spark, index) => {
      const spin = time * spark.userData.speed + spark.userData.angle;
      spark.position.set(Math.cos(spin) * spark.userData.radius, Math.sin(spin * 1.8) * 0.35 + spark.userData.height, Math.sin(spin) * spark.userData.radius * 0.35);
      spark.scale.setScalar(1 + Math.sin(time * 3 + index) * 0.25 + quantumFlux * 0.2);
    });
    this.dwarfStarGroup.rotation.y += delta * 0.08;
    this.dwarfStarAura.material.opacity = 0.26 + quantumFlux * 0.26;
    this.dwarfStarAura.scale.setScalar(8.2 + quantumFlux * 3.2);
    this.atomicRings.forEach((ring, index) => {
      ring.rotation.z += delta * (0.22 + index * 0.09);
      ring.material.opacity = 0.28 + dreamFlux * 0.16 - index * 0.03;
    });
    this.electrons.forEach((electron) => {
      const ringIndex = Math.round((electron.userData.radius - 2.2) / 1.05);
      const angle = time * electron.userData.speed + electron.userData.phase;
      electron.position.set(Math.cos(angle) * electron.userData.radius, Math.sin(angle + electron.userData.tilt) * 0.7, Math.sin(angle) * electron.userData.radius * (0.45 + ringIndex * 0.06));
    });
    this.seamPlane.material.opacity = 0.22 + dreamFlux * 0.18 + voidPressure * 0.16;
    this.seamPlane.scale.set(1 + quantumFlux * 0.2, 1 + dreamFlux * 0.12, 1);
    this.seamPlane.lookAt(this.camera.position);
    this.debris.forEach((piece, index) => {
      const theta = time * piece.userData.speed + piece.userData.offset;
      piece.position.set(Math.cos(theta) * piece.userData.radius, piece.userData.height + Math.sin(theta * piece.userData.wobble) * 0.5, piece.userData.depth + Math.sin(theta) * 2.8);
      piece.rotation.set(theta * 0.7, theta * 0.4 + index * 0.02, theta * 0.6);
      piece.material.opacity = 0.14 + voidPressure * 0.18;
    });
  }

  updateCamera(delta) {
    this.pointerDrift.lerp(this.pointer, 0.06);
    this.focusCurrent.x = THREE.MathUtils.damp(this.focusCurrent.x, this.focusTarget.x, 4.5, delta);
    this.focusCurrent.y = THREE.MathUtils.damp(this.focusCurrent.y, this.focusTarget.y, 4.5, delta);
    this.focusCurrent.z = THREE.MathUtils.damp(this.focusCurrent.z, this.focusTarget.z, 4.5, delta);
    this.cameraState.yaw = THREE.MathUtils.damp(this.cameraState.yaw, this.cameraState.targetYaw, 4.6, delta);
    this.cameraState.pitch = THREE.MathUtils.damp(this.cameraState.pitch, this.cameraState.targetPitch, 4.6, delta);
    this.cameraState.distance = THREE.MathUtils.damp(this.cameraState.distance, this.cameraState.targetDistance, 4.8, delta);
    const yaw = this.cameraState.yaw + this.pointerDrift.x * 0.1;
    const pitch = this.cameraState.pitch + this.pointerDrift.y * -0.06;
    const distance = this.cameraState.distance;
    const orbitOffset = new THREE.Vector3(Math.sin(yaw) * Math.cos(pitch) * distance, Math.sin(pitch) * distance, Math.cos(yaw) * Math.cos(pitch) * distance);
    const target = this.focusCurrent.clone().add(new THREE.Vector3(this.pointerDrift.x * 1.2, this.pointerDrift.y * -0.8, 0));
    this.camera.position.copy(target).add(orbitOffset);
    this.camera.lookAt(target.x, target.y + 0.05, target.z);
  }

  renderFrame() {
    const delta = Math.min(this.clock.getDelta(), 0.033);
    this.motion.time += delta;
    this.updateBackdrop(this.motion.time, delta);
    this.updateOcean(this.motion.time, delta);
    this.updateCamera(delta);
    this.renderer.render(this.scene, this.camera);
  }
}
