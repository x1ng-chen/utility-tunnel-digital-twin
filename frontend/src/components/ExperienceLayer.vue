<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue';

type TrailPoint = { x: number; y: number; opacity: number; scale: number };

const finePointer = ref(false);
const cursor = reactive({ x: -80, y: -80, active: false, pressed: false });
const trail = ref<TrailPoint[]>(Array.from({ length: 6 }, (_, index) => ({ x: -80, y: -80, opacity: 0.34 - index * 0.045, scale: 1 - index * 0.1 })));
let pendingPointer: PointerEvent | undefined;
let animationFrame = 0;

function interactiveTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) return null;
  return target.closest('button, a, input, select, textarea, [role="button"]');
}

function paintPointer() {
  animationFrame = 0;
  if (!pendingPointer) return;
  const event = pendingPointer;
  pendingPointer = undefined;
  cursor.x = event.clientX;
  cursor.y = event.clientY;
  cursor.active = true;
  document.documentElement.style.setProperty('--pointer-x', `${event.clientX}px`);
  document.documentElement.style.setProperty('--pointer-y', `${event.clientY}px`);
  document.body.dataset.pointerMode = interactiveTarget(event.target) ? 'interactive' : 'default';
  trail.value = trail.value.map((point, index, points) => {
    const leader = index === 0 ? { x: event.clientX, y: event.clientY } : points[index - 1];
    const easing = 0.78 - index * 0.055;
    return { ...point, x: point.x + (leader.x - point.x) * easing, y: point.y + (leader.y - point.y) * easing };
  });
}

function onPointerMove(event: PointerEvent) {
  if (!finePointer.value) return;
  pendingPointer = event;
  if (!animationFrame) animationFrame = window.requestAnimationFrame(paintPointer);
}

function onPointerDown(event: PointerEvent) {
  if (!finePointer.value) return;
  cursor.pressed = true;
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

function onPointerUp() { cursor.pressed = false; }
function onPointerLeave() { cursor.active = false; document.body.dataset.pointerMode = 'default'; }

onMounted(() => {
  finePointer.value = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  if (!finePointer.value) return;
  document.body.classList.add('fx-enabled');
  window.addEventListener('pointermove', onPointerMove, { passive: true });
  window.addEventListener('pointerdown', onPointerDown, { passive: true });
  window.addEventListener('pointerup', onPointerUp, { passive: true });
  document.addEventListener('pointerleave', onPointerLeave);
});

onUnmounted(() => {
  document.body.classList.remove('fx-enabled');
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
  <div v-if="finePointer" class="experience-cursor" :class="{ active: cursor.active, pressed: cursor.pressed }" :style="{ transform: `translate3d(${cursor.x}px, ${cursor.y}px, 0)` }" aria-hidden="true">
    <i v-for="(point, index) in trail" :key="index" class="cursor-trail" :style="{ transform: `translate3d(${point.x - cursor.x}px, ${point.y - cursor.y}px, 0) scale(${point.scale})`, opacity: point.opacity }" />
    <i class="cursor-ring" />
    <i class="cursor-dot" />
  </div>
</template>
