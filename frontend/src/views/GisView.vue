<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import AppShell from '../components/AppShell.vue';
import { escapeMapText, hasValidLocation, integrationLabels, locationSourceLabels } from '../services/gis';
import { primaryTwinAlert, resolveTwinVisualState, twinStateLabel } from '../services/twin3d';
import { useOperationsStore } from '../stores/operations';
import type { Asset, HardwareConnectivity, IntegrationStatus, SpatialFeature, SpatialLayerType, SpatialSource } from '../types';
import '../assets/gis.css';
import '../assets/operational-layout-polish.css';

const store = useOperationsStore();
const route = useRoute();
const router = useRouter();
const mapElement = ref<HTMLElement | null>(null);
const requestedCode = typeof route.query.asset === 'string' ? route.query.asset : '';
const selectedCode = ref(store.assets.some((asset) => asset.code === requestedCode) ? requestedCode : 'CTRL-01');
const search = ref('');
const zone = ref('all');
const integration = ref<'all' | IntegrationStatus>('all');
const spatialLayer = ref<'all' | SpatialLayerType>('all');
const tileStatus = ref<'loading' | 'ready' | 'degraded'>('loading');
let map: L.Map | null = null;
let markers: L.LayerGroup | null = null;
let featureLayers: L.LayerGroup | null = null;

const spatialLayerLabels: Record<SpatialLayerType, string> = { tunnel_segment: '管廊区段', chamber: '舱室', manhole: '井口', inspection_route: '巡检路线', risk_zone: '风险区域', installation_point: '安装点' };
const connectivityLabels: Record<HardwareConnectivity, string> = { online: '设备在线', offline: '心跳超时', awaiting_data: '等待首条数据', inactive: '接口未启用', error: '接入异常' };
const spatialSourceLabels: Record<SpatialSource, string> = { surveyed: '现场测绘', cad_import: '图纸整理', configured: '人工登记' };

const zones = computed(() => [...new Set(store.assets.map((asset) => asset.zone))].sort());
const filteredAssets = computed(() => {
  const keyword = search.value.trim().toLowerCase();
  return store.assets.filter((asset) => {
    const matchesText = !keyword || `${asset.hardwareCode} ${asset.code} ${asset.name} ${asset.interface}`.toLowerCase().includes(keyword);
    return matchesText && (zone.value === 'all' || asset.zone === zone.value) && (integration.value === 'all' || asset.integrationStatus === integration.value);
  });
});
const locatedAssets = computed(() => filteredAssets.value.filter(hasValidLocation));
const selectedAsset = computed(() => store.assets.find((asset) => asset.code === selectedCode.value) ?? filteredAssets.value[0] ?? null);
const demoCoordinateCount = computed(() => store.assets.filter((asset) => asset.locationSource === 'demo_anchor').length);
const governedCoordinateCount = computed(() => store.assets.filter((asset) => ['surveyed', 'gps', 'configured'].includes(asset.locationSource)).length);
const visibleSpatialFeatures = computed(() => store.spatialFeatures.filter((feature) => feature.status === 'published' && (spatialLayer.value === 'all' || feature.layerType === spatialLayer.value)));
const publishedFeatureCount = computed(() => store.spatialFeatures.filter((feature) => feature.status === 'published').length);
const verifiedCount = computed(() => store.assets.filter((asset) => asset.integrationStatus === 'verified').length);
const connectedCount = computed(() => store.assets.filter((asset) => ['verified', 'firmware_connected', 'calibration_required'].includes(asset.integrationStatus)).length);
const selectedBinding = computed(() => selectedAsset.value ? store.hardwareBindings.find((binding) => binding.assetCode === selectedAsset.value?.code) : null);
const selectedAlert = computed(() => selectedAsset.value ? primaryTwinAlert(selectedAsset.value.code, store.alerts) : null);
const navigationContext = computed(() => {
  const source = typeof route.query.source === 'string' ? route.query.source : '';
  if (source === 'twin') return '已从三维孪生定位到当前设备。';
  if (source === 'alert') return '已从告警中心定位到当前设备。';
  return '';
});

function markerIcon(asset: Asset) {
  return L.divIcon({
    className: 'gis-marker-shell',
    html: `<div class="gis-marker ${resolveTwinVisualState(asset, store.alerts)}"><i></i><span>${escapeMapText(asset.hardwareCode ?? asset.code)}</span></div>`,
    iconSize: [58, 42],
    iconAnchor: [29, 34],
  });
}

