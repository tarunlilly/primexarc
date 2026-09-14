import { useState } from 'react'
import { Copy, Check, Code2 } from 'lucide-react'

interface JsonDetailViewProps {
  data: any
  title?: string
}

export function JsonDetailView({ data, title = "Full Record" }: JsonDetailViewProps) {
  const [copied, setCopied] = useState(false)

  const jsonString = JSON.stringify(data, null, 2)

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonString)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center">
          <Code2 className="h-4 w-4 mr-2 text-gray-600" />
          <span className="text-sm font-semibold text-gray-700">{title}</span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 transition-colors px-2 py-1 rounded hover:bg-gray-100"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-green-600" />
              <span className="text-green-600">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Copy JSON</span>
            </>
          )}
        </button>
      </div>
      <div className="bg-gray-900 p-4 overflow-x-auto">
        <pre className="text-xs text-green-400 font-mono">
          {jsonString}
        </pre>
      </div>
    </div>
  )
}
