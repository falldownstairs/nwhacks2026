import { Inter } from 'next/font/google';
import './globals.css';
import Navigation from '@/components/Navigation';
import ErrorBoundary from '@/components/ErrorBoundary';

const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title: 'Chronic Disease Coach',
  description: 'AI-Powered Early Warning System for Heart Failure',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-900 text-white antialiased`}>
        <ErrorBoundary>
          <Navigation />
          <main className="max-w-7xl mx-auto px-4 py-6 min-h-[calc(100vh-64px)]">
            {children}
          </main>
        </ErrorBoundary>
      </body>
    </html>
  );
}
