<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Hand, Home, Orbit, ZoomIn, ZoomOut } from 'lucide-vue-next';
import { Box3, BoxGeometry, Color, DirectionalLight, Fog, Group, HemisphereLight, MOUSE, Mesh, MeshBasicMaterial, MeshStandardMaterial, Object3D, PerspectiveCamera, PointLight, Raycaster, Scene, Sphere, SphereGeometry, SRGBColorSpace, Vector2, Vector3, WebGLRenderer } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { Alert, Asset } from '../types';
import { cameraFitDistance } from '../utils/cameraFit';
import { leakPipeNodeNames, modelNodeNames, nextTwinCameraDistance, primaryTwinAlert, resolveTwinVisualState, summarizeTwinModelBindings, twinModelUrl, type TwinModelBindingReport, type TwinVisualState } from '../services/twin3d';

const props = defineProps<{ assets: Asset[]; alerts: Alert[]; selectedCode: string | null; modelUrl?: string; leakAssetCode?: string | null }>();
const emit = defineEmits<{ select: [code: string]; modelReport: [report: TwinModelBindingReport] }>();
const host = ref<HTMLDivElement>();
const modelState = ref<'loading' | 'loaded' | 'fallback'>('loading');
const modelMessage = ref('正在加载三维模型…');
const modelProgress = ref(0);
const performanceMode = ref<'full' | 'reduced'>('full');
const navigationMode = ref<'pan' | 'orbit'>('pan');
let scene: Scene | undefined;
let camera: PerspectiveCamera | undefined;
let renderer: WebGLRenderer | undefined;
let controls: OrbitControls | undefined;
let frame = 0;
let lastRenderedAt = 0;
let resizeObserver: ResizeObserver | undefined;
const raycaster = new Raycaster();
const pointer = new Vector2();
const assetObjects = new Map<string, Object3D>();
// Cache the materials that need a live emissive pulse while the model is
// bound. Traversing a full Blender scene for every asset on every animation
// frame is prohibitively expensive on integrated GPUs and can starve normal
// UI navigation. The scene graph is static between model reloads, so cache
// the small material lists once and update only those materials per frame.
const animatedMaterials = new Map<string, MeshStandardMaterial[]>();
const modelBoundCodes = new Set<string>();
const materialBaselines = new WeakMap<MeshStandardMaterial, { color: Color; emissive: Color }>();
let modelRoot: Object3D | undefined;
let fallbackSceneRoot: Group | undefined;
let fallbackAssetRoot: Group | undefined;
let leakOverlayRoot: Group | undefined;
let leakOverlayMaterial: MeshBasicMaterial | undefined;
let modelLoadToken = 0;
let modelLoadTimeout = 0;
let sceneRadius = 18;
let pendingPanGesture: { pointerId: number; startX: number; startY: number; target: Vector3 } | undefined;

const colors: Record<TwinVisualState, number> = { normal: 0x4ee7c3, warning: 0xffbb62, alarm: 0xff536f, unknown: 0x6d87aa };

function publishCameraDistance() {
  if (!host.value || !camera || !controls) return;
  host.value.dataset.cameraDistance = camera.position.distanceTo(controls.target).toFixed(4);
  host.value.dataset.cameraPosition = camera.position.toArray().map((value) => value.toFixed(4)).join(',');
  host.value.dataset.cameraTarget = controls.target.toArray().map((value) => value.toFixed(4)).join(',');
}

function makeFallbackScene() {
  if (!scene) return;
  if (fallbackSceneRoot) return;
  fallbackSceneRoot = new Group();
  fallbackSceneRoot.name = 'TUNNEL_FALLBACK';
  scene.add(fallbackSceneRoot);
  const corridor = new Group();
  corridor.name = 'TUNNEL_FALLBACK_CORRIDOR';
  const floor = new Mesh(new BoxGeometry(32, .32, 18), new MeshStandardMaterial({ color: 0x102643, metalness: .5, roughness: .44 }));
  floor.position.y = -.2;
  corridor.add(floor);
  const wallMaterial = new MeshStandardMaterial({ color: 0x173558, metalness: .38, roughness: .56, transparent: true, opacity: .88 });
  for (const side of [-1, 1]) {
    const wall = new Mesh(new BoxGeometry(32, 5.5, .18), wallMaterial.clone());
    wall.position.set(0, 2.55, side * 8.8);
    corridor.add(wall);
  }
  const ceiling = new Mesh(new BoxGeometry(32, .18, 18), wallMaterial.clone());
  ceiling.position.y = 5.2;
  corridor.add(ceiling);
  for (let x = -14; x <= 14; x += 4) {
    const light = new PointLight(0x6e9cff, 1.5, 12, 2);
    light.position.set(x, 4.5, 0);
    corridor.add(light);
    const strip = new Mesh(new BoxGeometry(1.2, .08, .32), new MeshBasicMaterial({ color: 0xa6b8ff }));
    strip.position.copy(light.position);
    corridor.add(strip);
  }
  fallbackSceneRoot.add(corridor);
  props.assets.forEach((asset) => addFallbackAsset(asset));
}