function renderMarkers(fit = true) {
  if (!map || !markers) return;
  markers.clearLayers();
  const bounds: L.LatLngExpression[] = [];
  const groups = new Map<string, Asset[]>();
  for (const asset of locatedAssets.value) {
    const point: L.LatLngExpression = [asset.latitude, asset.longitude];
    bounds.push(point);
    const key = `${asset.latitude.toFixed(6)},${asset.longitude.toFixed(6)}`;
    groups.set(key, [...(groups.get(key) ?? []), asset]);
  }
  for (const group of groups.values()) {
    const asset = group[0]!;
    const point: L.LatLngExpression = [asset.latitude!, asset.longitude!];
    const grouped = group.length > 1;
    const icon = grouped ? L.divIcon({
      className: 'gis-marker-shell',
      html: `<div class="gis-marker site"><i></i><span>${group.length} 个设备</span></div>`,
      iconSize: [58, 42],
      iconAnchor: [29, 34],
    }) : markerIcon(asset);
    L.marker(point, { icon, title: grouped ? `共 ${group.length} 个设备` : `${asset.hardwareCode ?? asset.code} ${asset.name}` })
      .on('click', () => { selectedCode.value = asset.code; })
      .addTo(markers);
  }
  if (fit && bounds.length && map) map.fitBounds(L.latLngBounds(bounds), { padding: [54, 54], maxZoom: 19 });
}

function featureStyle(feature: SpatialFeature): L.PathOptions {
  const palette: Record<SpatialLayerType, string> = { tunnel_segment: '#6d8cff', chamber: '#62d4b5', manhole: '#f5b45c', inspection_route: '#df7fd5', risk_zone: '#ef6e84', installation_point: '#82a5d7' };
  return { color: palette[feature.layerType], weight: feature.layerType === 'inspection_route' ? 3 : 4, opacity: .88, fillColor: palette[feature.layerType], fillOpacity: feature.layerType === 'risk_zone' ? .2 : .08, dashArray: feature.layerType === 'inspection_route' ? '8 6' : undefined };
}

function renderSpatialFeatures() {
  if (!featureLayers) return;
  featureLayers.clearLayers();
  for (const feature of visibleSpatialFeatures.value) {
    L.geoJSON(feature.geometry as never, {
      style: featureStyle(feature),
      pointToLayer: (_, latlng) => L.circleMarker(latlng, { ...featureStyle(feature), radius: 7, fillOpacity: .85 }),
      onEachFeature: (_, layer) => layer.bindTooltip(`${escapeMapText(feature.name)} · ${escapeMapText(spatialLayerLabels[feature.layerType])}`, { sticky: true }),
    }).addTo(featureLayers);
  }
}

function selectAsset(asset: Asset) {
  selectedCode.value = asset.code;
  if (map && hasValidLocation(asset)) map.flyTo([asset.latitude, asset.longitude], Math.max(map.getZoom(), 18), { duration: 0.65 });
}
function openTwin() { if (selectedAsset.value) void router.push({ path: '/twin-3d', query: { asset: selectedAsset.value.code, source: 'gis', ...(selectedAlert.value ? { alert: selectedAlert.value.code } : {}) } }); }
function openAlertCenter() { if (selectedAlert.value) void router.push({ path: '/alerts', query: { focus: selectedAlert.value.code, source: 'gis' } }); }

onMounted(async () => {
  await nextTick();
  if (!mapElement.value) return;
  map = L.map(mapElement.value, { zoomControl: false, minZoom: 2, maxZoom: 20 }).setView([36.635670, 109.472480], 18);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  const tileUrl = import.meta.env.VITE_GIS_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  L.tileLayer(tileUrl, {
    maxZoom: 20,
    attribution: import.meta.env.VITE_GIS_ATTRIBUTION || '&copy; OpenStreetMap contributors',
  }).on('load', () => { tileStatus.value = 'ready'; }).on('tileerror', () => { tileStatus.value = 'degraded'; }).addTo(map);
  markers = L.layerGroup().addTo(map);
  featureLayers = L.layerGroup().addTo(map);
  renderMarkers();
  renderSpatialFeatures();
});

