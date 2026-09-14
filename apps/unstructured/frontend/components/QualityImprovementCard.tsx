import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, Loader2, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { apiClient } from '@/lib/api-client'
import { ChunkQualityDrillDown } from './ChunkQualityDrillDown'

interface QualityData {
  product_id: string
  product_name: string
  version: number
  before: { overall: number; completeness: number; noise: number; structure: number }
  after: { overall: number; completeness: number; noise: number; structure: number }
  improvement: { overall: number; completeness: number; noise: number; structure: number }
  improvement_percentage: number
  has_improvement: boolean
  files_processed: number
  chunks_created: number
  baseline_available: boolean
  message?: string
  drill_down_available?: boolean
  low_quality_chunks?: number
  high_noise_chunks?: number
  mid_sentence_chunks?: number
}

interface QualityImprovementCardProps {
  productId: string
}

export function QualityImprovementCard({ productId }: QualityImprovementCardProps) {
  const [data, setData] = useState<QualityData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showDetails, setShowDetails] = useState(false)
  const [drillDownMetric, setDrillDownMetric] = useState<string | null>(null)

  const fetchQualityImprovement = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await apiClient.get(`/api/v1/products/${productId}/quality-improvement`)
      if (response.error) throw new Error(response.error || 'Failed to fetch quality improvement data')
      setData(response.data)
    } catch (err) {
      console.error('Error fetching quality improvement:', err)
      setError(err instanceof Error ? err.message : 'Failed to load quality data')
    } finally {
      setLoading(false)
    }
  }, [productId])

  useEffect(() => {
    fetchQualityImprovement()
  }, [fetchQualityImprovement])

  if (loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
        <div className="flex items-center justify-center py-4">
          <Loader2 className="h-5 w-5 text-gray-400 animate-spin mr-2" />
          <p className="text-sm text-gray-600">Loading quality data...</p>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <div className="flex items-start gap-2">
          <AlertCircle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Quality Assessment Unavailable</h3>
            <p className="text-xs text-gray-600 mt-1">{error || 'Unable to load quality improvement data.'}</p>
          </div>
        </div>
      </div>
    )
  }

  if (!data.baseline_available) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-start gap-2">
          <AlertCircle className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Quality Data Unavailable</h3>
            <p className="text-xs text-gray-600 mt-1">
              {data.message || 'Run the pipeline to generate quality metrics for this product.'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  const getImprovementColor = (value: number) => {
    if (value > 20) return 'text-green-700'
    if (value > 0) return 'text-green-600'
    if (value < -10) return 'text-red-600'
    return 'text-yellow-600'
  }

  return (
    <div className="bg-gradient-to-br from-green-50 via-emerald-50 to-teal-50 border border-green-200 rounded-lg shadow-sm">
      <div className="px-4 py-3 border-b border-green-200 bg-white/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-green-600" />
            <h3 className="text-base font-semibold text-gray-900">Data Quality Transformation</h3>
          </div>
          <div className={`text-sm font-bold ${getImprovementColor(data.improvement.overall)}`}>
            {data.improvement.overall > 0 ? '+' : ''}{Math.round(data.improvement.overall)} pts
          </div>
        </div>
      </div>

      <div className="p-4">
        <div className="grid grid-cols-3 gap-4 items-center mb-4">
          <div className="text-center bg-white/60 rounded-lg p-3 border border-red-200">
            <div className="flex items-center justify-center gap-1 mb-1">
              <span className="bg-red-100 text-red-700 text-[10px] font-bold px-2 py-0.5 rounded-full">Stage 0</span>
            </div>
            <p className="text-xs font-medium text-gray-600 mb-1">Baseline</p>
            <div className="text-3xl font-bold text-red-600">{Math.round(data.before.overall)}</div>
            <p className="text-xs text-gray-500 mt-1">Raw Data</p>
          </div>

          <div className="text-center">
            <div className="text-4xl font-bold text-green-600">→</div>
            <div className={`text-sm font-bold mt-1 ${getImprovementColor(data.improvement.overall)}`}>
              {data.improvement_percentage > 0 ? '+' : ''}{Math.round(data.improvement_percentage)}%
            </div>
          </div>

          <div className="text-center bg-white/60 rounded-lg p-3 border border-green-200">
            <div className="flex items-center justify-center gap-1 mb-1">
              <span className="bg-green-100 text-green-700 text-[10px] font-bold px-2 py-0.5 rounded-full">Pipeline Complete</span>
            </div>
            <p className="text-xs font-medium text-gray-600 mb-1">Transformed</p>
            <div className="text-3xl font-bold text-green-600">{Math.round(data.after.overall)}</div>
            <p className="text-xs text-gray-500 mt-1">AI-Ready</p>
          </div>
        </div>

        <button
          onClick={() => setShowDetails(!showDetails)}
          className="w-full flex items-center justify-between bg-white/60 hover:bg-white/80 transition-colors rounded-lg px-4 py-2 border border-green-200 text-sm font-medium text-gray-700"
        >
          <span>{showDetails ? 'Hide' : 'Show'} Detailed Breakdown</span>
          {showDetails ? <ChevronUp className="h-4 w-4 text-gray-500" /> : <ChevronDown className="h-4 w-4 text-gray-500" />}
        </button>

        {showDetails && (
          <div className="mt-3 space-y-2 bg-white/60 rounded-lg p-3 border border-green-200">
            <MetricRow
              label="Completeness"
              before={data.before.completeness}
              after={data.after.completeness}
              improvement={data.improvement.completeness}
              onDrillDown={() => setDrillDownMetric('completeness')}
              drillDownAvailable={data.drill_down_available}
            />
            <MetricRow
              label="Noise Reduction"
              before={data.before.noise}
              after={data.after.noise}
              improvement={data.improvement.noise}
              inverted
              onDrillDown={() => setDrillDownMetric('noise')}
              drillDownAvailable={data.drill_down_available}
            />
            <MetricRow
              label="Structure"
              before={data.before.structure}
              after={data.after.structure}
              improvement={data.improvement.structure}
              onDrillDown={() => setDrillDownMetric('structure')}
              drillDownAvailable={data.drill_down_available}
            />
          </div>
        )}

        <div className="mt-3 flex items-center justify-between text-xs text-gray-600 bg-white/40 rounded-lg px-3 py-2">
          <span>{data.files_processed} files processed</span>
          <span>•</span>
          <span>{data.chunks_created} chunks created</span>
        </div>
      </div>

      {drillDownMetric && (
        <ChunkQualityDrillDown
          productId={data.product_id}
          version={data.version}
          metric={drillDownMetric as 'noise' | 'completeness' | 'structure'}
          onClose={() => setDrillDownMetric(null)}
        />
      )}
    </div>
  )
}