function publishModelReport(mode: TwinModelBindingReport['mode'], boundCodes: Iterable<string> = []) {
  emit('modelReport', { mode, ...summarizeTwinModelBindings(props.assets, boundCodes) });
}

function addFallbackAsset(asset: Asset) {
  if (!scene || assetObjects.has(asset.code)) return;
  if (!fallbackAssetRoot) {
    fallbackAssetRoot = new Group();
    fallbackAssetRoot.name = 'TWIN_FALLBACK_ASSETS';
    scene.add(fallbackAssetRoot);
  }
  const group = new Group();
  group.name = asset.mesh || asset.code;
  group.userData.assetCode = asset.code;
  const box = new Mesh(new BoxGeometry(.72, .72, .72), new MeshStandardMaterial({ color: 0x294a71, metalness: .48, roughness: .25, emissive: 0x000000 }));
  const beacon = new Mesh(new SphereGeometry(.18, 18, 18), new MeshStandardMaterial({ color: 0xffffff, emissive: 0x4ee7c3, emissiveIntensity: 1.7 }));
  beacon.position.y = .55;
  group.add(box, beacon);
  group.position.set((Number(asset.position.x) / 100 - .5) * 27, .45, (Number(asset.position.y) / 100 - .5) * 14);
  fallbackAssetRoot.add(group);
  assetObjects.set(asset.code, group);
  animatedMaterials.set(asset.code, [box.material, beacon.material]);
}

function normalizedModelNodeName(value: unknown) {
  return typeof value === 'string' ? value.trim().toUpperCase().replace(/[^A-Z0-9]/g, '') : '';
}

/**
 * GLTFLoader may de-duplicate or sanitize Object3D.name while retaining the
 * original Blender node name in userData.name. Resolve both representations,
 * then use a punctuation-insensitive alias as a final compatibility bridge.
 * This keeps legacy exports usable without weakening the formal mesh contract.
 */
function findModelNode(root: Object3D, asset: Asset) {
  const candidates = modelNodeNames(asset);
  for (const candidate of candidates) {
    const exact = root.getObjectByName(candidate);
    if (exact) return exact;
  }

  let originalNameMatch: Object3D | undefined;
  const normalizedCandidates = new Set(candidates.map(normalizedModelNodeName).filter(Boolean));
  let normalizedMatch: Object3D | undefined;
  root.traverse((object) => {
    if (originalNameMatch) return;
    const originalName = object.userData?.name;
    if (typeof originalName === 'string' && candidates.includes(originalName)) {
      originalNameMatch = object;
      return;
    }
    if (!normalizedMatch && (
      normalizedCandidates.has(normalizedModelNodeName(object.name))
      || normalizedCandidates.has(normalizedModelNodeName(originalName))
    )) normalizedMatch = object;
  });
  return originalNameMatch || normalizedMatch;
}

function bindModelAssets(root: Object3D) {
  const boundCodes: string[] = [];
  props.assets.forEach((asset) => {
    if (modelBoundCodes.has(asset.code)) { boundCodes.push(asset.code); return; }
    const node = findModelNode(root, asset);
    if (!node) {
      addFallbackAsset(asset);
      return;
    }
    node.userData.assetCode = asset.code;
    const materials: MeshStandardMaterial[] = [];
    node.traverse((child) => {
      child.userData.assetCode = asset.code;
      if (!(child instanceof Mesh)) return;
      child.material = Array.isArray(child.material) ? child.material.map((material) => material.clone()) : child.material.clone();
      const childMaterials = Array.isArray(child.material) ? child.material : [child.material];
      childMaterials.forEach((material) => { if (material instanceof MeshStandardMaterial) materials.push(material); });
    });
    assetObjects.set(asset.code, node);
    animatedMaterials.set(asset.code, materials);
    modelBoundCodes.add(asset.code);
    boundCodes.push(asset.code);
  });
  return boundCodes;
}

