// frontend/src/app/layout.tsx
// Root layout — wraps every page in the app.
// Add global CSS, fonts, and providers here (e.g., a QueryClient for React Query).

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