interface MetricRowProps {
  label: string
  before: number
  after: number
  improvement: number
  inverted?: boolean
  onDrillDown?: () => void
  drillDownAvailable?: boolean
}

function MetricRow({ label, before, after, improvement, inverted = false, onDrillDown, drillDownAvailable }: MetricRowProps) {
  const displayChange = after - before
  const arrow = displayChange > 0 ? '⬆' : displayChange < 0 ? '⬇' : '→'
  const isImprovement = inverted ? displayChange < 0 : displayChange > 0
  const isRegression = inverted ? displayChange > 0 : displayChange < 0
  const color = isImprovement ? 'text-green-600' : isRegression ? 'text-red-600' : 'text-gray-600'

  return (
    <div className="flex items-center justify-between text-sm py-2 border-b border-gray-100 last:border-0">
      <span className="text-gray-700 font-medium">{label}:</span>
      <div className="flex items-center gap-3">
        <span className="text-gray-500">{Math.round(before)}%</span>
        <span className="text-gray-400">→</span>
        <span className="font-semibold">{Math.round(after)}%</span>
        <span className={`${color} font-bold min-w-[60px] text-right`}>
          ({displayChange > 0 ? '+' : ''}{Math.round(displayChange)}%) {arrow}
        </span>
        {drillDownAvailable && onDrillDown && (
          <button
            onClick={onDrillDown}
            className="ml-2 px-2 py-1 text-xs font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded transition-colors"
            title="View detailed breakdown"
          >
            View Details
          </button>
        )}
      </div>
    </div>
  )
}