function syncSceneAssets() {
  if (modelRoot) publishModelReport('loaded', bindModelAssets(modelRoot));
  else if (modelState.value === 'fallback') {
    props.assets.forEach((asset) => addFallbackAsset(asset));
    publishModelReport('fallback');
  }
}

function clearLeakOverlay() {
  if (!leakOverlayRoot) return;
  leakOverlayRoot.traverse((object) => {
    if (!(object instanceof Mesh)) return;
    object.geometry.dispose();
    (Array.isArray(object.material) ? object.material : [object.material]).forEach((material) => material.dispose());
  });
  leakOverlayRoot.removeFromParent();
  leakOverlayRoot = undefined;
  leakOverlayMaterial = undefined;
}

function syncLeakOverlay() {
  clearLeakOverlay();
  if (!scene || !props.leakAssetCode) return;
  const asset = props.assets.find((item) => item.code === props.leakAssetCode);
  if (!asset) return;
  let target: Object3D | undefined;
  if (modelRoot) {
    for (const name of leakPipeNodeNames(asset)) {
      target = modelRoot.getObjectByName(name);
      if (target) break;
    }
  }
  target ||= assetObjects.get(asset.code);
  const bounds = target ? new Box3().setFromObject(target) : new Box3();
  const centre = bounds.isEmpty()
    ? new Vector3((Number(asset.position.x) / 100 - .5) * 27, .6, (Number(asset.position.y) / 100 - .5) * 14)
    : bounds.getCenter(new Vector3());
  const size = bounds.isEmpty() ? new Vector3(4.2, .34, .34) : bounds.getSize(new Vector3());
  const pipeLength = Math.max(size.x, size.z, sceneRadius * .11, 2.2);
  const pipeWidth = Math.max(Math.min(size.y, pipeLength * .18), sceneRadius * .008, .16);
  leakOverlayRoot = new Group();
  leakOverlayRoot.name = `LEAK_PIPE_OVERLAY_${asset.code}`;
  leakOverlayRoot.userData.assetCode = asset.code;
  leakOverlayRoot.position.copy(centre);
  leakOverlayMaterial = new MeshBasicMaterial({ color: 0xff244f, transparent: true, opacity: .48, depthWrite: false });
  const body = new Mesh(new BoxGeometry(pipeLength, pipeWidth, pipeWidth), leakOverlayMaterial);
  const outline = new Mesh(new BoxGeometry(pipeLength * 1.04, pipeWidth * 1.75, pipeWidth * 1.75), new MeshBasicMaterial({ color: 0xff708c, wireframe: true, transparent: true, opacity: .82, depthWrite: false }));
  const beacon = new PointLight(0xff1748, 3.2, Math.max(pipeLength * 1.8, 5), 2);
  beacon.position.y = pipeWidth * 2;
  leakOverlayRoot.add(body, outline, beacon);
  scene.add(leakOverlayRoot);
}

function clearLoadedModel() {
  window.clearTimeout(modelLoadTimeout);
  const disposableRoots = [modelRoot, fallbackSceneRoot, fallbackAssetRoot].filter(Boolean) as Object3D[];
  const disposedGeometries = new Set<object>();
  const disposedMaterials = new Set<object>();
  disposableRoots.forEach((root) => root.traverse((object) => {
    if (!(object instanceof Mesh)) return;
    if (!disposedGeometries.has(object.geometry)) {
      object.geometry.dispose();
      disposedGeometries.add(object.geometry);
    }
    (Array.isArray(object.material) ? object.material : [object.material]).forEach((material) => {
      if (disposedMaterials.has(material)) return;
      material.dispose();
      disposedMaterials.add(material);
    });
  }));
  modelRoot?.removeFromParent();
  fallbackSceneRoot?.removeFromParent();
  fallbackAssetRoot?.removeFromParent();
  modelRoot = undefined;
  fallbackSceneRoot = undefined;
  fallbackAssetRoot = undefined;
  modelBoundCodes.clear();
  assetObjects.clear();
  animatedMaterials.clear();
  clearLeakOverlay();
}

