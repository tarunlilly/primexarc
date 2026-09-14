
import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, AlertCircle, Loader2, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import { apiClient, TrustMetricsResponse } from '@/lib/api-client'
import { useToast } from './ui/toast'

interface TrustMetricsDisplayProps {
  productId: string
  showTitle?: boolean
}

const METRIC_NAMES: Record<string, string> = {
  AI_Trust_Score: 'AI Trust Score',
  Completeness: 'Completeness',
  Accuracy: 'Accuracy',
  Secure: 'Security',
  Quality: 'Quality',
  Timeliness: 'Timeliness',
  Token_Count: 'Token Count',
  GPT_Confidence: 'GPT Confidence',
  Context_Quality: 'Context Quality',
  Metadata_Presence: 'Metadata Presence',
  Audience_Intentionality: 'Audience Intentionality',
  Diversity: 'Diversity',
  Audience_Accessibility: 'Audience Accessibility',
  KnowledgeBase_Ready: 'Knowledge Base Ready',
}

const METRIC_DESCRIPTIONS: Record<string, string> = {
  AI_Trust_Score: 'Overall AI readiness score (0-1)',
  Completeness: 'How complete the content is',
  Accuracy: 'Accuracy of the information',
  Secure: 'Security and privacy compliance',
  Quality: 'Overall content quality',
  Timeliness: 'How up-to-date the content is',
  Token_Count: 'Number of tokens in content',
  GPT_Confidence: 'GPT model confidence level',
  Context_Quality: 'Quality of context provided',
  Metadata_Presence: 'Presence of metadata',
  Audience_Intentionality: 'Content matches audience intent',
  Diversity: 'Content diversity',
  Audience_Accessibility: 'Accessibility for target audience',
  KnowledgeBase_Ready: 'Ready for knowledge base use',
}

