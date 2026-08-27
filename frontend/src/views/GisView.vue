<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import AppShell from '../components/AppShell.vue';
import { escapeMapText, hasValidLocation, integrationLabels, locationSourceLabels } from '../services/gis';
import { useOperationsStore } from '../stores/operations';
import type { Asset, IntegrationStatus } from '../types';
import '../assets/gis.css';

const store = useOperationsStore();
const mapElement = ref<HTMLElement | null>(null);
const selectedCode = ref('CTRL-01');
const search = ref('');
const zone = ref('all');
const integration = ref<'all' | IntegrationStatus>('all');
const tileStatus = ref<'loading' | 'ready' | 'degraded'>('loading');
let map: L.Map | null = null;
let markers: L.LayerGroup | null = null;

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
const verifiedCount = computed(() => store.assets.filter((asset) => asset.integrationStatus === 'verified').length);
const connectedCount = computed(() => store.assets.filter((asset) => ['verified', 'firmware_connected', 'calibration_required'].includes(asset.integrationStatus)).length);

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

function selectAsset(asset: Asset) {
  selectedCode.value = asset.code;
  if (map && hasValidLocation(asset)) map.flyTo([asset.latitude, asset.longitude], Math.max(map.getZoom(), 18), { duration: 0.65 });
}

onMounted(async () => {
  await nextTick();
  if (!mapElement.value) return;
  map = L.map(mapElement.value, { zoomControl: false, minZoom: 2, maxZoom: 20 }).setView([31.2304, 121.4737], 18);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  const tileUrl = import.meta.env.VITE_GIS_TILE_URL || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
  L.tileLayer(tileUrl, {
    maxZoom: 20,
    attribution: import.meta.env.VITE_GIS_ATTRIBUTION || '&copy; OpenStreetMap contributors',
  }).on('load', () => { tileStatus.value = 'ready'; }).on('tileerror', () => { tileStatus.value = 'degraded'; }).addTo(map);
  markers = L.layerGroup().addTo(map);
  renderMarkers();
});

watch(filteredAssets, () => {
  if (!filteredAssets.value.some((asset) => asset.code === selectedCode.value)) selectedCode.value = filteredAssets.value[0]?.code ?? '';
  renderMarkers();
});

onBeforeUnmount(() => {
  map?.remove();
  map = null;
  markers = null;
});
</script>

<template>
  <AppShell>
    <section class="section-title gis-title">
      <div><span class="eyebrow light">GEOGRAPHIC INFORMATION SYSTEM</span><h1>GIS 设备位置总览</h1><p>以 WGS84 坐标聚合实物开发板模块；管廊内部相对位置仍由“设备台账”孪生视图负责。</p></div>
      <div class="gis-live"><i />{{ connectedCount }} / {{ store.assets.length }} 固件链路已接入</div>
    </section>

    <section v-if="demoCoordinateCount" class="coordinate-notice" role="note">
      <span>坐标数据声明</span>
      <strong>{{ demoCoordinateCount }} 个模块当前使用演示锚点，不是 GPS 或现场测绘坐标。</strong>
      <p>获得现场经纬度后可通过资产数据更新，GIS 会自动切换并保留坐标来源。</p>
    </section>

    <section class="gis-metrics">
      <article><small>实物模块</small><strong>{{ store.assets.length }}</strong><span>计划书 V2.7 交付清单</span></article>
      <article><small>固件已验证</small><strong>{{ verifiedCount }}</strong><span>主控 / TFT / DHT11</span></article>
      <article><small>已接入链路</small><strong>{{ connectedCount }}</strong><span>含待标定与待实测</span></article>
      <article><small>地图底图</small><strong>{{ tileStatus === 'ready' ? '在线' : tileStatus === 'degraded' ? '降级' : '连接中' }}</strong><span>标记层可独立工作</span></article>
    </section>

    <section class="gis-filters" aria-label="GIS 筛选条件">
      <input v-model="search" class="search-input" placeholder="搜索硬件编号、模块或接口" aria-label="搜索 GIS 模块" />
      <select v-model="zone" aria-label="按区域筛选"><option value="all">全部区域</option><option v-for="item in zones" :key="item" :value="item">{{ item }}</option></select>
      <select v-model="integration" aria-label="按接入状态筛选"><option value="all">全部接入状态</option><option v-for="(label, value) in integrationLabels" :key="value" :value="value">{{ label }}</option></select>
      <span>{{ locatedAssets.length }} 个地图标记</span>
    </section>

    <section class="gis-workspace">
      <div class="gis-map-panel">
        <div ref="mapElement" class="gis-map" aria-label="开发板模块 GIS 地图" />
        <div class="gis-legend"><span><i class="verified" />已验证</span><span><i class="connected" />固件已接入</span><span><i class="pending" />待验证</span></div>
      </div>

      <aside v-if="selectedAsset" class="gis-inspector" aria-live="polite">
        <header><span>{{ selectedAsset.hardwareCode || 'NO HW ID' }}</span><b :class="`integration-${selectedAsset.integrationStatus}`">{{ integrationLabels[selectedAsset.integrationStatus] }}</b></header>
        <h2>{{ selectedAsset.name }}</h2><p>{{ selectedAsset.code }} · {{ selectedAsset.zone }}</p>
        <dl><div><dt>硬件接口</dt><dd>{{ selectedAsset.interface || '未配置' }}</dd></div><div><dt>坐标来源</dt><dd>{{ locationSourceLabels[selectedAsset.locationSource] }}</dd></div><div><dt>纬度</dt><dd>{{ selectedAsset.latitude?.toFixed(6) ?? '未配置' }}</dd></div><div><dt>经度</dt><dd>{{ selectedAsset.longitude?.toFixed(6) ?? '未配置' }}</dd></div></dl>
        <div class="gis-capabilities"><small>当前能力</small><span v-for="capability in selectedAsset.capabilities" :key="capability">{{ capability }}</span></div>
        <div class="gis-note"><small>实物状态说明</small><p>{{ selectedAsset.installationNote }}</p></div>
      </aside>
    </section>

    <section class="gis-module-list" aria-label="全部实物模块">
      <button v-for="asset in filteredAssets" :key="asset.id" :class="{ active: selectedAsset?.code === asset.code }" @click="selectAsset(asset)">
        <i :class="asset.status" /><span><small>{{ asset.hardwareCode }} · {{ asset.zone }}</small><strong>{{ asset.name }}</strong><em>{{ integrationLabels[asset.integrationStatus] }}</em></span>
      </button>
    </section>
  </AppShell>
</template>