watch(filteredAssets, () => {
  if (!filteredAssets.value.some((asset) => asset.code === selectedCode.value)) selectedCode.value = filteredAssets.value[0]?.code ?? '';
  renderMarkers();
});
watch(() => store.alerts, () => renderMarkers(false), { deep: true });

watch(() => route.query.asset, (code) => {
  if (typeof code !== 'string') return;
  const asset = store.assets.find((item) => item.code === code);
  if (asset) selectAsset(asset);
});

watch(visibleSpatialFeatures, renderSpatialFeatures);

onBeforeUnmount(() => {
  map?.remove();
  map = null;
  markers = null;
  featureLayers = null;
});
</script>

<template>
  <AppShell>
    <section class="section-title gis-title">
      <div><span class="eyebrow light">空间位置总览</span><h1>GIS 空间运维总览</h1><p>演示定位：陕西省延安市延安大学新城校区信息大厦 B 栋。以受治理的 WGS84 坐标、审核空间图层和硬件绑定契约支撑现场地图；二维孪生仍由设备台账负责。</p></div>
      <div class="gis-live"><i />{{ connectedCount }} / {{ store.assets.length }} 固件链路已接入</div>
    </section>

    <section v-if="demoCoordinateCount" class="coordinate-notice" role="note">
      <span>坐标数据声明</span>
      <strong>{{ demoCoordinateCount }} 个模块当前使用信息大厦附近的演示锚点，不是 B 栋内各设备的 GPS 或现场测绘坐标。</strong>
      <p>真实坐标和管廊图层必须经 GeoJSON 导入、来源登记和管理员审核后发布；系统不会把未审核数据展示为现场位置。</p>
    </section>

    <section class="gis-metrics">
      <article><small>受治理坐标</small><strong>{{ governedCoordinateCount }}</strong><span>测绘 / GPS / 已配置</span></article>
      <article><small>已发布图层</small><strong>{{ publishedFeatureCount }}</strong><span>GeoJSON 审核后发布</span></article>
      <article><small>固件已验证</small><strong>{{ verifiedCount }}</strong><span>主控 / TFT / DHT11</span></article>
      <article><small>硬件链路</small><strong>{{ connectedCount }}</strong><span>固件状态，不等同 GIS 坐标</span></article>
      <article><small>地图底图</small><strong>{{ tileStatus === 'ready' ? '在线' : tileStatus === 'degraded' ? '降级' : '连接中' }}</strong><span>标记层可独立工作</span></article>
    </section>

    <section class="gis-filters" aria-label="GIS 筛选条件">
      <input v-model="search" class="search-input" placeholder="搜索硬件编号、模块或接口" aria-label="搜索 GIS 模块" />
      <select v-model="zone" aria-label="按区域筛选"><option value="all">全部区域</option><option v-for="item in zones" :key="item" :value="item">{{ item }}</option></select>
      <select v-model="integration" aria-label="按接入状态筛选"><option value="all">全部接入状态</option><option v-for="(label, value) in integrationLabels" :key="value" :value="value">{{ label }}</option></select>
      <select v-model="spatialLayer" aria-label="按空间图层筛选"><option value="all">全部空间图层</option><option v-for="(label, value) in spatialLayerLabels" :key="value" :value="value">{{ label }}</option></select>
      <span>{{ locatedAssets.length }} 个资产点 · {{ visibleSpatialFeatures.length }} 个已发布空间对象</span>
    </section>

    <section class="gis-workspace">
      <div class="gis-map-panel">
        <div ref="mapElement" class="gis-map" aria-label="开发板模块 GIS 地图" />
        <div class="gis-legend"><span><i class="alarm" />告警</span><span><i class="connected" />关注</span><span><i class="verified" />正常</span><span><i class="pending" />待核验</span><span><i class="spatial" />审核空间图层</span></div>
      </div>

      <aside v-if="selectedAsset" class="gis-inspector" aria-live="polite">
        <p v-if="navigationContext" class="gis-navigation-context" role="status">{{ navigationContext }}</p>
        <header><span>{{ selectedAsset.hardwareCode || 'NO HW ID' }}</span><b :class="`integration-${selectedAsset.integrationStatus}`">{{ integrationLabels[selectedAsset.integrationStatus] }}</b></header>
        <h2>{{ selectedAsset.name }}</h2><p>{{ selectedAsset.code }} · {{ selectedAsset.zone }}</p>
        <dl><div><dt>硬件接口</dt><dd>{{ selectedAsset.interface || '未配置' }}</dd></div><div><dt>坐标来源</dt><dd>{{ locationSourceLabels[selectedAsset.locationSource] }}</dd></div><div><dt>纬度</dt><dd>{{ selectedAsset.latitude?.toFixed(6) ?? '未配置' }}</dd></div><div><dt>经度</dt><dd>{{ selectedAsset.longitude?.toFixed(6) ?? '未配置' }}</dd></div></dl>
        <div class="gis-capabilities"><small>当前能力</small><span v-for="capability in selectedAsset.capabilities" :key="capability">{{ capability }}</span></div>
        <div class="gis-note"><small>实物状态说明</small><p>{{ selectedAsset.installationNote }}</p></div>
        <div class="gis-binding"><small>设备数据连接</small><template v-if="selectedBinding"><p><b :class="selectedBinding.connectivity">{{ connectivityLabels[selectedBinding.connectivity] }}</b>{{ selectedBinding.protocol.toUpperCase() }} · {{ selectedBinding.deviceIdentifier }}</p><code>{{ selectedBinding.endpoint }}</code><em v-if="selectedBinding.connectivity === 'online'">最近心跳 {{ selectedBinding.heartbeatAgeSeconds }} 秒前，连接正常。</em><em v-else-if="selectedBinding.connectivity === 'offline'">设备超过 {{ selectedBinding.expectedIntervalSeconds * 3 }} 秒未上报，请检查供电与网络。</em><em v-else>期望每 {{ selectedBinding.expectedIntervalSeconds }} 秒上报；收到真实数据后才显示在线。</em></template><p v-else>尚未登记设备数据接口。</p></div>
        <div v-if="selectedAlert" class="gis-alert-summary"><small>当前异常</small><strong>{{ selectedAlert.title }}</strong><p>{{ selectedAlert.severity === 'critical' ? '严重告警' : '待处置告警' }} · {{ selectedAlert.code }}</p></div>
        <div class="gis-context-actions"><button class="gis-twin-link" @click="openTwin">在三维中查看此设备 →</button><button v-if="selectedAlert" class="gis-alert-link" @click="openAlertCenter">查看当前告警</button></div>
      </aside>
    </section>

    <section class="gis-module-list" aria-label="全部实物模块">
      <button v-for="asset in filteredAssets" :key="asset.id" :class="{ active: selectedAsset?.code === asset.code }" @click="selectAsset(asset)">
        <i :class="resolveTwinVisualState(asset, store.alerts)" /><span><small>{{ asset.hardwareCode }} · {{ asset.zone }}</small><strong>{{ asset.name }}</strong><em>{{ twinStateLabel(resolveTwinVisualState(asset, store.alerts)) }} · {{ integrationLabels[asset.integrationStatus] }}</em></span>
      </button>
    </section>

    <section class="spatial-feature-list" aria-label="已发布 GIS 空间对象">
      <header><span class="eyebrow">已发布空间图层</span><h2>已审核空间对象</h2><p>仅显示已发布的 WGS84 GeoJSON；草稿与退役对象不会进入运维地图。</p></header>
      <div v-if="visibleSpatialFeatures.length" class="spatial-feature-grid"><article v-for="feature in visibleSpatialFeatures" :key="feature.id"><span>{{ spatialLayerLabels[feature.layerType] }}</span><strong>{{ feature.name }}</strong><small>{{ feature.code }} · {{ spatialSourceLabels[feature.source] }} · {{ feature.accuracyM == null ? '精度未登记' : `精度 ${feature.accuracyM} 米` }}</small></article></div>
      <div v-else class="empty-state">当前没有已审核发布的空间对象。管理员可通过 GIS 数据管理接口导入真实 GeoJSON 后发布。</div>
    </section>
  </AppShell>
</template>

<style>
.gis-marker.alarm i {
  border-color: #ffd0d7;
  background: #ff4d61;
  box-shadow: 0 0 0 8px #ff4d6124, 0 0 25px #ff4d61;
}
.gis-marker.site i { border-color: #cce0ff; background: #6287ee; box-shadow: 0 0 0 8px #6287ee24, 0 0 25px #6287ee; }
.gis-module-list button > i.alarm, .gis-legend i.alarm { background: #ff4d61; }
</style>
