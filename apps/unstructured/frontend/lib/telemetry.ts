import { MeterProvider, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics'
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http'
import { WebTracerProvider } from '@opentelemetry/sdk-trace-web'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base'
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch'
import { XMLHttpRequestInstrumentation } from '@opentelemetry/instrumentation-xml-http-request'
import { registerInstrumentations } from '@opentelemetry/instrumentation'
import { resourceFromAttributes } from '@opentelemetry/resources'
import { metrics, Histogram, Counter, UpDownCounter } from '@opentelemetry/api'

const METER_NAME = 'primedata-ui'

function getRuntimeEnv() {
  return (window as any).__ENV__ ?? {}
}

// Fix 1: Strip any accidental trailing /v1/metrics or /v1/traces from env var
// so VITE_OTEL_ENDPOINT should always be the base URL e.g. http://grafana-alloy.monitoring:4318
function normaliseBaseEndpoint(endpoint: string): string {
  return endpoint.replace(/\/v1\/(metrics|traces)\/?$/, '').replace(/\/$/, '')
}

function getOtelEndpoint(): string | null {
  const runtimeEnv = getRuntimeEnv()
  return runtimeEnv.VITE_OTEL_ENDPOINT || import.meta.env.VITE_OTEL_ENDPOINT || null
}

function getEnvironment(): string {
  const runtimeEnv = getRuntimeEnv()
  return runtimeEnv.ENVIRONMENT || import.meta.env.MODE || 'production'
}

function buildResource() {
  const runtimeEnv = getRuntimeEnv()
  return resourceFromAttributes({
    'service.name': 'primedata-ui',
    'service.version': runtimeEnv.APP_VERSION || '1.0.0',
    'deployment.environment': getEnvironment(),
  })
}

// ─── Metrics ────────────────────────────────────────────────────────────────

function initMetrics(baseEndpoint: string, resource: ReturnType<typeof buildResource>): void {
  const exporter = new OTLPMetricExporter({
    // Fix 1: always use the base endpoint and append /v1/metrics ourselves
    // CATS HTTP metrics endpoint: http://grafana-alloy.monitoring:4318
    url: `${baseEndpoint}/v1/metrics`,
    headers: {},
  })

  const meterProvider = new MeterProvider({
    resource,
    readers: [
      new PeriodicExportingMetricReader({
        exporter,
        exportIntervalMillis: 30_000, // export every 30 seconds
      }),
    ],
  })

  metrics.setGlobalMeterProvider(meterProvider)
}

// ─── Traces ─────────────────────────────────────────────────────────────────

// Fix 3: Add distributed tracing exporter to Alloy (port 4318 HTTP)
// Traces are routed by Alloy to Jaeger at jaeger-deployment-collector.logging
function initTracing(baseEndpoint: string, resource: ReturnType<typeof buildResource>): void {
  const traceExporter = new OTLPTraceExporter({
    // CATS HTTP traces endpoint: http://grafana-alloy.monitoring:4318
    url: `${baseEndpoint}/v1/traces`,
    headers: {},
  })

  const tracerProvider = new WebTracerProvider({
    resource,
    spanProcessors: [new BatchSpanProcessor(traceExporter)],
  })
  tracerProvider.register()

  // Auto-instrument fetch and XHR so every API call gets a trace span
  registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation({
        // Only trace calls to our own API, not third-party resources
        ignoreUrls: [/^(?!.*\/api\/v1\/).*$/],
        clearTimingResources: true,
      }),
      new XMLHttpRequestInstrumentation({
        ignoreUrls: [/^(?!.*\/api\/v1\/).*$/],
      }),
    ],
  })
}

// ─── Public init ────────────────────────────────────────────────────────────

export function initTelemetry(): void {
  const endpoint = getOtelEndpoint()
  if (!endpoint) return

  // Fix 1: sanitise the base URL before use
  const base = normaliseBaseEndpoint(endpoint)
  const resource = buildResource()

  initMetrics(base, resource)
  initTracing(base, resource)
}

// ─── Metric instruments (lazy-initialised) ──────────────────────────────────

let _apiRequestDuration: Histogram | null = null
let _apiRequestCount: Counter | null = null
let _apiErrorCount: Counter | null = null
let _activeRequests: UpDownCounter | null = null

function getMeter() {
  return metrics.getMeter(METER_NAME)
}

function apiRequestDuration(): Histogram {
  if (!_apiRequestDuration) {
    _apiRequestDuration = getMeter().createHistogram('api.request.duration', {
      description: 'Duration of API requests in milliseconds',
      unit: 'ms',
    })
  }
  return _apiRequestDuration
}

function apiRequestCount(): Counter {
  if (!_apiRequestCount) {
    _apiRequestCount = getMeter().createCounter('api.request.count', {
      description: 'Total number of API requests',
    })
  }
  return _apiRequestCount
}

function apiErrorCount(): Counter {
  if (!_apiErrorCount) {
    _apiErrorCount = getMeter().createCounter('api.error.count', {
      description: 'Total number of failed API requests',
    })
  }
  return _apiErrorCount
}

function activeRequests(): UpDownCounter {
  if (!_activeRequests) {
    _activeRequests = getMeter().createUpDownCounter('api.active_requests', {
      description: 'Number of in-flight API requests',
    })
  }
  return _activeRequests
}

// ─── Route normalisation ────────────────────────────────────────────────────

// Extracts a normalised route label from a full URL path
// e.g. "/api/v1/products/abc-123" → "/api/v1/products/{id}"
function normaliseRoute(path: string): string {
  return path
    .replace(/\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, '/{id}')
    .replace(/\/\d+/g, '/{id}')
    .split('?')[0]
}

// ─── Recording helpers (called from api-client.ts) ──────────────────────────

export interface RequestMetricAttributes {
  method: string
  path: string
  status: number
}

export function recordRequestStart(method: string, path: string): void {
  activeRequests().add(1, { method, route: normaliseRoute(path) })
}

export function recordRequestEnd({ method, path, status }: RequestMetricAttributes, durationMs: number): void {
  const route = normaliseRoute(path)
  const attrs = { method, route, status_code: String(status) }

  activeRequests().add(-1, { method, route })
  apiRequestDuration().record(durationMs, attrs)
  apiRequestCount().add(1, attrs)

  if (status >= 400) {
    apiErrorCount().add(1, { method, route, status_code: String(status) })
  }
}

export function recordNetworkError(method: string, path: string): void {
  const route = normaliseRoute(path)
  activeRequests().add(-1, { method, route })
  apiErrorCount().add(1, { method, route, status_code: 'network_error' })
}
