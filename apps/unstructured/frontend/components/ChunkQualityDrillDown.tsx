import { useState, useEffect, useCallback } from 'react'
import { X, Loader2, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'
import { apiClient } from '@/lib/api-client'
import { DetailedDiffView } from './DetailedDiffView'

interface ChunkData {
  chunk_id: string
  chunk_index: number
  chunk_of: number
  text_preview: string
  text_full: string
  text_length: number
  section: string
  page: number | null
  filename: string
  document_id: string
  score: number
  trust_completeness?: number
  trust_accuracy?: number
  trust_secure?: number
  trust_quality?: number
  trust_context_quality?: number
  chunk_coherence?: number
  noise_free_score?: number
  noise_details?: {
    noise_ratio: number
    total_chars: number
    noise_chars: number
    boilerplate_chars: number
    navigation_chars: number
    legal_footer_chars: number
  }
  mid_sentence_boundary: boolean
  raw_text_full?: string
  raw_text_length?: number
  has_raw_text: boolean
}

interface ChunkQualityDrillDownProps {
  productId: string
  version: number
  metric: 'noise' | 'completeness' | 'structure'
  onClose: () => void
}

export function ChunkQualityDrillDown({ productId, version, metric, onClose }: ChunkQualityDrillDownProps) {
  const [chunks, setChunks] = useState<ChunkData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedChunkId, setExpandedChunkId] = useState<string | null>(null)
  const [legacyData, setLegacyData] = useState(false)
  const [offset, setOffset] = useState(0)
  const [totalCount, setTotalCount] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [noiseThreshold, setNoiseThreshold] = useState(50)
  const [confidenceThreshold, setConfidenceThreshold] = useState(70)
  const [skipMidSentence, setSkipMidSentence] = useState(true)
  const LIMIT = 100

  const getFiltersForMetric = (noiseMax: number, confidenceMax: number, skipMid: boolean) => {
    switch (metric) {
      case 'noise': return { noise_max: String(noiseMax), sort_by: 'noise_score', sort_order: 'asc' as const }
      case 'completeness': return { score_max: String(confidenceMax), sort_by: 'score', sort_order: 'asc' as const }
      case 'structure': return { skip_mid_sentence: String(skipMid), sort_by: 'chunk_order', sort_order: 'asc' as const }
      default: return { sort_by: 'chunk_order', sort_order: 'asc' as const }
    }
  }

  const fetchChunks = useCallback(async (pageOffset: number = 0) => {
    try {
      setLoading(true)
      setError(null)
      const filters = getFiltersForMetric(noiseThreshold, confidenceThreshold, skipMidSentence)
      const params = new URLSearchParams({
        sort_by: filters.sort_by,
        sort_order: filters.sort_order,
        offset: String(pageOffset),
        limit: String(LIMIT),
        ...(metric === 'noise' && { noise_max: filters.noise_max }),
        ...(metric === 'completeness' && { score_max: filters.score_max }),
        ...(metric === 'structure' && { skip_mid_sentence: filters.skip_mid_sentence }),
      })
      const response = await apiClient.get(
        `/api/v1/chunk-quality/products/${productId}/versions/${version}/chunks?${params}`
      )
      if (response.error) throw new Error(response.error || 'Failed to fetch chunk details')

      console.log('Chunk quality API response:', response.data)

      // Transform QualityChunkPoint array to ChunkData array
      const totalChunks = response.data.total_count || 0
      const transformedChunks = (response.data.chunks || []).map((point: any, index: number) => {
        console.log('Transforming chunk point:', point)
        const rawText = point.metadata?.raw_text
        const cleanedText = point.metadata?.chunk_text
        return {
          chunk_id: point.id || point.metadata?.chunk_id || '',
          chunk_index: response.data.offset + index,
          chunk_of: totalChunks,
          text_preview: cleanedText?.substring(0, 100) || 'No text',
          text_full: cleanedText || 'No text available',
          text_length: cleanedText?.length || 0,
          section: point.metadata?.section,
          page: point.metadata?.page_number,
          filename: point.metadata?.source_file || 'unknown',
          document_id: point.metadata?.chunk_id || '',
          score: point.metadata?.score || 0,
          trust_completeness: point.metadata?.score || 0,
          chunk_coherence: point.metadata?.coherence_score || 0,
          noise_free_score: point.metadata?.noise_score ? 100 - point.metadata.noise_score : 0,
          mid_sentence_boundary: point.metadata?.mid_sentence_end || false,
          raw_text_full: rawText || '',
          raw_text_length: rawText?.length || 0,
          has_raw_text: !!rawText && point.metadata?.has_raw_text,
        }
      })

      setChunks(transformedChunks)
      setOffset(pageOffset)
      setTotalCount(response.data.total_count || 0)
      setHasMore(response.data.has_more || false)
      setLegacyData(false)
    } catch (err) {
      console.error('Error fetching chunk details:', err)
      setError(err instanceof Error ? err.message : 'Failed to load chunk data')
    } finally {
      setLoading(false)
    }
  }, [productId, version, metric, noiseThreshold, confidenceThreshold, skipMidSentence])

  useEffect(() => {
    fetchChunks(0)
    setOffset(0)
  }, [productId, version, metric])

  const handleToggleSkipMidSentence = useCallback(async () => {
    const newValue = !skipMidSentence
    setSkipMidSentence(newValue)

    try {
      setLoading(true)
      setError(null)
      const filters = getFiltersForMetric(noiseThreshold, confidenceThreshold, newValue)
      const params = new URLSearchParams({
        sort_by: filters.sort_by,
        sort_order: filters.sort_order,
        offset: '0',
        limit: String(LIMIT),
        ...(metric === 'structure' && { skip_mid_sentence: String(newValue) }),
      })
      const response = await apiClient.get(
        `/api/v1/chunk-quality/products/${productId}/versions/${version}/chunks?${params}`
      )
      if (response.error) throw new Error(response.error || 'Failed to fetch chunk details')

      const totalChunks = response.data.total_count || 0
      const transformedChunks = (response.data.chunks || []).map((point: any, index: number) => {
        const rawText = point.metadata?.raw_text
        const cleanedText = point.metadata?.chunk_text
        return {
          chunk_id: point.id || point.metadata?.chunk_id || '',
          chunk_index: response.data.offset + index,
          chunk_of: totalChunks,
          text_preview: cleanedText?.substring(0, 100) || 'No text',
          text_full: cleanedText || 'No text available',
          text_length: cleanedText?.length || 0,
          section: point.metadata?.section,
          page: point.metadata?.page_number,
          filename: point.metadata?.source_file || 'unknown',
          document_id: point.metadata?.chunk_id || '',
          score: point.metadata?.score || 0,
          trust_completeness: point.metadata?.score || 0,
          chunk_coherence: point.metadata?.coherence_score || 0,
          noise_free_score: point.metadata?.noise_score ? 100 - point.metadata.noise_score : 0,
          mid_sentence_boundary: point.metadata?.mid_sentence_end || false,
          raw_text_full: rawText || '',
          raw_text_length: rawText?.length || 0,
          has_raw_text: !!rawText && point.metadata?.has_raw_text,
        }
      })

      setChunks(transformedChunks)
      setOffset(0)
      setTotalCount(response.data.total_count || 0)
      setHasMore(response.data.has_more || false)
    } catch (err) {
      console.error('Error fetching chunk details:', err)
      setError(err instanceof Error ? err.message : 'Failed to load chunk data')
    } finally {
      setLoading(false)
    }
  }, [skipMidSentence, noiseThreshold, confidenceThreshold, productId, version, metric, LIMIT])

  const getMetricTitle = () => {
    switch (metric) {
      case 'noise': return 'Noise Reduction Details'
      case 'completeness': return 'Completeness Details'
      case 'structure': return 'Structure Details'
      default: return 'Quality Details'
    }
  }

  const getMetricDescription = () => {
    switch (metric) {
      case 'noise': return `Showing chunks with noise levels up to ${noiseThreshold}%`
      case 'completeness': return `Showing chunks with completeness scores up to ${confidenceThreshold}%`
      case 'structure': return 'Showing chunks with structure issues (mid-sentence boundaries)'
      default: return 'Showing chunk quality details'
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{getMetricTitle()}</h2>
            <p className="text-sm text-gray-600 mt-1">{getMetricDescription()}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg transition-colors" aria-label="Close">
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        {metric === 'noise' && (
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium text-gray-700">Noise Threshold:</label>
              <input
                type="range"
                min="0"
                max="100"
                value={noiseThreshold}
                onChange={(e) => setNoiseThreshold(Number(e.target.value))}
                onMouseUp={() => fetchChunks(0)}
                onTouchEnd={() => fetchChunks(0)}
                className="flex-1"
              />
              <span className="text-sm font-semibold text-gray-900 min-w-[40px]">{noiseThreshold}%</span>
            </div>
          </div>
        )}

        {metric === 'completeness' && (
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium text-gray-700">Completeness Threshold:</label>
              <input
                type="range"
                min="0"
                max="100"
                value={confidenceThreshold}
                onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                onMouseUp={() => fetchChunks(0)}
                onTouchEnd={() => fetchChunks(0)}
                className="flex-1"
              />
              <span className="text-sm font-semibold text-gray-900 min-w-[40px]">{confidenceThreshold}%</span>
            </div>
          </div>
        )}

        {metric === 'structure' && (
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium text-gray-700">Mid-Sentence Boundaries:</label>
              <button
                onClick={handleToggleSkipMidSentence}
                className={`px-4 py-1.5 text-sm font-medium rounded transition-colors ${
                  skipMidSentence
                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                {skipMidSentence ? 'Skip' : 'Include'}
              </button>
              <span className="text-sm text-gray-600">
                {skipMidSentence ? 'Skipping mid-sentence boundaries' : 'Including mid-sentence boundaries'}
              </span>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4 relative">
          {loading && (
            <div className="absolute inset-0 bg-white/50 backdrop-blur-sm flex items-center justify-center z-10 rounded-lg">
              <div className="flex flex-col items-center gap-2">
                <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
                <p className="text-sm font-medium text-gray-700">Updating results...</p>
              </div>
            </div>
          )}
          {!loading && !error && legacyData && chunks.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
              <div className="flex items-start gap-2">
                <AlertCircle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Quality Metrics Not Available</h3>
                  <p className="text-xs text-gray-600 mt-1">
                    This version was processed before enhanced quality metrics were implemented.
                    Run a new pipeline to enable detailed quality analysis.
                  </p>
                </div>
              </div>
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 text-gray-400 animate-spin mr-2" />
              <p className="text-sm text-gray-600">Loading chunk details...</p>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-start gap-2">
                <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Error Loading Data</h3>
                  <p className="text-xs text-gray-600 mt-1">{error}</p>
                </div>
              </div>
            </div>
          )}

          {!loading && !error && chunks.length === 0 && (
            <div className="text-center py-12">
              <p className="text-sm text-gray-600">No chunks found matching the criteria.</p>
              <p className="text-xs text-gray-500 mt-1">This metric may not have any issues to display.</p>
            </div>
          )}

          {!loading && !error && chunks.length > 0 && (
            <div className="space-y-3">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-sm text-gray-700">
                  Found <span className="font-semibold">{chunks.length}</span> chunk{chunks.length !== 1 ? 's' : ''}
                  {legacyData ? '' : ' with quality issues'}
                </p>
              </div>
              {chunks.map((chunk) => (
                <ChunkDetailCard
                  key={chunk.chunk_id}
                  chunk={chunk}
                  metric={metric}
                  isExpanded={expandedChunkId === chunk.chunk_id}
                  onToggleExpand={() =>
                    setExpandedChunkId(expandedChunkId === chunk.chunk_id ? null : chunk.chunk_id)
                  }
                  productId={productId}
                  version={version}
                />
              ))}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-200 bg-gray-50 space-y-3">
          {/* Pagination Controls */}
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-600">
              Showing {offset + 1}-{Math.min(offset + chunks.length, totalCount)} of {totalCount}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => fetchChunks(Math.max(0, offset - LIMIT))}
                disabled={offset === 0 || loading}
                className="px-3 py-1.5 text-sm font-medium bg-white border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                ← Previous
              </button>
              <button
                onClick={() => fetchChunks(offset + LIMIT)}
                disabled={!hasMore || loading}
                className="px-3 py-1.5 text-sm font-medium bg-white border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next →
              </button>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg transition-colors text-sm font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

interface ChunkDetailCardProps {
  chunk: ChunkData
  metric: 'noise' | 'completeness' | 'structure'
  isExpanded: boolean
  onToggleExpand: () => void
  productId: string
  version: number
}

function ChunkDetailCard({ chunk, metric, isExpanded, onToggleExpand, productId, version }: ChunkDetailCardProps) {
  const [viewMode, setViewMode] = useState<'before' | 'after' | 'sidebyside' | 'diff'>('after')

  const getMetricValue = () => {
    switch (metric) {
      case 'noise':
        if (chunk.noise_free_score === undefined) return 'Not calculated'
        if (chunk.noise_free_score === 0) return '0% (No noise detected)'
        return Math.round(chunk.noise_free_score)
      case 'completeness':
        return chunk.trust_completeness !== undefined && chunk.trust_completeness > 0 ? Math.round(chunk.trust_completeness) : 'Pending'
      case 'structure':
        return chunk.mid_sentence_boundary ? 'Mid-sentence' : 'Complete'
    }
  }

  const getMetricColor = () => {
    switch (metric) {
      case 'noise':
        const noiseFree = chunk.noise_free_score || 0
        if (noiseFree === 0) return 'text-gray-400'
        if (noiseFree < 25) return 'text-red-600'
        if (noiseFree < 50) return 'text-yellow-600'
        return 'text-green-600'
      case 'completeness':
        const completeness = chunk.trust_completeness || 0
        if (completeness === 0) return 'text-gray-400'
        if (completeness < 50) return 'text-red-600'
        if (completeness < 70) return 'text-yellow-600'
        return 'text-green-600'
      case 'structure':
        return chunk.mid_sentence_boundary ? 'text-red-600' : 'text-green-600'
    }
  }

  return (
    <div className="border border-gray-200 rounded-lg bg-white hover:shadow-md transition-shadow">
      <div className="p-4 cursor-pointer" onClick={onToggleExpand}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-mono text-gray-500">Chunk {chunk.chunk_index + 1} of {chunk.chunk_of}</span>
              {chunk.section && <><span className="text-gray-300">•</span><span className="text-xs text-gray-600">{chunk.section}</span></>}
              {chunk.page !== null && <><span className="text-gray-300">•</span><span className="text-xs text-gray-600">Page {chunk.page}</span></>}
            </div>
            <p className="text-sm text-gray-700 line-clamp-2">{chunk.text_preview}</p>
          </div>
          <div className="flex items-center gap-4 flex-shrink-0">
            <div className="text-right">
              <div className="text-xs text-gray-500 mb-1">
                {metric === 'noise' ? 'Noise Free' : metric === 'completeness' ? 'Completeness' : 'Status'}
              </div>
              <div className={`text-lg font-bold ${getMetricColor()}`}>
                {typeof getMetricValue() === 'number' ? `${getMetricValue()}%` : getMetricValue()}
              </div>
            </div>
            <button className="p-1 hover:bg-gray-100 rounded transition-colors">
              {isExpanded ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
            </button>
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="px-4 pb-4 border-t border-gray-100">
          {chunk.has_raw_text && (
            <div className="mt-4 flex gap-2 mb-3">
              {(['after', 'before', 'sidebyside', 'diff'] as const).map((mode) => (
                <button
                  key={mode}
                  className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                    viewMode === mode ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                  onClick={() => setViewMode(mode)}
                >
                  {mode === 'after' ? 'After (Cleaned)' : mode === 'before' ? 'Before (Raw)' : mode === 'sidebyside' ? 'Side-by-Side' : 'Detailed Diff'}
                </button>
              ))}
            </div>
          )}

          {!chunk.has_raw_text && (
            <div className="mt-4 bg-blue-50 border border-blue-200 rounded p-3 mb-3">
              <p className="text-xs text-blue-700">
                <strong>Note:</strong> Before/After comparison not available for this product version. Run the latest pipeline to enable side-by-side noise reduction comparisons.
              </p>
            </div>
          )}

          {viewMode === 'after' && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-gray-700 mb-2">Processed Text (After):</h4>
              <div className="bg-green-50 border border-green-200 rounded p-3 text-sm text-gray-700 whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">
                {chunk.text_full}
              </div>
              <div className="text-xs text-gray-500 mt-1">{chunk.text_length} characters</div>
            </div>
          )}

          {viewMode === 'before' && chunk.has_raw_text && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-gray-700 mb-2">Original Text (Before):</h4>
              <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-gray-700 whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">
                {chunk.raw_text_full}
              </div>
              <div className="text-xs text-gray-500 mt-1">{chunk.raw_text_length} characters</div>
            </div>
          )}

          {viewMode === 'sidebyside' && chunk.has_raw_text && (
            <div className="mt-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-2">
                    <span className="inline-block w-3 h-3 bg-red-400 rounded-full"></span>
                    Before (Raw with Noise)
                  </h4>
                  <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-gray-700 whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">
                    {chunk.raw_text_full}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{chunk.raw_text_length?.toLocaleString()} characters</div>
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-2">
                    <span className="inline-block w-3 h-3 bg-green-400 rounded-full"></span>
                    After (Cleaned)
                  </h4>
                  <div className="bg-green-50 border border-green-200 rounded p-3 text-sm text-gray-700 whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">
                    {chunk.text_full}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{chunk.text_length.toLocaleString()} characters</div>
                </div>
              </div>
            </div>
          )}

          {viewMode === 'diff' && chunk.has_raw_text && (
            <div className="mt-4">
              <DetailedDiffView chunkId={chunk.chunk_id} productId={productId} version={version} />
            </div>
          )}

          {!chunk.has_raw_text && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-gray-700 mb-2">Full Text:</h4>
              <div className="bg-gray-50 rounded p-3 text-sm text-gray-700 whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">
                {chunk.text_full}
              </div>
            </div>
          )}

          {metric === 'noise' && chunk.noise_details && viewMode !== 'diff' && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-gray-700 mb-2">Noise Breakdown:</h4>
              <div className="bg-gray-50 rounded p-3 space-y-2">
                <div className="flex justify-between text-sm"><span className="text-gray-600">Total Characters:</span><span className="font-mono">{chunk.noise_details.total_chars}</span></div>
                <div className="flex justify-between text-sm"><span className="text-gray-600">Noise Characters:</span><span className="font-mono text-red-600">{chunk.noise_details.noise_chars}</span></div>
                <div className="flex justify-between text-sm pl-4"><span className="text-gray-500">↳ Boilerplate:</span><span className="font-mono text-yellow-600">{chunk.noise_details.boilerplate_chars}</span></div>
                <div className="flex justify-between text-sm pl-4"><span className="text-gray-500">↳ Navigation:</span><span className="font-mono text-yellow-600">{chunk.noise_details.navigation_chars}</span></div>
                <div className="flex justify-between text-sm pl-4"><span className="text-gray-500">↳ Legal Footer:</span><span className="font-mono text-yellow-600">{chunk.noise_details.legal_footer_chars}</span></div>
                <div className="flex justify-between text-sm font-semibold border-t border-gray-200 pt-2 mt-2"><span className="text-gray-700">Noise Ratio:</span><span className="font-mono text-red-600">{Math.round(chunk.noise_details.noise_ratio)}%</span></div>
              </div>
            </div>
          )}

          <div className="mt-4">
            <h4 className="text-xs font-semibold text-gray-700 mb-2">Quality Scores:</h4>
            <div className="grid grid-cols-2 gap-2">
              {chunk.score !== undefined && chunk.score > 0 && (
                <div className="bg-gray-50 rounded p-2">
                  <div className="text-xs text-gray-500">AI Trust Score</div>
                  <div className="text-sm font-semibold">{Math.round(chunk.score)}%</div>
                </div>
              )}
              {chunk.chunk_coherence !== undefined && chunk.chunk_coherence > 0 && (
                <div className="bg-gray-50 rounded p-2">
                  <div className="text-xs text-gray-500">Coherence</div>
                  <div className="text-sm font-semibold">{Math.round(chunk.chunk_coherence)}%</div>
                </div>
              )}
              {chunk.noise_free_score !== undefined && chunk.noise_free_score > 0 && (
                <div className="bg-gray-50 rounded p-2">
                  <div className="text-xs text-gray-500">Noise Free</div>
                  <div className="text-sm font-semibold">{Math.round(chunk.noise_free_score)}%</div>
                </div>
              )}
              {chunk.trust_completeness !== undefined && chunk.trust_completeness > 0 && (
                <div className="bg-gray-50 rounded p-2">
                  <div className="text-xs text-gray-500">Completeness</div>
                  <div className="text-sm font-semibold">{Math.round(chunk.trust_completeness)}%</div>
                </div>
              )}
              {[chunk.score, chunk.chunk_coherence, chunk.noise_free_score, chunk.trust_completeness].every(s => !s || s === 0) && (
                <div className="col-span-2 bg-blue-50 border border-blue-200 rounded p-2">
                  <div className="text-xs text-blue-600">Quality metrics pending calculation during pipeline processing</div>
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 text-xs text-gray-500 space-y-1">
            <div>Chunk ID: <span className="font-mono">{chunk.chunk_id}</span></div>
            <div>Document: <span className="font-mono">{chunk.document_id}</span></div>
            {chunk.mid_sentence_boundary && (
              <div className="text-yellow-600 font-medium">⚠️ Ends mid-sentence</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
