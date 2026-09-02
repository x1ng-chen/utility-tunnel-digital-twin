<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';

type TrailPoint = { x: number; y: number };

const finePointer = ref(false);
const cursorNode = ref<HTMLElement>();
const trailNodes = ref<HTMLElement[]>([]);
const target = { x: -80, y: -80 };
const trail = Array.from({ length: 5 }, (): TrailPoint => ({ x: -80, y: -80 }));
let animationFrame = 0;
let visible = false;

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
  if (!finePointer.value) return;
  target.x = event.clientX;
  target.y = event.clientY;
  visible = true;
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
}

onMounted(() => {
  const runtime = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } };
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  finePointer.value = window.matchMedia('(hover: hover) and (pointer: fine)').matches && !reducedMotion;
  if ((runtime.deviceMemory || 8) < 6 || navigator.hardwareConcurrency < 6 || runtime.connection?.saveData || window.devicePixelRatio > 2) {
    document.body.classList.add('fx-lite');
  }
  if (!finePointer.value) return;
  document.body.classList.add('fx-enabled');
  window.addEventListener('pointermove', onPointerMove, { passive: true });
  window.addEventListener('pointerdown', onPointerDown, { passive: true });
  window.addEventListener('pointerup', onPointerUp, { passive: true });
  document.addEventListener('pointerleave', onPointerLeave);
});

onUnmounted(() => {
  document.body.classList.remove('fx-enabled');
  document.body.classList.remove('fx-lite');
  delete document.body.dataset.pointerMode;
  window.removeEventListener('pointermove', onPointerMove);
  window.removeEventListener('pointerdown', onPointerDown);
  window.removeEventListener('pointerup', onPointerUp);
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
  <div v-if="finePointer" ref="cursorNode" class="experience-cursor" aria-hidden="true">
    <i class="cursor-aura" />
    <i v-for="(_, index) in trail" :key="index" ref="trailNodes" class="cursor-trail" :style="{ opacity: .3 - index * .05 }" />
    <i class="cursor-ring" />
    <i class="cursor-dot" />
  </div>
</template>