function visualIntensity(state: TwinVisualState, selected: boolean, critical: boolean, now = 0) {
  if (state === 'alarm') return (critical ? 2.1 : 1.55) + Math.sin(now * (critical ? 7 : 4.5)) * (critical ? .72 : .38) + (selected ? .55 : 0);
  if (selected) return 2.25;
  return state === 'warning' ? 1.08 : .42;
}

function colorObject(object: Object3D, state: TwinVisualState, selected = false, critical = false) {
  const color = state === 'alarm' && critical ? 0xff3d66 : colors[state];
  object.traverse((child) => {
    if (!(child instanceof Mesh)) return;
    const materials = Array.isArray(child.material) ? child.material : [child.material];
    materials.forEach((material) => {
      if (!(material instanceof MeshStandardMaterial)) return;
      const baseline = materialBaselines.get(material) ?? { color: material.color.clone(), emissive: material.emissive.clone() };
      materialBaselines.set(material, baseline);
      material.color.copy(baseline.color).lerp(new Color(color), selected ? .31 : state === 'alarm' ? .22 : .06);
      material.emissive.copy(baseline.emissive).lerp(new Color(color), state === 'alarm' ? .88 : state === 'warning' ? .52 : .26);
      material.emissiveIntensity = visualIntensity(state, selected, critical);
    });
  });
}

function applyVisualState() {
  props.assets.forEach((asset) => {
    const object = assetObjects.get(asset.code);
    const alert = primaryTwinAlert(asset.code, props.alerts);
    if (object) colorObject(object, resolveTwinVisualState(asset, props.alerts), props.selectedCode === asset.code, alert?.severity === 'critical');
  });
}

function focusAsset(code: string | null) {
  if (!code || !camera || !controls) return;
  const object = assetObjects.get(code);
  if (!object) return;
  const bounds = new Box3().setFromObject(object);
  const target = bounds.isEmpty() ? object.getWorldPosition(new Vector3()) : bounds.getCenter(new Vector3());
  const measuredRadius = bounds.isEmpty() ? sceneRadius * .025 : bounds.getBoundingSphere(new Sphere()).radius;
  // Some Blender exports place an equipment marker on a parent node that also
  // owns adjacent meshes.  Do not let that oversized parent bound turn an
  // equipment focus action into another whole-model view.
  const objectRadius = Math.max(Math.min(measuredRadius, sceneRadius * .12), sceneRadius * .006, .002);
  const distance = Math.max(objectRadius * 3.25, sceneRadius * .018, .05);
  controls.target.copy(target);
  controls.minDistance = Math.max(.002, sceneRadius * .0008);
  camera.position.copy(target.clone().add(new Vector3(1, .72, 1).normalize().multiplyScalar(distance)));
  camera.near = Math.max(.0002, distance / 800);
  camera.updateProjectionMatrix();
  controls.update();
  publishCameraDistance();
}

function resetView() {
  if (!camera || !controls) return;
  const root = modelRoot || fallbackSceneRoot;
  const bounds = root ? new Box3().setFromObject(root) : null;
  if (bounds && !bounds.isEmpty()) {
    const sphere = bounds.getBoundingSphere(new Sphere());
    sceneRadius = Math.max(sphere.radius, .2);
    const distance = cameraFitDistance(sceneRadius, camera.fov, camera.aspect);
    controls.target.copy(sphere.center);
    camera.position.copy(sphere.center.clone().add(new Vector3(1, .68, 1).normalize().multiplyScalar(distance)));
    controls.minDistance = Math.max(.002, sceneRadius * .0008);
    controls.maxDistance = Math.max(20, sceneRadius * 12, distance * 2);
    camera.near = Math.max(.005, sceneRadius / 500);
    camera.far = Math.max(200, controls.maxDistance + sceneRadius * 2);
  } else {
    sceneRadius = 18;
    camera.position.set(18, 13, 22);
    controls.target.set(0, 1.8, 0);
    controls.minDistance = .35;
    controls.maxDistance = 80;
    camera.near = .05;
  }
  camera.updateProjectionMatrix();
  controls.update();
  publishCameraDistance();
}

function zoomBy(scale: number) {
  if (!camera || !controls) return;
  const offset = camera.position.clone().sub(controls.target);
  const currentDistance = Math.max(offset.length(), .001);
  const nextDistance = nextTwinCameraDistance(currentDistance, scale, controls.minDistance, controls.maxDistance);
  camera.position.copy(controls.target.clone().add(offset.normalize().multiplyScalar(nextDistance)));
  camera.near = Math.max(.0002, nextDistance / 1000);
  camera.updateProjectionMatrix();
  controls.update();
  publishCameraDistance();
}

