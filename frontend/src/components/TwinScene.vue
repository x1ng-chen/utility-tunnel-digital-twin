<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { BoxGeometry, Color, DirectionalLight, Fog, Group, HemisphereLight, Mesh, MeshBasicMaterial, MeshStandardMaterial, Object3D, PerspectiveCamera, PointLight, Raycaster, Scene, SphereGeometry, SRGBColorSpace, Vector2, Vector3, WebGLRenderer } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { Alert, Asset } from '../types';
import { modelNodeNames, primaryTwinAlert, resolveTwinVisualState, summarizeTwinModelBindings, twinModelUrl, type TwinModelBindingReport, type TwinVisualState } from '../services/twin3d';

const props = defineProps<{ assets: Asset[]; alerts: Alert[]; selectedCode: string | null }>();
const emit = defineEmits<{ select: [code: string]; modelReport: [report: TwinModelBindingReport] }>();
const host = ref<HTMLDivElement>();
const modelState = ref<'loading' | 'loaded' | 'fallback'>('loading');
const modelMessage = ref('正在加载三维模型…');
let scene: Scene | undefined;
let camera: PerspectiveCamera | undefined;
let renderer: WebGLRenderer | undefined;
let controls: OrbitControls | undefined;
let frame = 0;
let resizeObserver: ResizeObserver | undefined;
const raycaster = new Raycaster();
const pointer = new Vector2();
const assetObjects = new Map<string, Object3D>();
const animatedObjects = new Map<string, Object3D>();
const modelBoundCodes = new Set<string>();
const materialBaselines = new WeakMap<MeshStandardMaterial, { color: Color; emissive: Color }>();
let modelRoot: Object3D | undefined;
let fallbackSceneRoot: Group | undefined;
let fallbackAssetRoot: Group | undefined;
let modelLoadToken = 0;

const colors: Record<TwinVisualState, number> = { normal: 0x4ee7c3, warning: 0xffbb62, alarm: 0xff536f, unknown: 0x6d87aa };

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
  animatedObjects.set(asset.code, group);
}

function bindModelAssets(root: Object3D) {
  const boundCodes: string[] = [];
  props.assets.forEach((asset) => {
    if (modelBoundCodes.has(asset.code)) { boundCodes.push(asset.code); return; }
    const node = modelNodeNames(asset).map((name) => root.getObjectByName(name)).find(Boolean);
    if (!node) { addFallbackAsset(asset); return; }
    node.userData.assetCode = asset.code;
    node.traverse((child) => {
      child.userData.assetCode = asset.code;
      if (!(child instanceof Mesh)) return;
      child.material = Array.isArray(child.material) ? child.material.map((material) => material.clone()) : child.material.clone();
    });
    assetObjects.set(asset.code, node);
    animatedObjects.set(asset.code, node);
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
  modelRoot?.removeFromParent();
  fallbackSceneRoot?.removeFromParent();
  fallbackAssetRoot?.removeFromParent();
  modelRoot = undefined;
  fallbackSceneRoot = undefined;
  fallbackAssetRoot = undefined;
  modelBoundCodes.clear();
  assetObjects.clear();
  animatedObjects.clear();
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
  const target = new Vector3();
  object.getWorldPosition(target);
  controls.target.copy(target);
  camera.position.copy(target.clone().add(new Vector3(6, 4.5, 7.5)));
  controls.update();
}

function resetView() {
  if (!camera || !controls) return;
  camera.position.set(18, 13, 22);
  controls.target.set(0, 1.8, 0);
  controls.update();
}

function onCanvasPointerDown(event: PointerEvent) {
  if (!renderer || !camera) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects([...assetObjects.values()], true)[0];
  const code = hit?.object.userData.assetCode as string | undefined;
  if (code) emit('select', code);
}

function animate() {
  frame = window.requestAnimationFrame(animate);
  const now = performance.now() / 1000;
  props.assets.forEach((asset) => {
    const object = animatedObjects.get(asset.code);
    if (!object) return;
    const state = resolveTwinVisualState(asset, props.alerts);
    const critical = primaryTwinAlert(asset.code, props.alerts)?.severity === 'critical';
    object.traverse((child) => {
      if (!(child instanceof Mesh)) return;
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      materials.forEach((material) => {
        if (material instanceof MeshStandardMaterial) material.emissiveIntensity = visualIntensity(state, props.selectedCode === asset.code, critical, now);
      });
    });
  });
  controls?.update();
  if (renderer && scene && camera) renderer.render(scene, camera);
}

function loadModel() {
  if (!scene) return;
  const loadToken = ++modelLoadToken;
  new GLTFLoader().load(twinModelUrl, (gltf) => {
    if (loadToken !== modelLoadToken || !scene) return;
    modelRoot = gltf.scene;
    scene.add(modelRoot);
    publishModelReport('loaded', bindModelAssets(modelRoot));
    modelState.value = 'loaded';
    modelMessage.value = '已加载实体三维模型';
    applyVisualState();
  }, undefined, () => {
    if (loadToken !== modelLoadToken) return;
    makeFallbackScene();
    publishModelReport('fallback');
    modelState.value = 'fallback';
    modelMessage.value = '等待实体模型交付，当前为可交互预览场景';
    applyVisualState();
  });
}

function reloadModel() {
  if (!scene) return;
  clearLoadedModel();
  modelState.value = 'loading';
  modelMessage.value = '正在重新检测实体三维模型…';
  loadModel();
}

onMounted(() => {
  if (!host.value) return;
  scene = new Scene();
  scene.background = new Color(0x081628);
  scene.fog = new Fog(0x081628, 22, 55);
  camera = new PerspectiveCamera(48, 1, .1, 200);
  renderer = new WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  host.value.append(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = .06;
  controls.minDistance = 7;
  controls.maxDistance = 46;
  controls.maxPolarAngle = Math.PI * .48;
  resetView();
  scene.add(new HemisphereLight(0x8ba6ff, 0x071021, 2.1));
  const key = new DirectionalLight(0xb5d5ff, 2.5);
  key.position.set(10, 16, 10);
  scene.add(key);
  renderer.domElement.addEventListener('pointerdown', onCanvasPointerDown);
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

watch(() => [props.assets, props.alerts, props.selectedCode], () => { syncSceneAssets(); applyVisualState(); focusAsset(props.selectedCode); }, { deep: true });
onBeforeUnmount(() => {
  modelLoadToken += 1;
  window.cancelAnimationFrame(frame);
  resizeObserver?.disconnect();
  renderer?.domElement.removeEventListener('pointerdown', onCanvasPointerDown);
  controls?.dispose();
  renderer?.dispose();
  scene?.traverse((object) => {
    if (!(object instanceof Mesh)) return;
    object.geometry.dispose();
    (Array.isArray(object.material) ? object.material : [object.material]).forEach((material) => material.dispose());
  });
  assetObjects.clear();
  animatedObjects.clear();
  modelBoundCodes.clear();
});

defineExpose({ resetView, focusAsset, reloadModel, modelState, modelMessage });
</script>

<template>
  <div class="twin-scene" :data-model-state="modelState">
    <div ref="host" class="twin-canvas" aria-label="综合管廊三维数字孪生场景" role="application" />
    <div class="twin-model-state"><i :class="modelState" /><span>{{ modelMessage }}</span></div>
    <div class="twin-scene-tip">拖动旋转 · 滚轮缩放 · 点击设备查看详情</div>
  </div>
</template>
