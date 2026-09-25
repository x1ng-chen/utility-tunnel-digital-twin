<script setup lang="ts">
import { ref } from 'vue';
import TwinScene from '../components/TwinScene.vue';
import type { Asset } from '../types';

const selected = ref<string | null>(null);
const scene = ref<InstanceType<typeof TwinScene>>();
const assets: Asset[] = ['ENV-01', 'GAS-01', 'FAN-01', 'DOOR-01'].map((code, id) => ({
  id, code, mesh: code, name: ['环境监测', '气体监测', '通风设备', '检修门'][id], zone: '演示区域', type: 'sensor',
  status: id === 1 ? 'alarm' : 'normal', hardwareCode: null, integrationStatus: 'pending_verification', interface: '', capabilities: [],
  position: { x: 25 + id * 15, y: 50 }, latitude: null, longitude: null, locationSource: 'demo_anchor', installationNote: '',
  lastSeenAt: null, isActive: true, version: 1,
}));
function select(code: string) { if (selected.value === code) scene.value?.focusAsset(code); selected.value = code; }
</script>
<template>
  <main>
    <header><div><small>UTILITY TUNNEL / SPATIAL STUDY</small><h1>管廊空间 · 交互预览</h1></div><p>本地效果样片 · 设备状态为演示数据</p></header>
    <section class="stage"><TwinScene ref="scene" :assets="assets" :alerts="[]" :selected-code="selected" @select="select" /></section>
    <nav aria-label="预览设备"><button @click="selected = null; scene?.resetView()">全景</button><button v-for="asset in assets" :key="asset.code" :class="{ selected: selected === asset.code }" @click="select(asset.code)">{{ asset.name }} <span>{{ asset.code }}</span></button></nav>
    <footer>选择设备体验镜头过渡；拖动或滚轮可随时接管。气体监测展示告警配色。</footer>
  </main>
</template>
<style>
*{box-sizing:border-box}body{margin:0;background:#060e18;color:#e3edf6;font-family:system-ui,sans-serif}main{max-width:1600px;margin:auto;padding:28px}header{display:flex;justify-content:space-between;align-items:center;gap:20px}small{font-size:10px;letter-spacing:3px;color:#68babd}h1{font-size:24px;font-weight:500;margin:10px 0 22px}header p,footer{font-size:12px;color:#93a7b8}.stage{border:1px solid #294653;border-radius:16px;overflow:hidden}.twin-scene{height:68vh;min-height:380px}nav{display:flex;gap:10px;margin:18px 0;flex-wrap:wrap}nav button{padding:12px 18px;border:1px solid #294653;background:#101e2b;border-radius:8px;color:#d7e6f1;cursor:pointer}nav button.selected{border-color:#61d8c9;background:#173338}nav span{margin-left:8px;font-size:10px;color:#91a8bb}.twin-camera-controls{position:absolute;left:16px;bottom:18px;display:flex;gap:6px}.twin-camera-controls button{width:34px;height:34px;background:#12263c;color:#c3dbe8;border:1px solid #385570;border-radius:6px}.twin-camera-controls svg{width:17px;height:17px}button:focus-visible{outline:2px solid #68ead6;outline-offset:3px}@media(max-width:700px){main{padding:14px}header{display:block}.twin-scene-tip{display:none}h1{font-size:20px}}
</style>
<style>
.stage .twin-camera-controls{top:auto;right:auto;left:16px;bottom:18px;width:auto;height:auto;padding:6px;flex-direction:row;transform:none}
</style>
