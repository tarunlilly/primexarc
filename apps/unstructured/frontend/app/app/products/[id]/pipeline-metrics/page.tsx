
import { useState, useEffect } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ArrowLeft, TrendingUp, Clock, Database, Zap, BarChart3, ExternalLink } from 'lucide-react'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { formatEmbeddingModelName } from '@/lib/embedding-models'

interface Product {
  id: string
  workspace_id: string
  owner_user_id: string
  name: string
  status: 'draft' | 'running' | 'ready' | 'failed'
  current_version: number
  promoted_version?: number
  created_at: string
  updated_at?: string
}

interface PipelineRun {
  id: string
  product_id: string
  version: number
  status: 'succeeded' | 'failed' | 'running' | 'queued'
  started_at: string
  finished_at?: string
  dag_run_id?: string
  metrics: any
  created_at: string
}

// MLflow integration removed - metrics are now shown from pipeline run data

export default function PipelineMetricsPage() {
  const params = useParams()
  const navigate = useNavigate()
  const productId = params.id as string

  const [product, setProduct] = useState<Product | null>(null)
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRun[]>([])
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [selectedRun, setSelectedRun] = useState<PipelineRun | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadProduct()
    loadPipelineRuns()
  }, [productId])

  const loadProduct = async () => {
    try {
      const response = await apiClient.getProduct(productId)
      if (response.error) {
        console.error('Failed to load product:', response.error)
        return
      }
      setProduct(response.data as Product)
    } catch (err) {
      console.error('Error loading product:', err)
    }
  }

  const loadPipelineRuns = async () => {
    try {
      const response = await apiClient.getPipelineRuns(productId, 20)
      if (response.error) {
        console.error('Failed to load pipeline runs:', response.error)
        return
      }
      setPipelineRuns(response.data as PipelineRun[])
    } catch (err) {
      console.error('Error loading pipeline runs:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadVersionMetrics = (version: number) => {
    setSelectedVersion(version)
    const run = pipelineRuns.find(r => r.version === version)
    setSelectedRun(run || null)
  }

  const formatDuration = (seconds: number) => {
    if (seconds < 60) {
      return `${seconds.toFixed(1)}s`
    } else if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60)
      const remainingSeconds = seconds % 60
      return `${minutes}m ${remainingSeconds.toFixed(0)}s`
    } else {
      const hours = Math.floor(seconds / 3600)
      const minutes = Math.floor((seconds % 3600) / 60)
      return `${hours}h ${minutes}m`
    }
  }

  const formatEmbeddingModel = (modelName: string) => {
    if (!modelName || modelName === 'N/A') return 'N/A'
    return formatEmbeddingModelName(modelName)
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'succeeded':
      case 'finished':
        return 'bg-green-100 text-green-800'
      case 'failed':
        return 'bg-red-100 text-red-800'
      case 'partial_success':
        return 'bg-orange-100 text-orange-800'
      case 'running':
        return 'bg-[#F5E6E8] text-[#C8102E]'
      case 'queued':
        return 'bg-yellow-100 text-yellow-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6 flex items-center justify-center min-h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#C8102E] mx-auto mb-4"></div>
            <p className="text-gray-600">Loading pipeline metrics...</p>
          </div>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout>
      <div className="p-6 bg-gradient-to-br from-white via-white to-rose-100 min-h-screen">
        <div className="max-w-7xl mx-auto">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link to="/app/products" className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Products
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <Link to={`/app/products/${productId}`} className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            {product?.name}
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm text-gray-900 font-medium">Pipeline Metrics</span>
        </div>

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center">
              <div className="bg-[#C8102E] rounded-xl p-3 mr-4 shadow-lg">
                <BarChart3 className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900">Pipeline Metrics</h1>
                <p className="text-gray-600 mt-1">
                  Detailed metrics for each pipeline version of {product?.name}
                </p>
              </div>
            </div>
            {product?.promoted_version && (
              <div className="inline-flex items-center px-4 py-2 rounded-full text-sm font-bold bg-gradient-to-r from-purple-500 to-indigo-600 text-white shadow-md">
                🚀 Production Version: v{product.promoted_version}
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Pipeline Runs List */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl shadow-lg border-2 border-gray-100 p-6">
              <div className="mb-4">
                <h2 className="text-lg font-semibold text-gray-900 flex items-center space-x-2">
                  <BarChart3 className="h-5 w-5" />
                  <span>Pipeline Versions</span>
                </h2>
                <p className="text-sm text-gray-600 mt-1">
                  Select a version to view detailed metrics
                </p>
              </div>
              <div>
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {pipelineRuns.map((run) => (
                    <div
                      key={run.id}
                      className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                        selectedVersion === run.version
                          ? 'border-[#C8102E] bg-[#F5E6E8]'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                      onClick={() => loadVersionMetrics(run.version)}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          <span className="font-medium">v{run.version}</span>
                          {product?.promoted_version === run.version && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                              🚀 PROD
                            </span>
                          )}
                        </div>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(run.status)}`}>
                          {run.status}
                        </span>
                      </div>
                      <div className="text-sm text-gray-600">
                        <div>Started: {new Date(run.started_at).toLocaleString()}</div>
                        {run.finished_at && (
                          <div>Finished: {new Date(run.finished_at).toLocaleString()}</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Metrics Display */}
          <div className="lg:col-span-2">
            {!selectedVersion ? (
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-center h-64">
                  <div className="text-center">
                    <BarChart3 className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-gray-900 mb-2">
                      Select a Version
                    </h3>
                    <p className="text-gray-600">
                      Choose a pipeline version from the list to view detailed metrics
                    </p>
                  </div>
                </div>
              </div>
            ) : selectedRun ? (
              <div className="space-y-6">
                {/* Header */}
                <div className="bg-white rounded-xl shadow-lg border-2 border-gray-100 p-6">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 flex items-center space-x-2">
                      <TrendingUp className="h-5 w-5" />
                      <span>Version {selectedVersion} Pipeline Run</span>
                      {product?.promoted_version === selectedVersion && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                          🚀 PRODUCTION
                        </span>
                      )}
                    </h2>
                    <p className="text-sm text-gray-600 mt-1">
                      Pipeline run details for version {selectedVersion}
                    </p>
                  </div>
                </div>

                {/* Run Details */}
                <div className="bg-white rounded-xl shadow-lg border-2 border-gray-100 p-6">
                  <div className="mb-4">
                    <h3 className="text-lg font-semibold text-gray-900">Run Information</h3>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm font-medium text-gray-600">Run ID</p>
                      <p className="text-sm font-mono text-gray-900 break-all">
                        {selectedRun.id}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-600">Status</p>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(selectedRun.status)}`}>
                        {selectedRun.status}
                      </span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-600">Started At</p>
                      <p className="text-sm text-gray-900">
                        {new Date(selectedRun.started_at).toLocaleString()}
                      </p>
                    </div>
                    {selectedRun.finished_at && (
                      <div>
                        <p className="text-sm font-medium text-gray-600">Finished At</p>
                        <p className="text-sm text-gray-900">
                          {new Date(selectedRun.finished_at).toLocaleString()}
                        </p>
                      </div>
                    )}
                    {selectedRun.dag_run_id && (
                      <div>
                        <p className="text-sm font-medium text-gray-600">Airflow DAG Run ID</p>
                        <p className="text-sm font-mono text-gray-900 break-all">
                          {selectedRun.dag_run_id}
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Metrics (if available from pipeline run) */}
                {selectedRun.metrics && Object.keys(selectedRun.metrics).length > 0 && (
                  <div className="bg-white rounded-xl shadow-lg border-2 border-gray-100 p-6">
                    <div className="mb-4">
                      <h3 className="text-lg font-semibold text-gray-900">Run Metrics</h3>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {Object.entries(selectedRun.metrics).map(([key, value]) => (
                        <div key={key}>
                          <p className="text-sm font-medium text-gray-600 capitalize">
                            {key.replace(/_/g, ' ')}
                          </p>
                          <p className="text-lg font-semibold text-gray-900">
                            {typeof value === 'number' ? value.toLocaleString() : String(value)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-center h-64">
                  <div className="text-center">
                    <BarChart3 className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-gray-900 mb-2">
                      Select a Version
                    </h3>
                    <p className="text-gray-600">
                      Choose a pipeline version from the list to view run details
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
        </div>
      </div>
    </AppLayout>
  )
}
