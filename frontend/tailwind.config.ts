import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        ops: { void: '#080c14', panel: '#0f1724', raised: '#172235', line: '#334155', ink: '#e5edf7', muted: '#8da0b8', signal: '#38bdf8', ok: '#10b981', warn: '#f59e0b', danger: '#ef4444' },
      },
      fontFamily: {
        sans: ['Inter', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['JetBrains Mono', 'Cascadia Mono', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config;
