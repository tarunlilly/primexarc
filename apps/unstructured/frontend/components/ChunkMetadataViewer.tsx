import { useState, useEffect } from 'react'
import { Loader2, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { apiClient } from '@/lib/api-client'

interface ChunkMetadataProps {
  productId: string
  version?: number
}

interface Chunk {
  id: string
  vector_size?: number
  metadata: {
    chunk_id?: string
    chunk_text?: string
    chunk_order?: number
    source_file?: string
    section?: string
    page_number?: number
    confidence_score?: number | null
    noise_score?: number | null
    coherence_score?: number | null
    [key: string]: any
  }
}

export function ChunkMetadataViewer({ productId, version }: ChunkMetadataProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [totalChunks, setTotalChunks] = useState(0)
  const [collectionName, setCollectionName] = useState('')
  const [offset, setOffset] = useState(0)
  const [limit] = useState(50)
  const [searchTerm, setSearchTerm] = useState('')
  const [expandedMetadata, setExpandedMetadata] = useState<Record<string, boolean>>({})
  const [showRawJson, setShowRawJson] = useState<Record<string, boolean>>({})

  useEffect(() => {
    fetchChunks()
  }, [productId, version, offset])

  const fetchChunks = async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await apiClient.getProductChunks(productId, {
        version,
        offset,
        limit,
      })

      if (response.error) {
        throw new Error(response.error)
      }

      setChunks(response.data.chunks || [])
      setTotalChunks(response.data.total_count || response.data.total_chunks || 0)
      setCollectionName(response.data.collection_name || '')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load chunks')
      console.error('Failed to fetch chunks:', err)
    } finally {
      setLoading(false)
    }
  }

  const filteredChunks = chunks.filter(chunk =>
    searchTerm ? (chunk.metadata.chunk_text || '').toLowerCase().includes(searchTerm.toLowerCase()) : true
  )

  const handlePrevPage = () => {
    if (offset > 0) {
      setOffset(Math.max(0, offset - limit))
    }
  }

  const handleNextPage = () => {
    if (offset + limit < totalChunks) {
      setOffset(offset + limit)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-yellow-600 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-yellow-800 mb-1">Chunks Not Available</h3>
              <p className="text-sm text-yellow-700 mb-2">{error}</p>
              <div className="text-xs text-yellow-600">
                <p className="font-medium mb-1">Possible reasons:</p>
                <ul className="list-disc list-inside space-y-1 ml-2">
                  <li>The product pipeline hasn't reached the indexing stage yet</li>
                  <li>The indexing stage failed - check pipeline status</li>
                  <li>Qdrant service is down or unreachable</li>
                  <li>This version was never indexed (try a different version)</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        {version && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm text-blue-800">
              <strong>Tip:</strong> Try viewing chunks from an earlier version that completed indexing successfully.
            </p>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Chunk Metadata</h3>
          <p className="text-sm text-gray-500">
            {totalChunks} chunks in collection: {collectionName}
          </p>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search chunks..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {filteredChunks.length === 0 ? (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
          <div className="text-gray-500 mb-2">
            {searchTerm ? (
              <>
                <Search className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                <p className="font-medium">No chunks match your search</p>
                <p className="text-sm mt-1">Try a different search term</p>
              </>
            ) : totalChunks === 0 ? (
              <>
                <svg className="w-12 h-12 mx-auto mb-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                </svg>
                <p className="font-medium">No chunks indexed yet</p>
                <p className="text-sm mt-1">The indexing stage may still be running</p>
              </>
            ) : (
              <>
                <p className="font-medium">No chunks on this page</p>
                <p className="text-sm mt-1">Try navigating to a different page</p>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredChunks.map((chunk) => (
            <div
              key={chunk.id}
              className="bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <div className="text-xs font-medium text-gray-700 mb-1">
                    {chunk.metadata.source_file || 'Unknown file'}: Chunk {(() => {
                      if (chunk.metadata.chunk_id) {
                        const match = chunk.metadata.chunk_id.match(/_c(\d+)$/)
                        if (match) return parseInt(match[1]) + 1
                      }
                      return chunk.metadata.chunk_order !== undefined ? chunk.metadata.chunk_order + 1 : '?'
                    })()}
                    {chunk.metadata.chunk_of > 0 && ` of ${chunk.metadata.chunk_of}`}
                  </div>
                  <div className="flex items-center gap-2">
                    {chunk.metadata.page_number && (
                      <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                        Page {chunk.metadata.page_number}
                      </span>
                    )}
                    {chunk.metadata.section && (
                      <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                        {chunk.metadata.section}
                      </span>
                    )}
                    {chunk.vector_size && (
                      <span className="text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded">
                        {chunk.vector_size}D vector
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="text-sm text-gray-600 leading-relaxed">
                {chunk.metadata.chunk_text || <span className="italic text-gray-400">No text content</span>}
                {(chunk.metadata.chunk_text?.length ?? 0) >= 500 && '...'}
              </div>

              <div className="mt-3">
                <button
                  onClick={() => setExpandedMetadata(prev => ({
                    ...prev,
                    [chunk.id]: !prev[chunk.id]
                  }))}
                  className="text-xs text-gray-500 hover:text-gray-700 font-medium"
                >
                  {expandedMetadata[chunk.id] ? '▼' : '▶'} View metadata
                </button>

                {expandedMetadata[chunk.id] && (
                  <div className="mt-3 p-3 bg-gray-50 rounded-md border border-gray-200">
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div>
                        <span className="font-semibold text-gray-700">Chunk ID:</span>
                        <span className="ml-2 font-mono text-gray-600 text-[10px]">{chunk.metadata.chunk_id || chunk.id}</span>
                      </div>
                      {chunk.metadata.confidence_score != null && (
                        <div>
                          <span className="font-semibold text-gray-700">Confidence:</span>
                          <span className="ml-2 text-gray-600">{chunk.metadata.confidence_score?.toFixed(2)}</span>
                        </div>
                      )}
                      {chunk.metadata.noise_score != null && (
                        <div>
                          <span className="font-semibold text-gray-700">Noise Score:</span>
                          <span className="ml-2 text-gray-600">{chunk.metadata.noise_score?.toFixed(2)}</span>
                        </div>
                      )}
                      {chunk.metadata.coherence_score != null && (
                        <div>
                          <span className="font-semibold text-gray-700">Coherence:</span>
                          <span className="ml-2 text-gray-600">{chunk.metadata.coherence_score?.toFixed(2)}</span>
                        </div>
                      )}
                      {chunk.metadata.source_file && (
                        <div className="col-span-2">
                          <span className="font-semibold text-gray-700">Source File:</span>
                          <span className="ml-2 text-gray-600">{chunk.metadata.source_file}</span>
                        </div>
                      )}
                      <div className="col-span-2 mt-2 pt-2 border-t border-gray-300">
                        <button
                          onClick={() => setShowRawJson(prev => ({
                            ...prev,
                            [chunk.id]: !prev[chunk.id]
                          }))}
                          className="text-xs text-blue-600 hover:underline font-medium"
                        >
                          {showRawJson[chunk.id] ? 'Hide' : 'Show'} raw JSON
                        </button>
                        {showRawJson[chunk.id] && (
                          <pre className="mt-2 p-2 bg-white rounded border border-gray-300 overflow-auto text-[10px] max-h-60">
                            {JSON.stringify(chunk.metadata, null, 2)}
                          </pre>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between pt-4 border-t">
        <div className="text-sm text-gray-600">
          Showing {offset + 1}-{Math.min(offset + limit, totalChunks)} of {totalChunks} chunks
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handlePrevPage}
            disabled={offset === 0}
            className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={handleNextPage}
            disabled={offset + limit >= totalChunks}
            className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