export function TrustMetricsDisplay({ productId, showTitle = true }: TrustMetricsDisplayProps) {
  const [metrics, setMetrics] = useState<TrustMetricsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { addToast } = useToast()

  useEffect(() => {
    loadMetrics()
  }, [productId])

  const loadMetrics = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.getTrustMetrics(productId)
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to load trust metrics: ${response.error}`,
        })
      } else if (response.data) {
        setMetrics(response.data)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load trust metrics'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600 bg-green-50'
    if (score >= 0.6) return 'text-yellow-600 bg-yellow-50'
    return 'text-red-600 bg-red-50'
  }

  const getScoreIcon = (score: number) => {
    if (score >= 0.8) return <CheckCircle className="h-5 w-5 text-green-600" />
    if (score >= 0.6) return <AlertTriangle className="h-5 w-5 text-yellow-600" />
    return <XCircle className="h-5 w-5 text-red-600" />
  }

  const formatMetricValue = (key: string, value: number) => {
    // Token count: show as integer with separators (never as percentage)
    if (key === 'Token_Count') {
      return Math.round(value).toLocaleString()
    }

    // All other metrics are percentage-like (scores, quality, readiness, confidence, etc.)
    // Backend returns metrics in 0-100 scale, but some might be in 0-1 or >100
    // Normalize to 0-100 scale for display:
    let normalized = value
    
    // Handle different input scales
    if (normalized > 100) {
      // Values > 100: likely incorrectly scaled (e.g., 7500 means 75.0)
      // Divide by 100 to get back to 0-100 scale
      normalized = normalized / 100
    } else if (normalized <= 1 && normalized >= 0) {
      // Values 0-1: convert to percentage (multiply by 100)
      normalized = normalized * 100
    }
    // Values 1-100: use as-is (already in correct scale)
    
    // Ensure normalized is between 0-100
    normalized = Math.max(0, Math.min(100, normalized))
    
    return `${normalized.toFixed(2)}%`
  }

  // Helper to get normalized value for progress bar (0-1 scale)
  const getNormalizedValueForProgress = (key: string, value: number): number => {
    if (key === 'Token_Count') {
      // Token count: normalize to 0-1 based on reasonable max (e.g., 1000 tokens = 100%)
      return Math.min(value / 1000, 1.0)
    }
    
    // Normalize percentage metrics to 0-1 for progress bar
    // Same logic as formatMetricValue but return 0-1 scale
    let normalized = value
    if (normalized > 100) {
      // Values > 100: divide by 100
      normalized = normalized / 100
    } else if (normalized <= 1 && normalized >= 0) {
      // Values 0-1: multiply by 100 first, then divide by 100 for 0-1 scale
      normalized = normalized * 100
    }
    // Values 1-100: use as-is
    
    normalized = Math.max(0, Math.min(100, normalized))
    return normalized / 100  // Convert to 0-1 for progress bar
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">Trust Metrics</h2>}
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 text-gray-400 animate-spin mr-2" />
          <p className="text-gray-600">Loading trust metrics...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">Trust Metrics</h2>}
        <div className="flex items-center justify-center py-8">
          <AlertCircle className="h-6 w-6 text-red-500 mr-2" />
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    )
  }

  if (!metrics) {
    return null
  }

  const trustScore = metrics.ai_trust_score
  const otherMetrics = Object.entries(metrics.metrics || {})
    .filter(([key]) => key !== 'AI_Trust_Score')
    .sort(([a], [b]) => {
      // Sort by importance: put key metrics first
      const order = ['Secure', 'Metadata_Presence', 'KnowledgeBase_Ready', 'Quality', 'Completeness']
      const aIndex = order.indexOf(a)
      const bIndex = order.indexOf(b)
      if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex
      if (aIndex !== -1) return -1
      if (bIndex !== -1) return 1
      return a.localeCompare(b)
    })

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">AI Trust Metrics</h2>}
      
      {/* Overall Trust Score */}
      <div className="mb-6">
        <div className={`rounded-lg p-6 ${getScoreColor(trustScore)}`}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium mb-1">Overall AI Trust Score</p>
              <div className="flex items-baseline gap-2">
                <span className="text-4xl font-bold">{formatMetricValue('AI_Trust_Score', trustScore)}</span>
                <span className="text-sm opacity-75">/ 100%</span>
              </div>
              <p className="text-xs mt-2 opacity-75">
                {trustScore >= 0.8
                  ? 'Excellent - Ready for AI use'
                  : trustScore >= 0.6
                  ? 'Good - Minor improvements recommended'
                  : 'Needs Improvement - Significant enhancements required'}
              </p>
            </div>
            <div className="flex-shrink-0">{getScoreIcon(trustScore)}</div>
          </div>
        </div>
      </div>

      {/* Metrics Breakdown */}
      <div>
        <h3 className="text-sm font-medium text-gray-900 mb-3">Detailed Metrics</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {otherMetrics.map(([key, value]) => {
            const displayName = METRIC_NAMES[key] || key
            const description = METRIC_DESCRIPTIONS[key] || ''
            // Normalize value for color determination (0-1 scale)
            const normalizedForColor = (() => {
              if (key === 'Token_Count') return Math.min(value / 1000, 1.0)
              let n = value
              if (n <= 1 && n >= 0) n = n * 100
              else if (n > 100) n = n / 100
              n = Math.max(0, Math.min(100, n))
              return n / 100
            })()
            const scoreColor = normalizedForColor >= 0.8 ? 'text-green-600' : normalizedForColor >= 0.6 ? 'text-yellow-600' : 'text-red-600'
            
            return (
              <div key={key} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1">
                    <h4 className="text-sm font-medium text-gray-900">{displayName}</h4>
                    {description && (
                      <p className="text-xs text-gray-500 mt-1">{description}</p>
                    )}
                  </div>
                  <div className={`text-lg font-semibold ${scoreColor} ml-2`}>
                    {formatMetricValue(key, value)}
                  </div>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${
                      (() => {
                        const normalized = getNormalizedValueForProgress(key, value)
                        return normalized >= 0.8 ? 'bg-green-500' : normalized >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                      })()
                    }`}
                    style={{ width: `${Math.min(getNormalizedValueForProgress(key, value) * 100, 100)}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Chunk Count */}
      {metrics.chunk_count > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <p className="text-sm text-gray-600">
            Metrics calculated from <span className="font-medium">{metrics.chunk_count.toLocaleString()}</span> chunks
          </p>
        </div>
      )}
    </div>
  )
}




