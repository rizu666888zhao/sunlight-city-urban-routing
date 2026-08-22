import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Sunlight City - Urban Comfort Analysis',
  description: 'Advanced platform for analyzing pedestrian and cycling route comfort in urban environments',
  icons: {
    icon: [
      { url: '/logo.png', sizes: '32x32' },
      { url: '/logo.png', sizes: '48x48' },
    ],
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-light text-dark`}>
        {children}
      </body>
    </html>
  )
}
