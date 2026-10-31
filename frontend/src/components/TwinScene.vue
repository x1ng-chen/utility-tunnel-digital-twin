<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Hand, Home, Orbit, ZoomIn, ZoomOut } from 'lucide-vue-next';
import { Box3, BoxGeometry, Color, DirectionalLight, Fog, Group, HemisphereLight, MOUSE, Mesh, MeshBasicMaterial, MeshStandardMaterial, Object3D, PerspectiveCamera, PointLight, Raycaster, Scene, Sphere, SphereGeometry, SRGBColorSpace, Vector2, Vector3, WebGLRenderer } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { Alert, Asset } from '../types';
import { cameraFitDistance } from '../utils/cameraFit';
import { createFanAnimator, type FanFeedbackContext, type FanVisualFeedback } from '../utils/fanMotion';
import { modelNodeNames, nextTwinCameraDistance, resolveTwinVisualState, summarizeTwinModelBindings, twinModelUrl, type TwinModelBindingReport, type TwinVisualState } from '../services/twin3d';
import TwinAlarmOverlay from './TwinAlarmOverlay.vue';
import { collectVisualAlarms, paintTwinMaterial, twinVisualColors, visualIntensity } from '../utils/twinAlarmStyle';
import { createAlarmEffects, type AlarmTarget } from '../utils/twinAlarmEffects';
import { layoutAlarmLabels, type AlarmAnchor, type AlarmLabel } from '../utils/alarmLabelLayout';

const props = defineProps<{ assets: Asset[]; alerts: Alert[]; selectedCode: string | null; modelUrl?: string; modelEnabled?: boolean; fanFeedback?: FanFeedbackContext; overviewDirection?: number[] }>();
const emit = defineEmits<{ select: [code: string]; modelReport: [report: TwinModelBindingReport] }>();
const host = ref<HTMLDivElement>();
const modelState = ref<'loading' | 'loaded' | 'fallback'>('loading');
const modelMessage = ref('正在加载三维模型…');
const modelProgress = ref(0);
const performanceMode = ref<'full' | 'reduced'>('full');
const navigationMode = ref<'pan' | 'orbit'>('pan');
const visualAlarms = computed(() => collectVisualAlarms(props.assets, props.alerts));
const criticalAlarmCodes = computed(() => new Set(visualAlarms.value.filter(alarm => alarm.severity === 'critical').map(alarm => alarm.assetCode)));
const alarmLabels = ref<AlarmLabel[]>([]);
const unplacedAlarmCodes = ref<string[]>(visualAlarms.value.map(alarm=>alarm.assetCode));
const reducedMotion = ref(false);
let alarmEffects: ReturnType<typeof createAlarmEffects> | undefined;
let lastLabelFrame = 0;
let labelSignature = '';
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
let fanAnimator: ReturnType<typeof createFanAnimator> | undefined;
let lastFanFrame = 0;
const fanStates = ref<FanVisualFeedback[]>([]);
let fanUiSignature = '';
let fallbackSceneRoot: Group | undefined;
let fallbackAssetRoot: Group | undefined;
let modelLoadToken = 0;
let modelLoadTimeout = 0;
let sceneRadius = 18;
let pendingPanGesture: { pointerId: number; startX: number; startY: number; target: Vector3 } | undefined;
let pendingSelectionGesture: { pointerId: number; startX: number; startY: number; code: string } | undefined;

const colors: Record<TwinVisualState, number> = twinVisualColors;

function isFiniteVector(vector: Vector3) {
  return Number.isFinite(vector.x) && Number.isFinite(vector.y) && Number.isFinite(vector.z);
}

function boundingSphere(root: Object3D) {
  const bounds = new Box3().setFromObject(root);
  if (bounds.isEmpty() || !isFiniteVector(bounds.min) || !isFiniteVector(bounds.max)) return null;
  const sphere = bounds.getBoundingSphere(new Sphere());
  return isFiniteVector(sphere.center) && Number.isFinite(sphere.radius) && sphere.radius > 0 ? sphere : null;
}

