import React, { useEffect, useState } from 'react'
import { CheckCircle, AlertCircle, Info } from 'lucide-react'
import { apiClient } from '@/lib/api-client'

interface DiffChange {
  type: 'removed' | 'added' | 'modified'
  text: string
  reason: string
  line_number: number
}

interface TransformationDetails {
  description: string
  chars_removed: number
  pattern: string
}

interface DiffMetrics {
  chars_before: number
  chars_after: number
  chars_removed: number
  changes_count: number
  lines_before: number
  lines_after: number
}

interface DiffData {
  before: string
  after: string
  changes: DiffChange[]
  transformation_log: Record<string, TransformationDetails>
  metrics: DiffMetrics
  has_raw_text: boolean
  message?: string
  chunk_id: string
}

interface DetailedDiffViewProps {
  chunkId: string
  productId: string
  version: number
}

export function DetailedDiffView({ chunkId, productId, version }: DetailedDiffViewProps) {
  const [diffData, setDiffData] = useState<DiffData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchDiff = async () => {
      try {
        setLoading(true)
        setError(null)
        const response = await apiClient.get(
          `/api/v1/products/${productId}/versions/${version}/chunks/${chunkId}/diff`
        )
        setDiffData(response.data)
      } catch (err: any) {
        console.error('Failed to fetch diff:', err)
        setError(err.response?.data?.detail || 'Failed to load diff data')
      } finally {
        setLoading(false)
      }
    }
    fetchDiff()
  }, [chunkId, productId, version])

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-600">Loading detailed diff...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex items-center">
          <AlertCircle className="h-5 w-5 text-red-500 mr-2" />
          <span className="text-red-700">{error}</span>
        </div>
      </div>
    )
  }

  if (!diffData) {
    return null
  }

  const isMinimalTransformation = diffData.metrics.chars_removed < 10
  const hasTransformations = Object.keys(diffData.transformation_log).length > 0

  return (
    <div className="space-y-4">
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h4 className="font-semibold text-blue-900 mb-3 flex items-center">
          <Info className="h-5 w-5 mr-2" />
          Transformation Summary
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-gray-600">Characters Before</div>
            <div className="font-semibold text-gray-900">{diffData.metrics.chars_before.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-gray-600">Characters After</div>
            <div className="font-semibold text-gray-900">{diffData.metrics.chars_after.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-gray-600">Characters Removed</div>
            <div className="font-semibold text-red-600">{diffData.metrics.chars_removed.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-gray-600">Changes Made</div>
            <div className="font-semibold text-blue-600">{diffData.metrics.changes_count}</div>
          </div>
        </div>
      </div>

      {isMinimalTransformation && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-center">
            <CheckCircle className="h-5 w-5 text-green-600 mr-2 flex-shrink-0" />
            <div>
              <div className="font-semibold text-green-900">Document Already Well-Formatted</div>
              <div className="text-sm text-green-700 mt-1">
                This document required minimal preprocessing ({diffData.metrics.chars_removed} characters removed).
                The pipeline preserved the original quality.
              </div>
            </div>
          </div>
        </div>
      )}

      {hasTransformations && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <h4 className="font-semibold text-yellow-900 mb-3">Transformations Applied</h4>
          <div className="space-y-2">
            {Object.entries(diffData.transformation_log).map(([name, details]) => (
              <div key={name} className="text-sm border-l-2 border-yellow-400 pl-3">
                <div className="font-medium text-yellow-900">{name}</div>
                <div className="text-yellow-700">{details.description}</div>
                {details.chars_removed > 0 && (
                  <div className="text-xs text-yellow-600 mt-1">
                    Removed {details.chars_removed} characters
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!hasTransformations && !diffData.message && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-600">
            No specific normalizer transformations were applied to this chunk's page.
          </div>
        </div>
      )}

      {diffData.message && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-600">{diffData.message}</div>
        </div>
      )}

      {diffData.changes.length > 0 && (
        <div className="border border-gray-300 rounded-lg overflow-hidden">
          <div className="bg-gray-100 px-4 py-2 border-b border-gray-300">
            <h4 className="font-semibold text-gray-900">Line-by-Line Changes</h4>
            <p className="text-xs text-gray-600 mt-1">Red lines were removed, green lines were added or reformatted</p>
          </div>
          <div className="bg-white max-h-96 overflow-y-auto">
            <div className="font-mono text-xs">
              {diffData.changes.map((change, idx) => (
                <div
                  key={idx}
                  className={`px-4 py-1 border-b border-gray-100 ${
                    change.type === 'removed'
                      ? 'bg-red-50 border-l-4 border-l-red-400'
                      : 'bg-green-50 border-l-4 border-l-green-400'
                  }`}
                >
                  <div className="flex items-start">
                    <span className={`font-bold mr-2 ${change.type === 'removed' ? 'text-red-600' : 'text-green-600'}`}>
                      {change.type === 'removed' ? '-' : '+'}
                    </span>
                    <div className="flex-1">
                      <div className="whitespace-pre-wrap break-words">{change.text || '(empty line)'}</div>
                      <div className={`text-xs mt-1 ${change.type === 'removed' ? 'text-red-600' : 'text-green-600'}`}>
                        {change.reason}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {diffData.changes.length === 0 && diffData.has_raw_text && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-600">
            No line-level changes detected. The raw and processed texts are identical or differ only in whitespace.
          </div>
        </div>
      )}
    </div>
  )
}
