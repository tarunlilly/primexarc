import { useEffect, useState } from 'react'
import { Loader2, Database, Hash, Layers, TrendingUp } from 'lucide-react'
import { apiClient } from '@/lib/api-client'

interface VectorRecord {
  id: string
  content_preview: string
  vector_sample: number[]
  vector_dimension: number
  magnitude: number
}

interface VectorViewerProps {
  artifact_id: string
  storage_key: string
  collection_name?: string
  max_vectors?: number
}

export function VectorViewer({ artifact_id, storage_key, collection_name, max_vectors = 5 }: VectorViewerProps) {
  const [vectors, setVectors] = useState<VectorRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [collectionInfo, setCollectionInfo] = useState<any>(null)

  useEffect(() => {
    fetchVectorPreview()
  }, [artifact_id])

  const fetchVectorPreview = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await apiClient.getArtifactVectorPreview(artifact_id, max_vectors)
      if (response.error) throw new Error(response.error)
      setVectors(response.data.embeddings || [])
      setCollectionInfo(response.data.statistics)
    } catch (err) {
      console.error('Error fetching vector preview:', err)
      setError(err instanceof Error ? err.message : 'Failed to load vector preview')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        <span className="ml-2 text-sm text-gray-500">Loading vector preview...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-sm text-red-700">{error}</p>
      </div>
    )
  }

  if (vectors.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <p className="text-sm text-gray-600">No vectors available in this artifact.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center">
          <Database className="h-4 w-4 mr-2 text-purple-500" />
          Vector Store Preview
        </h3>
        <span className="text-xs text-gray-500">
          Showing {vectors.length} vector{vectors.length !== 1 ? 's' : ''}
        </span>
      </div>

      {collectionInfo && (
        <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="font-semibold text-purple-900">Dimension:</span>
              <span className="ml-1 text-purple-700">{collectionInfo.dimension}</span>
            </div>
            <div>
              <span className="font-semibold text-purple-900">Avg Magnitude:</span>
              <span className="ml-1 text-purple-700">{collectionInfo.avg_magnitude?.toFixed(4)}</span>
            </div>
            {collectionInfo.vector_range && (
              <>
                <div>
                  <span className="font-semibold text-purple-900">Range Min:</span>
                  <span className="ml-1 text-purple-700">{collectionInfo.vector_range.min?.toFixed(4)}</span>
                </div>
                <div>
                  <span className="font-semibold text-purple-900">Range Max:</span>
                  <span className="ml-1 text-purple-700">{collectionInfo.vector_range.max?.toFixed(4)}</span>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <div className="space-y-3">
        {vectors.map((vector, idx) => (
          <div key={idx} className="border border-gray-200 rounded-lg bg-white hover:shadow-md transition-shadow">
            <div className="bg-purple-50 border-b border-purple-200 px-4 py-2 flex items-center justify-between">
              <span className="text-xs font-mono text-purple-600 flex items-center">
                <Hash className="h-3 w-3 mr-1" />
                {vector.id}
              </span>
              <div className="flex items-center space-x-2">
                <span className="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded">
                  {vector.vector_dimension}D
                </span>
                {vector.magnitude !== undefined && (
                  <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded flex items-center">
                    <TrendingUp className="h-3 w-3 mr-1" />
                    magnitude: {vector.magnitude.toFixed(4)}
                  </span>
                )}
              </div>
            </div>
            <div className="p-4 space-y-3">
              <div className="flex items-start">
                <Layers className="h-4 w-4 text-gray-400 mr-2 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <div className="text-xs font-semibold text-gray-500">Content Preview</div>
                  <div className="text-sm text-gray-900 mt-0.5">{vector.content_preview}</div>
                </div>
              </div>
              {vector.vector_sample && vector.vector_sample.length > 0 && (
                <div className="flex items-start">
                  <Database className="h-4 w-4 text-gray-400 mr-2 mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <div className="text-xs font-semibold text-gray-500">Vector Sample (first 5 dims)</div>
                    <div className="text-xs text-gray-700 font-mono mt-0.5 break-all">
                      [{vector.vector_sample.slice(0, 5).map(v => v.toFixed(4)).join(', ')}, ...]
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="text-center">
        <p className="text-xs text-gray-500">
          Preview limited to first {max_vectors} vectors.
        </p>
      </div>
    </div>
  )
}
