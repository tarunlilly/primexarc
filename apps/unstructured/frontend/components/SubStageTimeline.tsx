import { CheckCircle, XCircle, MinusCircle, Clock } from 'lucide-react'

interface SubStage {
  status: string
  timestamp: string
  duration_seconds: number | null
  metrics: Record<string, any>
}

interface SubStageTimelineProps {
  subStages: Record<string, SubStage>
  stageName: string
}

export default function SubStageTimeline({ subStages, stageName }: SubStageTimelineProps) {
  const relevantSubStages = Object.entries(subStages).filter(([name]) =>
    name.startsWith(`${stageName}.`)
  )

  if (relevantSubStages.length === 0) {
    return null
  }

  const totalDuration = relevantSubStages.reduce((sum, [_, data]) =>
    sum + (data.duration_seconds || 0), 0
  )

  const getStatusIcon = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'success': return <CheckCircle className="h-3 w-3 text-green-500" />
      case 'failed': return <XCircle className="h-3 w-3 text-red-500" />
      case 'skipped': return <MinusCircle className="h-3 w-3 text-yellow-500" />
      default: return <Clock className="h-3 w-3 text-gray-400" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'success': return 'bg-green-500'
      case 'failed': return 'bg-red-500'
      case 'skipped': return 'bg-yellow-500'
      default: return 'bg-gray-400'
    }
  }

  const formatDuration = (seconds: number | null) => {
    if (seconds === null || seconds === undefined) return 'N/A'
    if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
    if (seconds < 60) return `${seconds.toFixed(2)}s`
    const mins = Math.floor(seconds / 60)
    const secs = Math.round(seconds % 60)
    return `${mins}m ${secs}s`
  }

  const formatSubStageName = (fullName: string) => {
    const name = fullName.split('.').pop() || fullName
    return name.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
  }

  const formatMetricValue = (value: any): string => {
    if (typeof value === 'boolean') return value ? 'Yes' : 'No'
    if (typeof value === 'number') {
      if (Number.isInteger(value)) return value.toLocaleString()
      return value.toFixed(2)
    }
    return String(value)
  }

  return (
    <div className="mt-4 mb-2">
      <div className="flex items-center justify-between mb-3">
        <h5 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
          Sub-Stage Breakdown
        </h5>
        <span className="text-xs text-gray-500">Total: {formatDuration(totalDuration)}</span>
      </div>

      <div className="mb-4">
        <div className="flex h-6 rounded-lg overflow-hidden border border-gray-200">
          {relevantSubStages.map(([name, data]) => {
            const percentage = totalDuration > 0
              ? ((data.duration_seconds || 0) / totalDuration) * 100
              : 100 / relevantSubStages.length
            return (
              <div
                key={name}
                className={`relative ${getStatusColor(data.status)} transition-all hover:opacity-80`}
                style={{ width: `${percentage}%` }}
                title={`${formatSubStageName(name)}: ${formatDuration(data.duration_seconds)} (${percentage.toFixed(1)}%)`}
              >
                {percentage > 10 && (
                  <span className="absolute inset-0 flex items-center justify-center text-[10px] font-medium text-white">
                    {percentage.toFixed(0)}%
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <div className="space-y-2">
        {relevantSubStages.map(([name, data]) => {
          const percentage = totalDuration > 0
            ? ((data.duration_seconds || 0) / totalDuration) * 100
            : 0
          return (
            <div key={name} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center space-x-2">
                  {getStatusIcon(data.status)}
                  <span className="text-sm font-medium text-gray-900">{formatSubStageName(name)}</span>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold text-gray-900">{formatDuration(data.duration_seconds)}</div>
                  <div className="text-xs text-gray-500">{percentage.toFixed(1)}%</div>
                </div>
              </div>
              {data.metrics && Object.keys(data.metrics).length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-200">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                    {Object.entries(data.metrics).map(([key, value]) => (
                      <div key={key} className="flex justify-between text-xs">
                        <span className="text-gray-600">
                          {key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}:
                        </span>
                        <span className="font-medium text-gray-900 ml-2">{formatMetricValue(value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
