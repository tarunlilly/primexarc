import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { ArrowLeft, Download, Filter, Loader2, Layers } from 'lucide-react'
import { apiClient } from '@/lib/api-client'
import { JsonlViewer } from '@/components/JsonlViewer'
import { VectorViewer } from '@/components/VectorViewer'
import { JsonDetailView } from '@/components/JsonDetailView'

interface LineageNode {
  id: string
  label: string
  type: string
  stage?: string
  sub_stage?: string
  layer?: string
  status?: string
  duration_seconds?: number
  size_bytes: number
  storage_key: string
  created_at: string
  metadata?: any
  artifact_id?: string
}

interface LineageEdge {
  source: string
  target: string
  label: string
}

interface LineageMetadata {
  total_nodes: number
  max_depth_reached: number
  has_more: boolean
  direction: string
}

interface LineageResponse {
  nodes: LineageNode[]
  edges: LineageEdge[]
  metadata: LineageMetadata
}

// Detailed API response shape
interface DetailedArtifact {
  artifact_id: string
  artifact_name: string
  version: number
  file_size: number
  checksum: string
}

interface DetailedStage {
  stage_name: string
  artifact_type: string
  count: number
  artifacts: DetailedArtifact[]
}

interface DetailedLineageResponse {
  product_id: string
  product_name: string
  current_version: number
  pipeline_runs_analyzed: number
  total_artifacts: number
  stages: DetailedStage[]
  timestamp: string
}
interface ApiEntity {
  entity_id: string
  entity_type: string
  name: string
  description: string
  properties: Record<string, any>
  created_at: string
}

interface ApiRelationship {
  source_id: string
  target_id: string
  relationship_type: string
  properties: Record<string, any>
}

interface ApiLineageResponse {
  graph_id: string
  entity_id: string
  entity_type: string
  entities: ApiEntity[]
  relationships: ApiRelationship[]
  depth: number
  timestamp: string
}

function transformLineageResponse(api: ApiLineageResponse): LineageResponse {
  const nodes: LineageNode[] = api.entities.map(entity => ({
    id: entity.entity_id,
    label: entity.name,
    type: entity.entity_type === 'product' ? 'product' : (entity.properties.stage_name || entity.entity_type),
    stage: entity.properties.stage_name,
    size_bytes: entity.properties.file_size || 0,
    storage_key: entity.properties.storage_key || '',
    created_at: entity.created_at,
    metadata: entity.properties,
    artifact_id: entity.entity_type === 'artifact' ? entity.entity_id : undefined,
  }))

  const edges: LineageEdge[] = api.relationships.map(rel => ({
    source: rel.source_id,
    target: rel.target_id,
    label: rel.relationship_type,
  }))

  return {
    nodes,
    edges,
    metadata: {
      total_nodes: api.entities.length,
      max_depth_reached: api.depth,
      has_more: false,
      direction: 'downstream',
    },
  }
}

const stageColors: Record<string, string> = {
  product: '#C8102E',
  preprocess: '#3b82f6',
  scoring: '#10b981',
  fingerprint: '#8b5cf6',
  policy: '#f59e0b',
  validation: '#ef4444',
  reporting: '#ec4899',
  indexing: '#06b6d4',
  rawfile: '#6b7280',
}

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

