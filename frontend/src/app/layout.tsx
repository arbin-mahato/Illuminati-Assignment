import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'QSR Insight Studio',
  description: 'Evidence-led agentic analytics for QSR operations.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