function setNavigationMode(mode: 'pan' | 'orbit') {
  navigationMode.value = mode;
  if (!controls) return;
  // Both modes retain full navigation. The active mode only decides what the
  // primary mouse button does; the secondary button always provides the other
  // operation so an operator never becomes trapped in a fixed-axis view.
  controls.mouseButtons.LEFT = mode === 'pan' ? MOUSE.PAN : MOUSE.ROTATE;
  controls.mouseButtons.RIGHT = mode === 'pan' ? MOUSE.ROTATE : MOUSE.PAN;
}

function onCanvasPointerDown(event: PointerEvent) {
  if (!renderer || !camera || !controls) return;
  if (event.button === 0 && navigationMode.value === 'pan') {
    pendingPanGesture = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      target: controls.target.clone(),
    };
    return;
  }
  // Camera gestures must never select an object and pull the target back to it.
  if (event.button !== 0 || event.shiftKey || event.ctrlKey || event.metaKey || navigationMode.value === 'pan') return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects([...assetObjects.values()], true)[0];
  const code = hit?.object.userData.assetCode as string | undefined;
  if (code) emit('select', code);
}

function onCanvasPointerUp(event: PointerEvent) {
  const gesture = pendingPanGesture;
  if (!gesture || gesture.pointerId !== event.pointerId) return;
  pendingPanGesture = undefined;
  if (!renderer || !camera || !controls) return;

  // OrbitControls normally handles the gesture. A pointer-capture transition
  // can occasionally swallow its move events in Chromium (notably around
  // fullscreen/custom-cursor layers). If that happened, apply the same
  // screen-space translation once on release so left-button panning remains
  // deterministic instead of appearing unresponsive.
  if (controls.target.distanceToSquared(gesture.target) > 1e-10) {
    publishCameraDistance();
    return;
  }
  const deltaX = event.clientX - gesture.startX;
  const deltaY = event.clientY - gesture.startY;
  if (Math.hypot(deltaX, deltaY) < 4) return;
  const height = Math.max(renderer.domElement.clientHeight, 1);
  const distance = Math.max(camera.position.distanceTo(controls.target), .001);
  const worldPerPixel = 2 * distance * Math.tan(camera.fov * Math.PI / 360) / height;
  const offset = new Vector3(1, 0, 0).applyQuaternion(camera.quaternion).multiplyScalar(-deltaX * worldPerPixel)
    .add(new Vector3(0, 1, 0).applyQuaternion(camera.quaternion).multiplyScalar(deltaY * worldPerPixel));
  camera.position.add(offset);
  controls.target.add(offset);
  controls.update();
  publishCameraDistance();
}

function cancelCanvasPan() { pendingPanGesture = undefined; }

function animate(timestamp = 0) {
  frame = window.requestAnimationFrame(animate);
  // Software WebGL, low-core industrial terminals and users who request less
  // motion should not spend the entire main-thread budget repainting a static
  // model. 30 FPS keeps camera gestures responsive while leaving enough time
  // for surrounding navigation and business controls.
  const minimumFrameInterval = performanceMode.value === 'reduced' ? 1000 / 30 : 0;
  if (minimumFrameInterval && timestamp - lastRenderedAt < minimumFrameInterval) return;
  lastRenderedAt = timestamp;
  const now = performance.now() / 1000;
  if (leakOverlayRoot && leakOverlayMaterial) {
    const pulse = .72 + Math.sin(now * 6.5) * .22;
    leakOverlayMaterial.opacity = pulse;
    leakOverlayRoot.scale.set(1, 1 + pulse * .28, 1 + pulse * .28);
  }
  props.assets.forEach((asset) => {
    const materials = animatedMaterials.get(asset.code);
    if (!materials?.length) return;
    const state = resolveTwinVisualState(asset, props.alerts);
    const critical = primaryTwinAlert(asset.code, props.alerts)?.severity === 'critical';
    const intensity = visualIntensity(state, props.selectedCode === asset.code, critical, now);
    materials.forEach((material) => { material.emissiveIntensity = intensity; });
  });
  controls?.update();
  if (renderer && scene && camera) renderer.render(scene, camera);
}