export default function ProductLineagePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lineageData, setLineageData] = useState<LineageResponse | null>(null)
  const [detailedData, setDetailedData] = useState<DetailedLineageResponse | null>(null)
  const [selectedNode, setSelectedNode] = useState<LineageNode | null>(null)
  const [stageFilter, setStageFilter] = useState<string>('all')
  const [selectedLayers, setSelectedLayers] = useState<string[]>(['chunks', 'vectors'])
  const [showDetailedView, setShowDetailedView] = useState(false)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useEffect(() => {
    fetchLineage()
  }, [id, showDetailedView])

  useEffect(() => {
    if (lineageData) {
      updateFlowGraph()
    }
  }, [lineageData, stageFilter, selectedLayers])

  const toggleLayer = (layer: string) => {
    setSelectedLayers(prev =>
      prev.includes(layer) ? prev.filter(l => l !== layer) : [...prev, layer]
    )
  }

  const fetchLineage = async () => {
    try {
      setLoading(true)
      setError(null)

      let response
      if (showDetailedView) {
        response = await apiClient.getProductLineageDetailed(id!)
        if (response.error) throw new Error(response.error)
        setDetailedData(response.data as DetailedLineageResponse)
        setLineageData(null)
      } else {
        response = await apiClient.getProductLineage(id!)
        if (response.error) throw new Error(response.error)
        setDetailedData(null)
        setLineageData(transformLineageResponse(response.data as ApiLineageResponse))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load lineage')
      console.error('Failed to fetch lineage:', err)
    } finally {
      setLoading(false)
    }
  }

  const updateFlowGraph = () => {
    if (!lineageData) return

    let filteredNodes = lineageData.nodes

    if (selectedLayers.length < 2) {
      filteredNodes = filteredNodes.filter(node => {
        const nodeLayer = node.layer || 'chunks'
        return selectedLayers.includes(nodeLayer)
      })
    }

    if (stageFilter !== 'all') {
      filteredNodes = filteredNodes.filter(node => node.stage === stageFilter || node.type === 'rawfile')
    }

    const layer1Stages = ['product', 'rawfile', 'preprocess', 'scoring', 'fingerprint', 'policy', 'validation', 'reporting']
    const layer2Stages = ['indexing', 'embedding_generation', 'vector_preparation']
    const stageOrder = [...layer1Stages, ...layer2Stages]

    const nodesByStage: Record<string, typeof filteredNodes> = {}
    filteredNodes.forEach(node => {
      const stage = node.stage || node.type || 'rawfile'
      if (!nodesByStage[stage]) nodesByStage[stage] = []
      nodesByStage[stage].push(node)
    })

    const flowNodes: Node[] = []
    let xPosition = 100

    stageOrder.forEach(stage => {
      const stageNodes = nodesByStage[stage] || []
      if (stageNodes.length === 0) return

      const totalHeight = stageNodes.length * 200
      const startY = Math.max(100, 400 - totalHeight / 2)

      stageNodes.forEach((node, index) => {
        const color = stageColors[stage] || '#6b7280'
        const nodeLayer = node.layer || 'chunks'
        const isLayer2 = nodeLayer === 'vectors'
        const isSubStage = node.type === 'sub_stage'
        const yPosition = startY + index * 200

        const nodeStyle = isSubStage
          ? {
              background: `linear-gradient(135deg, ${color} 0%, ${color}dd 100%)`,
              color: 'white',
              border: '2px dashed rgba(255, 255, 255, 0.6)',
              borderRadius: '8px',
              padding: '10px',
              minWidth: '180px',
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
              cursor: 'pointer',
            }
          : {
              background: color,
              color: 'white',
              border: '2px solid white',
              borderRadius: '12px',
              padding: '12px',
              minWidth: '200px',
              boxShadow: isLayer2 ? '0 4px 12px rgba(168, 85, 247, 0.4)' : '0 4px 6px rgba(0, 0, 0, 0.1)',
              cursor: 'pointer',
            }

        flowNodes.push({
          id: node.id,
          type: 'default',
          data: {
            label: (
              <div className="flex flex-col items-center">
                <div className={`font-semibold ${isSubStage ? 'text-xs' : 'text-sm'} truncate max-w-[180px]`}>
                  {node.label}
                </div>
                {!isSubStage && <div className="text-xs text-white/80 mt-1">{formatBytes(node.size_bytes)}</div>}
                {isSubStage && node.duration_seconds && (
                  <div className="text-xs text-white/80 mt-1">{node.duration_seconds.toFixed(1)}s</div>
                )}
                <div className="flex items-center gap-1 mt-1">
                  {node.sub_stage && (
                    <div className="text-xs px-2 py-0.5 rounded-full bg-white/30 border border-white/40">
                      {node.sub_stage.split('.')[1] || node.sub_stage}
                    </div>
                  )}
                  {node.stage && !isSubStage && (
                    <div className="text-xs px-2 py-0.5 rounded-full bg-white/20">{node.stage}</div>
                  )}
                  {node.metadata?.version && (
                    <div className="text-xs px-2 py-0.5 rounded-full bg-yellow-500/30 border border-yellow-300">
                      v{node.metadata.version}
                    </div>
                  )}
                  {isLayer2 && !isSubStage && (
                    <div className="text-xs px-2 py-0.5 rounded-full bg-purple-500/30 border border-purple-300">L2</div>
                  )}
                  {node.status === 'success' && isSubStage && <div className="text-xs">✓</div>}
                </div>
              </div>
            ),
            nodeData: node,
          },
          position: { x: xPosition, y: yPosition },
          style: nodeStyle,
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
        })
      })

      xPosition += 400
    })

    const nodeIds = new Set(filteredNodes.map(n => n.id))
    const filteredEdges = lineageData.edges.filter(
      edge => nodeIds.has(edge.source) && nodeIds.has(edge.target)
    )

    const flowEdges: Edge[] = filteredEdges.map(edge => ({
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      label: edge.label === 'input_to' ? '' : edge.label,
      type: 'smoothstep',
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
      style: { stroke: '#94a3b8', strokeWidth: 2.5 },
      labelStyle: { fontSize: 11, fontWeight: 500, fill: '#475569' },
      labelBgStyle: { fill: 'white', fillOpacity: 0.9 },
    }))

    setNodes(flowNodes)
    setEdges(flowEdges)
  }

  const onNodeClick = (_event: React.MouseEvent, node: Node) => {
    const lineageNode = lineageData?.nodes.find(n => n.id === node.id)
    if (lineageNode) setSelectedNode(lineageNode)
  }

  const uniqueStages = lineageData
    ? Array.from(new Set(lineageData.nodes.map(n => n.stage).filter(Boolean)))
    : []

  // All possible stages for dropdown (including those without current data)
  const allPossibleStages = ['rawfile', 'preprocess', 'scoring', 'fingerprint', 'policy', 'validation', 'reporting', 'indexing']

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen">
        <div className="text-red-600 mb-4">{error}</div>
        <button onClick={() => navigate(-1)} className="text-blue-600 hover:text-blue-800">Go Back</button>
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate(-1)} className="text-gray-600 hover:text-gray-900">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">AI Data Lineage</h1>
            <p className="text-sm text-gray-500">
              {lineageData?.metadata.total_nodes || 0} nodes • {lineageData?.edges.length || 0} edges • Flow: Left → Right
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Granularity Toggle */}
          <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setShowDetailedView(false)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                !showDetailedView ? 'bg-white text-gray-900 shadow-sm' : 'bg-transparent text-gray-600 hover:bg-gray-200'
              }`}
            >
              Stage View
            </button>
            <button
              onClick={() => setShowDetailedView(true)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                showDetailedView ? 'bg-white text-gray-900 shadow-sm' : 'bg-transparent text-gray-600 hover:bg-gray-200'
              }`}
            >
              Sub-Stage View
            </button>
          </div>

          {/* Layer Toggle */}
          <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => toggleLayer('chunks')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                selectedLayers.includes('chunks') ? 'bg-blue-600 text-white' : 'bg-transparent text-gray-600 hover:bg-gray-200'
              }`}
            >
              <Layers className="w-3 h-3" />
              Layer 1: Chunks
            </button>
            <button
              onClick={() => toggleLayer('vectors')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                selectedLayers.includes('vectors') ? 'bg-green-600 text-white' : 'bg-transparent text-gray-600 hover:bg-gray-200'
              }`}
            >
              <Layers className="w-3 h-3" />
              Layer 2: Vectors
            </button>
          </div>

          {/* Stage Filter */}
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <select
              value={stageFilter}
              onChange={(e) => setStageFilter(e.target.value)}
              className="text-sm border border-gray-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Stages</option>
              {allPossibleStages.map(stage => (
                <option key={stage} value={stage}>{stage.charAt(0).toUpperCase() + stage.slice(1)}</option>
              ))}
            </select>
          </div>

          <button
            onClick={() => alert('Export functionality coming soon! Use browser screenshot for now.')}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            <Download className="w-4 h-4" />
            Export
          </button>
        </div>
      </div>

      {/* Graph + Side Panel */}
      {showDetailedView && detailedData ? (
        <div className="flex-1 overflow-auto p-6 bg-gray-50">
          <div className="mb-4 flex items-center gap-4 text-sm text-gray-600">
            <span><strong>{detailedData.product_name}</strong> · v{detailedData.current_version}</span>
            <span>{detailedData.total_artifacts} artifacts across {detailedData.stages.length} stages</span>
            <span>{detailedData.pipeline_runs_analyzed} pipeline runs analyzed</span>
          </div>
          <div className="flex items-start gap-3 overflow-x-auto pb-4">
            {detailedData.stages.map((stage, idx) => (
              <div key={stage.stage_name} className="flex items-start gap-3 flex-shrink-0">
                <div className="bg-white border border-gray-200 rounded-xl shadow-sm w-64">
                  <div
                    className="px-4 py-3 rounded-t-xl text-white text-sm font-semibold flex items-center justify-between"
                    style={{ backgroundColor: stageColors[stage.stage_name] || '#6b7280' }}
                  >
                    <span className="capitalize">{stage.stage_name}</span>
                    <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full">{stage.count}</span>
                  </div>
                  <div className="p-3 space-y-2">
                    {stage.artifacts.map(artifact => (
                      <div key={artifact.artifact_id} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                        <div className="text-xs font-medium text-gray-900 truncate" title={artifact.artifact_name}>
                          {artifact.artifact_name}
                        </div>
                        <div className="flex items-center justify-between mt-1.5 text-xs text-gray-500">
                          <span>v{artifact.version}</span>
                          <span>{formatBytes(artifact.file_size)}</span>
                        </div>
                        {artifact.checksum && (
                          <div className="mt-1 text-[10px] font-mono text-gray-400 truncate" title={artifact.checksum}>
                            {artifact.checksum.slice(0, 16)}…
                          </div>
                        )}
                      </div>
                    ))}
                    {stage.count === 0 && (
                      <p className="text-xs text-gray-400 text-center py-2">No artifacts</p>
                    )}
                  </div>
                </div>
                {idx < detailedData.stages.length - 1 && (
                  <div className="flex items-center self-center text-gray-400 flex-shrink-0">
                    <div className="w-6 h-0.5 bg-gray-300" />
                    <div className="w-0 h-0 border-t-4 border-b-4 border-l-6 border-transparent border-l-gray-300" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
      <div className="flex-1 flex">
        <div className="flex-1 relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            fitView
            attributionPosition="bottom-left"
          >
            <Background />
            <Controls />
            <MiniMap
              nodeColor={(node) => {
                const lineageNode = lineageData?.nodes.find(n => n.id === node.id)
                const stage = lineageNode?.stage || 'rawfile'
                return stageColors[stage] || '#6b7280'
              }}
              maskColor="rgba(0, 0, 0, 0.1)"
            />
          </ReactFlow>

          {selectedLayers.length === 2 && (
            <div
              className="absolute top-0 bottom-0 border-l-4 border-dashed border-purple-400 pointer-events-none"
              style={{ left: '2100px' }}
            >
              <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 bg-purple-500 text-white text-xs px-3 py-1 rounded-full whitespace-nowrap shadow-lg">
                Layer 1 → Layer 2
              </div>
            </div>
          )}

          {/* Stage Legend */}
          <div className="absolute top-4 left-4 bg-white rounded-lg shadow-lg p-4 border border-gray-200 max-w-xs">
            <h4 className="text-sm font-semibold text-gray-900 mb-3">Pipeline Stages</h4>
            <div className="mb-3">
              <div className="text-xs font-semibold text-blue-600 mb-2">Layer 1: AI-Ready Chunks</div>
              <div className="space-y-2">
                {Object.entries(stageColors)
                  .filter(([stage]) => ['rawfile', 'preprocess', 'scoring', 'fingerprint', 'policy', 'validation'].includes(stage))
                  .map(([stage, color]) => (
                    <div key={stage} className="flex items-center gap-2">
                      <div className="w-4 h-4 rounded" style={{ backgroundColor: color }} />
                      <span className="text-xs text-gray-700 capitalize">{stage}</span>
                    </div>
                  ))}
              </div>
            </div>
            <div className="border-t pt-3">
              <div className="text-xs font-semibold text-purple-600 mb-2">Layer 2: AI-Ready Vectors</div>
              <div className="space-y-2">
                {Object.entries(stageColors)
                  .filter(([stage]) => ['indexing'].includes(stage))
                  .map(([stage, color]) => (
                    <div key={stage} className="flex items-center gap-2">
                      <div className="w-4 h-4 rounded border-2 border-purple-400" style={{ backgroundColor: color }} />
                      <span className="text-xs text-gray-700 capitalize">{stage}</span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </div>

        {/* Side Panel */}
        {selectedNode && (
          <div className="w-96 bg-white border-l overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">Node Details</h3>
                <button onClick={() => setSelectedNode(null)} className="text-gray-400 hover:text-gray-600 text-xl">×</button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium text-gray-500">Name</label>
                  <div className="mt-1 text-sm text-gray-900">{selectedNode.label}</div>
                </div>

                {selectedNode.stage && (
                  <div>
                    <label className="text-sm font-medium text-gray-500">Stage</label>
                    <div className="mt-1">
                      <span
                        className="inline-block px-3 py-1 rounded-full text-sm text-white"
                        style={{ backgroundColor: stageColors[selectedNode.stage] }}
                      >
                        {selectedNode.stage}
                      </span>
                    </div>
                  </div>
                )}

                <div>
                  <label className="text-sm font-medium text-gray-500">Type</label>
                  <div className="mt-1 text-sm text-gray-900">{selectedNode.type}</div>
                </div>

                {selectedNode.type !== 'sub_stage' && (
                  <div>
                    <label className="text-sm font-medium text-gray-500">Size</label>
                    <div className="mt-1 text-sm text-gray-900">{formatBytes(selectedNode.size_bytes)}</div>
                  </div>
                )}

                {selectedNode.type === 'sub_stage' && selectedNode.duration_seconds !== undefined && (
                  <div>
                    <label className="text-sm font-medium text-gray-500">Duration</label>
                    <div className="mt-1 text-sm text-gray-900">{selectedNode.duration_seconds.toFixed(3)}s</div>
                  </div>
                )}

                {selectedNode.type === 'sub_stage' && selectedNode.status && (
                  <div>
                    <label className="text-sm font-medium text-gray-500">Status</label>
                    <div className="mt-1">
                      <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                        selectedNode.status === 'success' ? 'bg-green-100 text-green-800'
                        : selectedNode.status === 'failed' ? 'bg-red-100 text-red-800'
                        : 'bg-gray-100 text-gray-800'
                      }`}>
                        {selectedNode.status}
                      </span>
                    </div>
                  </div>
                )}

                {selectedNode.type !== 'sub_stage' && selectedNode.created_at && (
                  <div>
                    <label className="text-sm font-medium text-gray-500">Created At</label>
                    <div className="mt-1 text-sm text-gray-900">{new Date(selectedNode.created_at).toLocaleString()}</div>
                  </div>
                )}

                {selectedNode.type !== 'sub_stage' && selectedNode.storage_key && (
                  <div>
                    <label className="text-sm font-medium text-gray-500">Storage Key</label>
                    <div className="mt-1 text-xs text-gray-600 break-all font-mono bg-gray-50 p-2 rounded">
                      {selectedNode.storage_key}
                    </div>
                  </div>
                )}

                {selectedNode.type === 'sub_stage' && selectedNode.metadata?.metrics && (
                  <div>
                    <label className="text-sm font-medium text-gray-500">Sub-Stage Metrics</label>
                    <pre className="mt-1 text-xs text-gray-600 bg-gray-50 p-2 rounded overflow-x-auto">
                      {JSON.stringify(selectedNode.metadata.metrics, null, 2)}
                    </pre>
                  </div>
                )}

                {selectedNode.metadata && (
                  <div>
                    <label className="text-sm font-medium text-gray-500">Metadata</label>
                    <pre className="mt-1 text-xs text-gray-600 bg-gray-50 p-2 rounded overflow-x-auto">
                      {JSON.stringify(selectedNode.metadata, null, 2)}
                    </pre>
                  </div>
                )}

                <div className="mt-6 border-t pt-4">
                  <JsonDetailView data={selectedNode} title="Complete Artifact Record" />
                </div>

                {selectedNode.artifact_id && selectedNode.storage_key?.endsWith('.jsonl') && (
                  <div className="mt-6 border-t pt-4">
                    <h4 className="text-sm font-semibold text-gray-900 mb-3">Chunk Preview</h4>
                    <JsonlViewer artifact_id={selectedNode.artifact_id} storage_key={selectedNode.storage_key} max_chunks={5} />
                  </div>
                )}

                {selectedNode.artifact_id && selectedNode.stage === 'indexing' && (
                  <div className="mt-6 border-t pt-4">
                    <h4 className="text-sm font-semibold text-gray-900 mb-3">Vector Preview</h4>
                    <VectorViewer
                      artifact_id={selectedNode.artifact_id}
                      storage_key={selectedNode.storage_key}
                      collection_name={selectedNode.metadata?.collection_name}
                      max_vectors={5}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
      )}
    </div>
  )
}
