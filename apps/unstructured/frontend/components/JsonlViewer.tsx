import { useEffect, useState } from 'react'
import { Loader2, FileJson, Hash, FileText } from 'lucide-react'
import { apiClient } from '@/lib/api-client'

interface Chunk {
  chunk_id: string
  text: string
  token_est: number
  page?: number
  section?: string
  mid_sentence_boundary?: boolean
  [key: string]: any
}

interface JsonlViewerProps {
  artifact_id: string
  storage_key: string
  max_chunks?: number
}

export function JsonlViewer({ artifact_id, storage_key, max_chunks = 5 }: JsonlViewerProps) {
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchChunkPreview()
  }, [artifact_id])

  const fetchChunkPreview = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await apiClient.getArtifactChunkPreview(artifact_id, max_chunks)
      if (response.error) throw new Error(response.error)
      const content: string = response.data.content || ''
      const parsed = content
        .split('\n')
        .filter((line: string) => line.trim())
        .map((line: string) => {
          try { return JSON.parse(line) } catch { return null }
        })
        .filter(Boolean) as Chunk[]
      setChunks(parsed)
    } catch (err) {
      console.error('Error fetching chunk preview:', err)
      setError(err instanceof Error ? err.message : 'Failed to load chunk preview')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        <span className="ml-2 text-sm text-gray-500">Loading chunk preview...</span>
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

  if (chunks.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <p className="text-sm text-gray-600">No chunks available in this artifact.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center">
          <FileJson className="h-4 w-4 mr-2 text-blue-500" />
          JSONL File Preview
        </h3>
        <span className="text-xs text-gray-500">
          Showing {chunks.length} chunk{chunks.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="space-y-3">
        {chunks.map((chunk, idx) => (
          <div key={idx} className="border border-gray-200 rounded-lg bg-white hover:shadow-md transition-shadow">
            <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <span className="text-xs font-mono text-gray-600 flex items-center">
                  <Hash className="h-3 w-3 mr-1" />
                  {chunk.chunk_id}
                </span>
                {chunk.page && <span className="text-xs text-gray-500">Page {chunk.page}</span>}
                {chunk.section && <span className="text-xs text-gray-500">{chunk.section}</span>}
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">
                  {chunk.token_est} tokens
                </span>
                {chunk.mid_sentence_boundary && (
                  <span className="text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded">
                    Mid-sentence
                  </span>
                )}
              </div>
            </div>
            <div className="p-4">
              <div className="flex items-start">
                <FileText className="h-4 w-4 text-gray-400 mr-2 mt-0.5 flex-shrink-0" />
                <pre className="text-sm text-gray-700 whitespace-pre-wrap break-words flex-1 font-sans">
                  {chunk.text}
                </pre>
              </div>
            </div>
            {(chunk.audience || chunk.source || chunk.timestamp) && (
              <div className="bg-gray-50 border-t border-gray-200 px-4 py-2 flex items-center space-x-4 text-xs text-gray-500">
                {chunk.audience && <span><span className="font-semibold">Audience:</span> {chunk.audience}</span>}
                {chunk.source && <span><span className="font-semibold">Source:</span> {chunk.source}</span>}
                {chunk.timestamp && (
                  <span><span className="font-semibold">Created:</span> {new Date(chunk.timestamp).toLocaleString()}</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="text-center">
        <p className="text-xs text-gray-500">
          Preview limited to first {max_chunks} chunks. Total chunks may be larger.
        </p>
      </div>
    </div>
  )
}