function loadModel() {
  if (!scene) return;
  const loadToken = ++modelLoadToken;
  modelProgress.value = 0;
  modelState.value = 'loading';
  modelMessage.value = '正在加载实体三维模型…';
  window.clearTimeout(modelLoadTimeout);
  modelLoadTimeout = window.setTimeout(() => {
    if (loadToken !== modelLoadToken) return;
    modelLoadToken += 1;
    makeFallbackScene();
    publishModelReport('fallback');
    modelState.value = 'fallback';
    modelMessage.value = '实体模型加载超时，已切换到安全预览，可重新检测';
    applyVisualState();
    syncLeakOverlay();
    resetView();
    // The GLTF success/error paths restore focus after a late model ready; the
    // timeout fallback must do the same so a new-alarm auto-locate that arrived
    // while the model was still loading is not silently dropped.
    if (props.selectedCode) focusAsset(props.selectedCode);
  }, 25_000);
  new GLTFLoader().load(props.modelUrl || twinModelUrl, (gltf) => {
    if (loadToken !== modelLoadToken || !scene) return;
    window.clearTimeout(modelLoadTimeout);
    modelRoot = gltf.scene;
    scene.add(modelRoot);
    publishModelReport('loaded', bindModelAssets(modelRoot));
    modelState.value = 'loaded';
    modelProgress.value = 100;
    modelMessage.value = '已加载实体三维模型';
    applyVisualState();
    syncLeakOverlay();
    resetView();
    if (props.selectedCode) focusAsset(props.selectedCode);
  }, (progress) => {
    if (loadToken !== modelLoadToken) return;
    if (progress.total > 0) {
      modelProgress.value = Math.min(99, Math.round(progress.loaded / progress.total * 100));
      modelMessage.value = `正在加载实体三维模型… ${modelProgress.value}%`;
    } else if (progress.loaded > 0) {
      modelMessage.value = `正在加载实体三维模型… ${(progress.loaded / 1024 / 1024).toFixed(1)} MB`;
    }
  }, () => {
    if (loadToken !== modelLoadToken) return;
    window.clearTimeout(modelLoadTimeout);
    makeFallbackScene();
    publishModelReport('fallback');
    modelState.value = 'fallback';
    modelMessage.value = '等待实体模型交付，当前为可交互预览场景';
    applyVisualState();
    syncLeakOverlay();
    resetView();
    if (props.selectedCode) focusAsset(props.selectedCode);
  });
}

function reloadModel() {
  if (!scene) return;
  clearLoadedModel();
  modelState.value = 'loading';
  modelProgress.value = 0;
  modelMessage.value = '正在重新检测实体三维模型…';
  loadModel();
}

