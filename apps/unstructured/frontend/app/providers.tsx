"use client"

import { ReactNode, useState, useEffect } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ToastProvider } from "@/components/ui/toast"
import { DefaultUserProvider } from "@/lib/default-user-context"
import { initializeAuth } from "@/lib/auth-utils"

interface ProvidersProps {
  children: ReactNode
}

export function Providers({ children }: ProvidersProps) {
  // Create a stable QueryClient instance
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // With SSR, we usually want to set some default staleTime
            // above 0 to avoid refetching immediately on the client
            staleTime: 30 * 1000, // 30 seconds - data is fresh for 30s
            gcTime: 5 * 60 * 1000, // 5 minutes - cache for 5 minutes
            refetchOnWindowFocus: false, // Don't refetch on window focus
            retry: 1, // Retry once on failure
          },
        },
      })
  )

  // Initialize default user authentication on mount
  useEffect(() => {
    initializeAuth()
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <DefaultUserProvider>
        <ToastProvider>
          {children}
        </ToastProvider>
      </DefaultUserProvider>
    </QueryClientProvider>
  )
}
