<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import AppShell from '../components/AppShell.vue';
import { escapeMapText, hasValidLocation, integrationLabels, locationSourceLabels } from '../services/gis';
import { useOperationsStore } from '../stores/operations';
import type { Asset, HardwareBindingStatus, IntegrationStatus, SpatialFeature, SpatialLayerType } from '../types';
import '../assets/gis.css';

const store = useOperationsStore();
const mapElement = ref<HTMLElement | null>(null);
const selectedCode = ref('CTRL-01');
const search = ref('');
const zone = ref('all');
const integration = ref<'all' | IntegrationStatus>('all');
const spatialLayer = ref<'all' | SpatialLayerType>('all');
const tileStatus = ref<'loading' | 'ready' | 'degraded'>('loading');
let map: L.Map | null = null;
let markers: L.LayerGroup | null = null;
let featureLayers: L.LayerGroup | null = null;

const spatialLayerLabels: Record<SpatialLayerType, string> = { tunnel_segment: '管廊区段', chamber: '舱室', manhole: '井口', inspection_route: '巡检路线', risk_zone: '风险区域', installation_point: '安装点' };
const hardwareBindingLabels: Record<HardwareBindingStatus, string> = { reserved: '接口已预留', connected: '已接入', inactive: '未启用', error: '接入异常' };

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

function markerIcon(asset: Asset) {
  return L.divIcon({
    className: 'gis-marker-shell',
    html: `<div class="gis-marker ${asset.status} integration-${asset.integrationStatus}"><i></i><span>${escapeMapText(asset.hardwareCode ?? asset.code)}</span></div>`,
    iconSize: [58, 42],
    iconAnchor: [29, 34],
  });
}

function renderMarkers(fit = true) {
  if (!map || !markers) return;
  markers.clearLayers();
  const bounds: L.LatLngExpression[] = [];
  for (const asset of locatedAssets.value) {
    const point: L.LatLngExpression = [asset.latitude, asset.longitude];
    bounds.push(point);
    L.marker(point, { icon: markerIcon(asset), title: `${asset.hardwareCode ?? asset.code} ${asset.name}` })
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
      onEachFeature: (_, layer) => layer.bindTooltip(`${feature.name} · ${spatialLayerLabels[feature.layerType]}`, { sticky: true }),
    }).addTo(featureLayers);
  }
}

function selectAsset(asset: Asset) {
  selectedCode.value = asset.code;
  if (map && hasValidLocation(asset)) map.flyTo([asset.latitude, asset.longitude], Math.max(map.getZoom(), 18), { duration: 0.65 });
}

onMounted(async () => {
  await nextTick();
  if (!mapElement.value) return;
  map = L.map(mapElement.value, { zoomControl: false, minZoom: 2, maxZoom: 20 }).setView([31.2304, 121.4737], 18);
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
      <div><span class="eyebrow light">GOVERNED GEOGRAPHIC INFORMATION SYSTEM</span><h1>GIS 空间运维总览</h1><p>以受治理的 WGS84 坐标、审核空间图层和硬件绑定契约支撑现场地图；二维孪生仍由设备台账负责。</p></div>
      <div class="gis-live"><i />{{ connectedCount }} / {{ store.assets.length }} 固件链路已接入</div>
    </section>

    <section v-if="demoCoordinateCount" class="coordinate-notice" role="note">
      <span>坐标数据声明</span>
      <strong>{{ demoCoordinateCount }} 个模块当前使用演示锚点，不是 GPS 或现场测绘坐标。</strong>
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
        <div class="gis-legend"><span><i class="verified" />已验证</span><span><i class="connected" />固件已接入</span><span><i class="pending" />待验证</span><span><i class="spatial" />审核空间图层</span></div>
      </div>

      <aside v-if="selectedAsset" class="gis-inspector" aria-live="polite">
        <header><span>{{ selectedAsset.hardwareCode || 'NO HW ID' }}</span><b :class="`integration-${selectedAsset.integrationStatus}`">{{ integrationLabels[selectedAsset.integrationStatus] }}</b></header>
        <h2>{{ selectedAsset.name }}</h2><p>{{ selectedAsset.code }} · {{ selectedAsset.zone }}</p>
        <dl><div><dt>硬件接口</dt><dd>{{ selectedAsset.interface || '未配置' }}</dd></div><div><dt>坐标来源</dt><dd>{{ locationSourceLabels[selectedAsset.locationSource] }}</dd></div><div><dt>纬度</dt><dd>{{ selectedAsset.latitude?.toFixed(6) ?? '未配置' }}</dd></div><div><dt>经度</dt><dd>{{ selectedAsset.longitude?.toFixed(6) ?? '未配置' }}</dd></div></dl>
        <div class="gis-capabilities"><small>当前能力</small><span v-for="capability in selectedAsset.capabilities" :key="capability">{{ capability }}</span></div>
        <div class="gis-note"><small>实物状态说明</small><p>{{ selectedAsset.installationNote }}</p></div>
        <div class="gis-binding"><small>硬件接入契约</small><template v-if="selectedBinding"><p><b :class="selectedBinding.status">{{ hardwareBindingLabels[selectedBinding.status] }}</b>{{ selectedBinding.protocol.toUpperCase() }} · {{ selectedBinding.deviceIdentifier }}</p><code>{{ selectedBinding.endpoint }}</code><em>期望心跳 {{ selectedBinding.expectedIntervalSeconds }} 秒；未收到真实心跳前不显示在线。</em></template><p v-else>尚未预留通信绑定。</p></div>
      </aside>
    </section>

    <section class="gis-module-list" aria-label="全部实物模块">
      <button v-for="asset in filteredAssets" :key="asset.id" :class="{ active: selectedAsset?.code === asset.code }" @click="selectAsset(asset)">
        <i :class="asset.status" /><span><small>{{ asset.hardwareCode }} · {{ asset.zone }}</small><strong>{{ asset.name }}</strong><em>{{ integrationLabels[asset.integrationStatus] }}</em></span>
      </button>
    </section>

    <section class="spatial-feature-list" aria-label="已发布 GIS 空间对象">
      <header><span class="eyebrow">PUBLISHED SPATIAL LAYERS</span><h2>已审核空间对象</h2><p>仅显示已发布的 WGS84 GeoJSON；草稿与退役对象不会进入运维地图。</p></header>
      <div v-if="visibleSpatialFeatures.length" class="spatial-feature-grid"><article v-for="feature in visibleSpatialFeatures" :key="feature.id"><span>{{ spatialLayerLabels[feature.layerType] }}</span><strong>{{ feature.name }}</strong><small>{{ feature.code }} · {{ feature.source }} · 精度 {{ feature.accuracyM ?? '未登记' }} m</small></article></div>
      <div v-else class="empty-state">当前没有已审核发布的空间对象。管理员可通过 GIS 数据管理接口导入真实 GeoJSON 后发布。</div>
    </section>
  </AppShell>
</template>
