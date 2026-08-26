import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'UT / OPS — 综合管廊运维中枢',
  description: '综合管廊数字孪生运维平台演示界面',
  icons: { icon: '/favicon.svg' },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
