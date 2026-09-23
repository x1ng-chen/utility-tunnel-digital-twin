<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';

type TrailPoint = { x: number; y: number };

const finePointer = ref(false);
const pointerHost = ref<Element | string>('body');
const cursorNode = ref<HTMLElement>();
const trailNodes = ref<HTMLElement[]>([]);
const target = { x: -80, y: -80 };
const trail = Array.from({ length: 5 }, (): TrailPoint => ({ x: -80, y: -80 }));
let animationFrame = 0;
let visible = false;
let pointerQuery: MediaQueryList;

function syncPointerMode() {
  finePointer.value = pointerQuery.matches;
  document.body.classList.toggle('fx-enabled', finePointer.value);
  if (!finePointer.value) onPointerLeave();
}

function syncFullscreen() {
  pointerHost.value = document.fullscreenElement || 'body';
  onPointerLeave();
}

function interactiveTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) return null;
  return target.closest('button, a, input, select, textarea, [role="button"]');
}

function paintPointer() {
  const node = cursorNode.value;
  if (!node || !visible) { animationFrame = 0; return; }
  node.style.transform = `translate3d(${target.x}px, ${target.y}px, 0)`;
  let moving = false;
  trail.forEach((point, index) => {
    const leader = index === 0 ? target : trail[index - 1];
    const easing = Math.max(.24, .56 - index * .06);
    point.x += (leader.x - point.x) * easing;
    point.y += (leader.y - point.y) * easing;
    moving ||= Math.abs(leader.x - point.x) > .15 || Math.abs(leader.y - point.y) > .15;
    const scale = 1 - index * .12;
    trailNodes.value[index]?.style.setProperty('transform', `translate3d(${point.x - target.x}px, ${point.y - target.y}px, 0) scale(${scale})`);
  });
  animationFrame = moving ? window.requestAnimationFrame(paintPointer) : 0;
}

function onPointerMove(event: PointerEvent) {
  if (!finePointer.value || event.pointerType === 'touch') return;
  target.x = event.clientX;
  target.y = event.clientY;
  visible = true;
  // Keep the cursor itself synchronous; only the decorative trail eases.
  if (cursorNode.value) cursorNode.value.style.transform = `translate3d(${target.x}px, ${target.y}px, 0)`;
  cursorNode.value?.classList.add('active');
  document.documentElement.style.setProperty('--pointer-x', `${event.clientX}px`);
  document.documentElement.style.setProperty('--pointer-y', `${event.clientY}px`);
  document.body.dataset.pointerMode = interactiveTarget(event.target) ? 'interactive' : 'default';
  if (!animationFrame) animationFrame = window.requestAnimationFrame(paintPointer);
}

function onPointerDown(event: PointerEvent) {
  if (!finePointer.value) return;
  cursorNode.value?.classList.add('pressed');
  const target = interactiveTarget(event.target);
  if (!(target instanceof HTMLElement) || target.matches(':disabled')) return;
  const bounds = target.getBoundingClientRect();
  const ripple = document.createElement('span');
  ripple.className = 'interaction-ripple';
  ripple.setAttribute('aria-hidden', 'true');
  ripple.style.setProperty('--ripple-x', `${event.clientX - bounds.left}px`);
  ripple.style.setProperty('--ripple-y', `${event.clientY - bounds.top}px`);
  target.append(ripple);
  ripple.addEventListener('animationend', () => ripple.remove(), { once: true });
}

function onPointerUp() { cursorNode.value?.classList.remove('pressed'); }
function onPointerLeave() {
  visible = false;
  cursorNode.value?.classList.remove('active', 'pressed');
  document.body.dataset.pointerMode = 'default';
  if (animationFrame) window.cancelAnimationFrame(animationFrame);
  animationFrame = 0;
}

onMounted(() => {
  const runtime = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } };
  pointerQuery = window.matchMedia('(min-width: 721px) and (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)');
  syncPointerMode();
  pointerQuery.addEventListener('change', syncPointerMode);
  document.addEventListener('fullscreenchange', syncFullscreen);
  if ((runtime.deviceMemory || 8) < 6 || navigator.hardwareConcurrency < 6 || runtime.connection?.saveData || window.devicePixelRatio > 2) {
    document.body.classList.add('fx-lite');
  }
  window.addEventListener('pointermove', onPointerMove, { passive: true, capture: true });
  window.addEventListener('pointerdown', onPointerDown, { passive: true, capture: true });
  window.addEventListener('pointerup', onPointerUp, { passive: true, capture: true });
  window.addEventListener('pointercancel', onPointerLeave, true);
  window.addEventListener('blur', onPointerLeave);
  document.addEventListener('pointerleave', onPointerLeave);
});

onUnmounted(() => {
  document.body.classList.remove('fx-enabled');
  document.body.classList.remove('fx-lite');
  delete document.body.dataset.pointerMode;
  pointerQuery.removeEventListener('change', syncPointerMode);
  document.removeEventListener('fullscreenchange', syncFullscreen);
  window.removeEventListener('pointermove', onPointerMove, true);
  window.removeEventListener('pointerdown', onPointerDown, true);
  window.removeEventListener('pointerup', onPointerUp, true);
  window.removeEventListener('pointercancel', onPointerLeave, true);
  window.removeEventListener('blur', onPointerLeave);
  document.removeEventListener('pointerleave', onPointerLeave);
  if (animationFrame) window.cancelAnimationFrame(animationFrame);
});
</script>

<template>
  <div class="experience-backdrop" aria-hidden="true">
    <i class="backdrop-grid" />
    <i class="backdrop-sweep sweep-one" />
    <i class="backdrop-sweep sweep-two" />
    <i class="backdrop-noise" />
  </div>
  <Teleport :to="pointerHost"><div v-if="finePointer" ref="cursorNode" class="experience-cursor" aria-hidden="true">
    <i class="cursor-aura" />
    <i v-for="(_, index) in trail" :key="index" ref="trailNodes" class="cursor-trail" :style="{ opacity: .3 - index * .05 }" />
    <i class="cursor-ring" />
    <i class="cursor-dot" />
  </div></Teleport>
</template>