function publishCameraDistance() {
  if (!host.value || !camera || !controls) return;
  // Never leak a corrupt camera coordinate into the DOM contract used by the
  // control layer or browser checks. resetView() repairs this state before the
  // next rendered frame, but the attribute must remain meaningful meanwhile.
  if (!isFiniteVector(camera.position) || !isFiniteVector(controls.target)) return;
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
  const floor = new Mesh(new BoxGeometry(32, .32, 18), new MeshStandardMaterial({ color: 0xd5e1ee, metalness: .5, roughness: .44 }));
  floor.position.y = -.2;
  corridor.add(floor);
  const wallMaterial = new MeshStandardMaterial({ color: 0xc5d5e8, metalness: .38, roughness: .56, transparent: true, opacity: .88 });
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
  const box = new Mesh(new BoxGeometry(.72, .72, .72), new MeshStandardMaterial({ color: 0x7898bb, metalness: .48, roughness: .25, emissive: 0x000000 }));
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
      if (!(child instanceof Mesh) || child.userData.fanRgb === true) return;
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

function clearLoadedModel() {
  alarmEffects?.clear();
  if (host.value) host.value.dataset.alarmMarkedAssets = '';
  alarmLabels.value = []; unplacedAlarmCodes.value = visualAlarms.value.map(alarm=>alarm.assetCode); labelSignature = ''; lastLabelFrame = 0;
  fanAnimator?.dispose();
  fanAnimator = undefined;
  fanStates.value = [];
  fanUiSignature = '';
  lastFanFrame = 0;
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
}

function colorObject(object: Object3D, state: TwinVisualState, selected = false, critical = false) {
  object.traverse((child) => {
    if (!(child instanceof Mesh) || child.userData.fanRgb === true) return;
    const materials = Array.isArray(child.material) ? child.material : [child.material];
    materials.forEach((material) => {
      if (!(material instanceof MeshStandardMaterial)) return;
      const baseline = materialBaselines.get(material) ?? { color: material.color.clone(), emissive: material.emissive.clone() };
      materialBaselines.set(material, baseline);
      paintTwinMaterial(material, baseline, state, selected, critical);
    });
  });
}

function applyVisualState() {
  props.assets.forEach((asset) => {
    const object = assetObjects.get(asset.code);
    if (object) colorObject(object, resolveTwinVisualState(asset, props.alerts), props.selectedCode === asset.code, criticalAlarmCodes.value.has(asset.code));
  });
  syncAlarmEffects();
}

function syncAlarmEffects() {
  if (!scene) return;
  alarmEffects ??= createAlarmEffects(scene);
  const targets: AlarmTarget[] = [];
  const missing: string[] = [];
  for (const alarm of visualAlarms.value) {
    const object = modelBoundCodes.has(alarm.assetCode) ? assetObjects.get(alarm.assetCode) : undefined;
    if (object) targets.push({...alarm, object}); else missing.push(alarm.assetCode);
  }
  alarmEffects.sync(targets, sceneRadius);
  const placed = new Set(alarmEffects.anchors().map(anchor=>anchor.assetCode));
  missing.push(...targets.filter(target=>!placed.has(target.assetCode)).map(target=>target.assetCode));
  unplacedAlarmCodes.value = missing;
  if (!alarmEffects.size) { alarmLabels.value = []; labelSignature = ''; }
  if (host.value) host.value.dataset.alarmMarkedAssets = [...placed].join(',');
}

function projectAlarmLabels(timestamp: number) {
  if (!alarmEffects?.size || !camera || !host.value || timestamp-lastLabelFrame < 70) return;
  lastLabelFrame = timestamp;
  const width = host.value.clientWidth, height = host.value.clientHeight;
  const points: AlarmAnchor[] = [];
  for (const anchor of alarmEffects.anchors()) {
    const point = anchor.world.clone().project(camera);
    if (point.z < -1 || point.z > 1 || Math.abs(point.x)>1 || Math.abs(point.y)>1) continue;
    points.push({assetCode:anchor.assetCode,zone:anchor.zone,title:anchor.title,severity:anchor.severity,alertId:anchor.alertId,
      anchorX:Math.round((point.x+1)*width/2),anchorY:Math.round((1-point.y)*height/2)});
  }
  const labels = layoutAlarmLabels(points, width, height);
  const signature = JSON.stringify(labels);
  if (signature !== labelSignature) { alarmLabels.value = labels; labelSignature = signature; }
}

function focusAsset(code: string | null) {
  if (!code || !camera || !controls) return;
  const object = assetObjects.get(code);
  if (!object) return;
  const sphere = boundingSphere(object);
  const objectPosition = object.getWorldPosition(new Vector3());
  const target = sphere?.center ?? (isFiniteVector(objectPosition) ? objectPosition : controls.target.clone());
  const measuredRadius = sphere?.radius ?? sceneRadius * .025;
  // Some Blender exports place an equipment marker on a parent node that also
  // owns adjacent meshes.  Do not let that oversized parent bound turn an
  // equipment focus action into another whole-model view.
  const objectRadius = Math.max(Math.min(measuredRadius, sceneRadius * .12), sceneRadius * .006, .002);
  const alarmAnchor = alarmEffects?.anchors().find(anchor=>anchor.assetCode===code);
  const alarmDistance = alarmAnchor ? (alarmAnchor.world.distanceTo(target)+objectRadius)*2.8 : 0;
  const distance = Math.max(objectRadius * 3.25, sceneRadius * .018, .05, alarmDistance);
  controls.target.copy(target);
  controls.minDistance = Math.max(.002, sceneRadius * .0008);
  camera.position.copy(target.clone().add(overviewOffset(true).multiplyScalar(distance)));
  camera.near = Math.max(.0002, distance / 800);
  camera.updateProjectionMatrix();
  controls.update();
  publishCameraDistance();
}

function overviewOffset(focus = false) {
  const v = props.overviewDirection;
  return v?.length === 3 && v.every(Number.isFinite) && v.some(n => n !== 0)
    ? new Vector3(v[0], v[1], v[2]).normalize() : new Vector3(1, focus ? .72 : .68, 1).normalize();
}

function focusStation(stationId: string) {
  if (!/^P[1-5]$/.test(stationId) || !modelRoot || !camera || !controls) return;
  const group = modelRoot.getObjectByName(`STATION_${stationId}`);
  const sphere = group ? boundingSphere(group) : null;
  if (!sphere) return;
  const distance = Math.max(.05, cameraFitDistance(sphere.radius, camera.fov, camera.aspect) * 1.2);
  controls.target.copy(sphere.center);
  camera.position.copy(sphere.center.clone().add(overviewOffset().multiplyScalar(distance)));
  camera.near = Math.max(.0002, distance / 800);
  camera.updateProjectionMatrix(); controls.update(); publishCameraDistance();
}

function resetView() {
  if (!camera || !controls) return;
  const root = modelRoot || fallbackSceneRoot;
  const sphere = root ? boundingSphere(root) : null;
  if (sphere) {
    sceneRadius = Math.max(sphere.radius, .2);
    const distance = cameraFitDistance(sceneRadius, camera.fov, camera.aspect);
    controls.target.copy(sphere.center);
    camera.position.copy(sphere.center.clone().add(overviewOffset().multiplyScalar(distance)));
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
  // Picking used to occur on pointerdown. In rotation mode that meant merely
  // starting a drag could select a nearby device and reset the camera target.
  // Keep the candidate and commit it only if pointerup is a short click.
  if (code) pendingSelectionGesture = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    code,
  };
}

function onCanvasPointerUp(event: PointerEvent) {
  const selection = pendingSelectionGesture;
  if (selection?.pointerId === event.pointerId) {
    pendingSelectionGesture = undefined;
    if (Math.hypot(event.clientX - selection.startX, event.clientY - selection.startY) < 6) emit('select', selection.code);
  }
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

function cancelCanvasPan() {
  pendingPanGesture = undefined;
  pendingSelectionGesture = undefined;
}

function animate(timestamp = 0) {
  frame = window.requestAnimationFrame(animate);
  // Software WebGL, low-core industrial terminals and users who request less
  // motion should not spend the entire main-thread budget repainting a static
  // model. 30 FPS keeps camera gestures responsive while leaving enough time
  // for surrounding navigation and business controls.
  const minimumFrameInterval = performanceMode.value === 'reduced' ? 1000 / 30 : 0;
  if (minimumFrameInterval && timestamp - lastRenderedAt < minimumFrameInterval) return;
  lastRenderedAt = timestamp;
  if (fanAnimator) {
    const states = fanAnimator.update(props.fanFeedback || { telemetry: [], bindings: [], source: 'demo', offline: true },
      Date.now(), lastFanFrame ? (timestamp - lastFanFrame) / 1000 : 0);
    lastFanFrame = timestamp;
    const signature = JSON.stringify(states);
    if (signature !== fanUiSignature) { fanStates.value = states; fanUiSignature = signature; }
  }
  const now = reducedMotion.value ? 0 : performance.now() / 1000;
  props.assets.forEach((asset) => {
    const materials = animatedMaterials.get(asset.code);
    if (!materials?.length) return;
    const state = resolveTwinVisualState(asset, props.alerts);
    const critical = criticalAlarmCodes.value.has(asset.code);
    const intensity = visualIntensity(state, props.selectedCode === asset.code, critical, now);
    materials.forEach((material) => { material.emissiveIntensity = intensity; });
  });
  controls?.update();
  alarmEffects?.update(now, reducedMotion.value);
  projectAlarmLabels(timestamp);
  if (renderer && scene && camera) renderer.render(scene, camera);
}

function loadModel() {
  if (!scene) return;
  const loadToken = ++modelLoadToken;
  modelProgress.value = 0;
  modelState.value = 'loading';
  modelMessage.value = '正在加载实体三维模型…';
  window.clearTimeout(modelLoadTimeout);
  if (props.modelEnabled === false) {
    makeFallbackScene();
    publishModelReport('fallback');
    modelState.value = 'fallback';
    modelMessage.value = '当前启用模型文件不可用，已保护性切换到预览场景';
    applyVisualState();
    resetView();
    if (props.selectedCode) focusAsset(props.selectedCode);
    return;
  }
  modelLoadTimeout = window.setTimeout(() => {
    if (loadToken !== modelLoadToken) return;
    modelLoadToken += 1;
    makeFallbackScene();
    publishModelReport('fallback');
    modelState.value = 'fallback';
    modelMessage.value = '实体模型加载超时，已切换到安全预览，可重新检测';
    applyVisualState();
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
    fanAnimator = createFanAnimator(modelRoot);
    scene.add(modelRoot);
    sceneRadius = Math.max(boundingSphere(modelRoot)?.radius || .2, .2);
    publishModelReport('loaded', bindModelAssets(modelRoot));
    modelState.value = 'loaded';
    modelProgress.value = 100;
    modelMessage.value = '已加载实体三维模型';
    applyVisualState();
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
  scene.background = new Color(0xeaf0f8);
  scene.fog = new Fog(0xeaf0f8, 22, 55);
  camera = new PerspectiveCamera(48, 1, .1, 200);
  const navigatorCapabilities = navigator as Navigator & { deviceMemory?: number };
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  reducedMotion.value = prefersReducedMotion;
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
  scene.add(new HemisphereLight(0xf4f8ff, 0xb5c4d8, 2.1));
  const key = new DirectionalLight(0xffffff, 2.5);
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
watch(() => props.assets, () => { syncSceneAssets(); applyVisualState(); }, { deep: true });
watch(() => props.alerts, applyVisualState, { deep: true });
watch(() => props.selectedCode, (next, previous) => {
  applyVisualState();
  if (next && next !== previous) focusAsset(next);
});
watch(() => [props.modelUrl, props.modelEnabled], (next, previous) => {
  if (next[0] !== previous[0] || next[1] !== previous[1]) reloadModel();
});
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
  alarmEffects?.dispose(); alarmEffects = undefined;
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

defineExpose({ resetView, focusAsset, focusStation, zoomBy, setNavigationMode, reloadModel, modelState, modelMessage, modelProgress });
</script>

<template>
  <div class="twin-scene" :data-model-state="modelState">
    <div ref="host" class="twin-canvas" aria-label="综合管廊三维数字孪生场景" role="application" />
    <TwinAlarmOverlay :alarms="visualAlarms" :labels="alarmLabels" :unplaced-codes="unplacedAlarmCodes" @select="emit('select',$event)" />
    <div class="twin-model-state"><i :class="modelState" /><span>{{ modelMessage }}</span><em v-if="performanceMode === 'reduced'">流畅模式</em></div>
    <div v-if="fanStates.length" class="twin-fan-feedback" aria-label="独立风机反馈">
      <span v-for="fan in fanStates" :key="fan.assetCode" :title="fan.reason">
        {{ fan.assetCode }} · {{ fan.state === 'unknown' ? '反馈未知' : fan.state === 'stopped' ? '0 rpm · 已停止' : `${fan.measuredRpm} rpm` }}
        · {{ fan.lighting.state === 'on' ? '供电亮灯' : fan.lighting.state === 'off' ? '断电灭灯' : '灯光供电未知' }}
      </span><small>叶轮转速为示意，数值为反馈值</small>
    </div>
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