onMounted(() => {
  if (!host.value) return;
  scene = new Scene();
  scene.background = new Color(0x081628);
  scene.fog = new Fog(0x081628, 22, 55);
  camera = new PerspectiveCamera(48, 1, .1, 200);
  const navigatorCapabilities = navigator as Navigator & { deviceMemory?: number };
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const limitedMemory = (navigatorCapabilities.deviceMemory ?? 8) <= 4;
  const limitedCpu = (navigator.hardwareConcurrency || 8) <= 4;
  performanceMode.value = prefersReducedMotion || limitedMemory || limitedCpu ? 'reduced' : 'full';
  renderer = new WebGLRenderer({ antialias: performanceMode.value === 'full', alpha: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, performanceMode.value === 'reduced' ? 1 : 2));
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.shadowMap.enabled = performanceMode.value === 'full';
  host.value.append(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableRotate = true;
  controls.enablePan = true;
  controls.enableZoom = true;
  controls.enableDamping = true;
  controls.dampingFactor = .045;
  controls.rotateSpeed = .72;
  controls.panSpeed = .9;
  controls.zoomSpeed = 1.08;
  controls.screenSpacePanning = true;
  controls.zoomToCursor = true;
  controls.keyPanSpeed = 18;
  controls.minDistance = .35;
  controls.maxDistance = 80;
  controls.minPolarAngle = .01;
  controls.maxPolarAngle = Math.PI - .01;
  setNavigationMode('pan');
  controls.listenToKeyEvents(window);
  controls.addEventListener('change', publishCameraDistance);
  resetView();
  scene.add(new HemisphereLight(0x8ba6ff, 0x071021, 2.1));
  const key = new DirectionalLight(0xb5d5ff, 2.5);
  key.position.set(10, 16, 10);
  scene.add(key);
  renderer.domElement.addEventListener('pointerdown', onCanvasPointerDown);
  window.addEventListener('pointerup', onCanvasPointerUp);
  window.addEventListener('pointercancel', cancelCanvasPan);
  renderer.domElement.addEventListener('webglcontextlost', onContextLost);
  renderer.domElement.addEventListener('webglcontextrestored', onContextRestored);
  resizeObserver = new ResizeObserver(([entry]) => {
    if (!renderer || !camera) return;
    const { width, height } = entry.contentRect;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  });
  resizeObserver.observe(host.value);
  loadModel();
  animate();
});

// Camera focus is a deliberate selection action. Live telemetry and alert
// refreshes must never re-run it, otherwise OrbitControls appears to "spring
// back" while an operator is zooming or rotating the model.
watch(() => props.assets, () => { syncSceneAssets(); applyVisualState(); syncLeakOverlay(); }, { deep: true });
watch(() => props.alerts, applyVisualState, { deep: true });
watch(() => props.leakAssetCode, syncLeakOverlay);
watch(() => props.selectedCode, (next, previous) => {
  applyVisualState();
  if (next && next !== previous) focusAsset(next);
});
watch(() => props.modelUrl, (next, previous) => { if (next && next !== previous) reloadModel(); });
onBeforeUnmount(() => {
  modelLoadToken += 1;
  window.clearTimeout(modelLoadTimeout);
  window.cancelAnimationFrame(frame);
  resizeObserver?.disconnect();
  renderer?.domElement.removeEventListener('pointerdown', onCanvasPointerDown);
  window.removeEventListener('pointerup', onCanvasPointerUp);
  window.removeEventListener('pointercancel', cancelCanvasPan);
  renderer?.domElement.removeEventListener('webglcontextlost', onContextLost);
  renderer?.domElement.removeEventListener('webglcontextrestored', onContextRestored);
  controls?.dispose();
  clearLoadedModel();
  renderer?.dispose();
  assetObjects.clear();
  animatedMaterials.clear();
  modelBoundCodes.clear();
});

function onContextLost(event: Event) {
  event.preventDefault();
  modelState.value = 'fallback';
  modelMessage.value = '三维图形服务暂时不可用，正在等待浏览器恢复';
}

function onContextRestored() {
  modelMessage.value = '三维图形服务已恢复，正在重新加载模型…';
  reloadModel();
}

defineExpose({ resetView, focusAsset, zoomBy, setNavigationMode, reloadModel, modelState, modelMessage, modelProgress });
</script>

<template>
  <div class="twin-scene" :data-model-state="modelState">
    <div ref="host" class="twin-canvas" aria-label="综合管廊三维数字孪生场景" role="application" />
    <div class="twin-model-state"><i :class="modelState" /><span>{{ modelMessage }}</span><em v-if="performanceMode === 'reduced'">流畅模式</em></div>
    <div v-if="modelState === 'loading'" class="twin-model-progress" role="progressbar" aria-label="三维模型加载进度" :aria-valuenow="modelProgress" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${Math.max(modelProgress, 6)}%` }" /></div>
    <div class="twin-camera-controls" role="group" aria-label="三维自由视角控制">
      <button type="button" aria-label="放大三维模型" title="放大" @click="zoomBy(.62)"><ZoomIn /></button>
      <button type="button" aria-label="缩小三维模型" title="缩小" @click="zoomBy(1.55)"><ZoomOut /></button>
      <button type="button" :class="{ active: navigationMode === 'pan' }" :aria-pressed="navigationMode === 'pan'" aria-label="启用自由平移" title="左键自由平移" @click="setNavigationMode('pan')"><Hand /></button>
      <button type="button" :class="{ active: navigationMode === 'orbit' }" :aria-pressed="navigationMode === 'orbit'" aria-label="启用自由旋转" title="左键自由旋转" @click="setNavigationMode('orbit')"><Orbit /></button>
      <button type="button" aria-label="显示完整三维模型" title="显示全景" @click="resetView"><Home /></button>
    </div>
    <div class="twin-scene-tip">{{ navigationMode === 'pan' ? '左键自由平移 · 右键旋转' : '左键旋转 · 右键自由平移' }} · 滚轮指向缩放 · 方向键平移</div>
  </div>
</template>
