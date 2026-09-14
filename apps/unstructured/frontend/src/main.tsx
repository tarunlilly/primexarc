import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import '@/app/globals.css'
import { getCachedUser, getCachedToken } from '@/lib/bouncer-auth'
import { initTelemetry } from '@/lib/telemetry'
import { initializeFaro, getWebInstrumentations } from '@grafana/faro-web-sdk'
import { TracingInstrumentation } from '@grafana/faro-web-tracing'

// Kick off session fetch immediately — before React renders — so the data is
// ready (or nearly ready) by the time components mount and call getCachedUser().
getCachedUser()
getCachedToken()

// Initialize Grafana Faro observability
const runtimeEnv = (window as any).__ENV__ ?? {}
const faroUrl = runtimeEnv.VITE_FARO_URL || import.meta.env.VITE_FARO_URL

if (faroUrl) {
  initializeFaro({
    url: faroUrl,
    app: {
      name: 'primedata-ui',
      version: runtimeEnv.APP_VERSION || '1.0.0',
      environment: runtimeEnv.ENVIRONMENT || import.meta.env.MODE,
    },
    sessionTracking: {
    enabled: true,
  },errorTracking: {
    enabled: true,
  },
    instrumentations: [
      ...getWebInstrumentations({
        captureConsole: true,
      }),
      new TracingInstrumentation(),
    ],
  })
}

// Initialize OpenTelemetry metrics
initTelemetry()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
