
import { useState, useEffect } from 'react'
import { useDefaultUser } from '@/lib/default-user-context'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { ArrowLeft, Database, Globe, HardDrive, FileText, Folder, Share, Cloud } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ResultModal } from '@/components/ui/modal'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'

interface DataSource {
  id: string
  workspace_id: string
  product_id: string
  type: string
  config: Record<string, any>
  last_cursor?: Record<string, any>
  created_at: string
  updated_at?: string
}

const DATA_SOURCE_TYPES = [
  {
    id: 'web',
    name: 'Web Scraping',
    description: 'Extract data from websites',
    icon: Globe,
    configFields: [
      { name: 'url', label: 'URL', type: 'url', required: true },
      { name: 'headers', label: 'Headers (JSON)', type: 'textarea', required: false },
      { name: 'max_pages', label: 'Max Pages', type: 'number', required: false },
    ]
  },
  {
    id: 'db',
    name: 'Database',
    description: 'Connect to SQL databases',
    icon: Database,
    configFields: [
      { name: 'host', label: 'Host', type: 'text', required: true },
      { name: 'port', label: 'Port', type: 'number', required: true },
      { name: 'database', label: 'Database', type: 'text', required: true },
      { name: 'username', label: 'Username', type: 'text', required: true },
      { name: 'password', label: 'Password', type: 'password', required: true },
    ]
  },
  {
    id: 'confluence',
    name: 'Confluence',
    description: 'Import from Confluence pages',
    icon: FileText,
    configFields: [
      { name: 'base_url', label: 'Base URL', type: 'url', required: true },
      { name: 'username', label: 'Username', type: 'text', required: true },
      { name: 'api_token', label: 'API Token', type: 'password', required: true },
      { name: 'space_keys', label: 'Space Keys (comma-separated)', type: 'text', required: false },
    ]
  },
  {
    id: 'sharepoint',
    name: 'SharePoint',
    description: 'Import from SharePoint sites',
    icon: Share,
    configFields: [
      { name: 'site_url', label: 'Site URL', type: 'url', required: true },
      { name: 'client_id', label: 'Client ID', type: 'text', required: true },
      { name: 'client_secret', label: 'Client Secret', type: 'password', required: true },
      { name: 'tenant_id', label: 'Tenant ID', type: 'text', required: true },
    ]
  },
  {
    id: 'folder',
    name: 'Local Folder',
    description: 'Import files from local directory',
    icon: Folder,
    configFields: [
      { name: 'path', label: 'Folder Path', type: 'text', required: false, placeholder: 'Optional - leave empty for upload mode' },
      { name: 'file_types', label: 'File Types (comma-separated)', type: 'text', required: false },
    ]
  },
  {
    id: 'aws_s3',
    name: 'AWS S3',
    description: 'Connect to AWS S3 buckets',
    icon: Cloud,
    configFields: [
      { name: 'bucket_name', label: 'Bucket Name', type: 'text', required: true },
      { name: 'access_key_id', label: 'AWS Access Key ID', type: 'text', required: true },
      { name: 'secret_access_key', label: 'AWS Secret Access Key', type: 'password', required: true },
      { name: 'region', label: 'Region', type: 'text', required: false, placeholder: 'us-east-1' },
      { name: 'prefix', label: 'Prefix/Path', type: 'text', required: false },
    ]
  },
  {
    id: 'azure_blob',
    name: 'Azure Blob Storage',
    description: 'Connect to Azure Blob Storage containers',
    icon: Cloud,
    configFields: [
      { name: 'storage_account_name', label: 'Storage Account Name', type: 'text', required: true },
      { name: 'container_name', label: 'Container Name', type: 'text', required: true },
      { name: 'account_key', label: 'Account Key', type: 'password', required: true },
      { name: 'prefix', label: 'Prefix/Path', type: 'text', required: false },
    ]
  },
  {
    id: 'google_drive',
    name: 'Google Drive',
    description: 'Connect to Google Drive folders',
    icon: Folder,
    configFields: [
      { name: 'folder_id', label: 'Folder ID', type: 'text', required: false, placeholder: 'Leave empty for root' },
      { name: 'credentials', label: 'OAuth Credentials (JSON)', type: 'textarea', required: true, placeholder: 'Paste OAuth credentials JSON here' },
    ]
  },
  {
    id: 'custom',
    name: 'Custom',
    description: 'Custom data source configuration',
    icon: HardDrive,
    configFields: [
      { name: 'config', label: 'Configuration (JSON)', type: 'textarea', required: true },
    ]
  }
]

export default function EditDataSourcePage() {
  const { user } = useDefaultUser()
  const navigate = useNavigate()
  const params = useParams()
  const productId = params.id as string
  const datasourceId = params.datasourceId as string
  
  const [dataSource, setDataSource] = useState<DataSource | null>(null)
  const [product, setProduct] = useState<any>(null)
  const [config, setConfig] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  
  // Modal states
  const [showResultModal, setShowResultModal] = useState(false)
  const [resultModalData, setResultModalData] = useState<{
    type: 'success' | 'error' | 'warning' | 'info'
    title: string
    message: string
  } | null>(null)

  useEffect(() => {
    if (productId && datasourceId) {
      loadProduct()
      loadDataSource()
    }
  }, [productId, datasourceId])

  const loadProduct = async () => {
    try {
      const response = await apiClient.getProduct(productId)
      if (response.data) {
        setProduct(response.data)
      }
    } catch (err) {
      console.error('Failed to load product:', err)
    }
  }

  const loadDataSource = async () => {
    try {
      console.log('Loading data source:', datasourceId)
      const response = await apiClient.getDataSource(datasourceId)
      console.log('Data source response:', response)
      
      if (response.error) {
        console.error('Data source error:', response.error)
        setError(response.error)
      } else if (response.data) {
        const data = response.data as DataSource
        console.log('Data source data:', data)
        setDataSource(data)
        setConfig(data.config || {})
      } else {
        console.error('No data in response:', response)
        setError('No data received from server')
      }
    } catch (err) {
      console.error('Failed to load data source:', err)
      setError('Failed to load data source')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6 flex items-center justify-center min-h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#C8102E] mx-auto mb-4"></div>
            <p className="text-gray-600">Loading data source...</p>
          </div>
        </div>
      </AppLayout>
    )
  }

  if (error || !dataSource) {
    return (
      <AppLayout>
        <div className="p-6 flex items-center justify-center min-h-96">
          <div className="text-center">
            <p className="text-red-600 mb-4">
              Error: {error || 'Data source not found'}
            </p>
            <p className="text-sm text-gray-500 mb-4">
              Data Source ID: {datasourceId}
            </p>
            <div className="space-x-3">
              <Link to={`/app/products/${productId}`}>
                <Button>Back to Product</Button>
              </Link>
              <Button 
                variant="outline" 
                onClick={() => {
                  setError(null)
                  setLoading(true)
                  loadDataSource()
                }}
              >
                Retry
              </Button>
            </div>
          </div>
        </div>
      </AppLayout>
    )
  }


  const selectedDataSourceType = DATA_SOURCE_TYPES.find(type => type.id === dataSource.type)

  const handleConfigChange = (fieldName: string, value: any) => {
    setConfig(prev => ({
      ...prev,
      [fieldName]: value
    }))
    // Clear test result when config changes
    setTestResult(null)
    // Clear field error when user starts typing
    if (fieldErrors[fieldName]) {
      setFieldErrors(prev => {
        const newErrors = { ...prev }
        delete newErrors[fieldName]
        return newErrors
      })
    }
    // Clear general error
    if (error) {
      setError(null)
    }
  }

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    setError(null)

    try {
      // Call backend API to test connection
      const response = await apiClient.testConnection(datasourceId)
      
      if (response.error) {
        setTestResult({ 
          success: false, 
          message: response.error || 'Failed to test connection' 
        })
      } else if (response.data) {
        const result = response.data as { ok: boolean; message: string }
        setTestResult({ 
          success: result.ok, 
          message: result.message 
        })
      } else {
        setTestResult({ 
          success: false, 
          message: 'No response from server' 
        })
      }
    } catch (err: any) {
      console.error('Test connection error:', err)
      setTestResult({ 
        success: false, 
        message: err?.message || 'Failed to test connection. Please check your inputs and try again.' 
      })
    } finally {
      setTesting(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    // Prevent multiple submissions
    if (saving) return
    
    setSaving(true)
    setError(null)

    // Clear previous errors
    setFieldErrors({})
    setError(null)
    
    // Basic validation for required fields
    const requiredFields = selectedDataSourceType?.configFields.filter(field => field.required) || []
    const newFieldErrors: Record<string, string> = {}
    let firstInvalidField: string | null = null
    
    for (const field of requiredFields) {
      const value = config[field.name]
      const isEmpty = !value || 
        (typeof value === 'string' && !value.trim()) ||
        (typeof value === 'number' && isNaN(value)) ||
        (Array.isArray(value) && value.length === 0)
      
      if (isEmpty) {
        newFieldErrors[field.name] = `Please enter ${field.label.toLowerCase()}`
        if (!firstInvalidField) {
          firstInvalidField = field.name
        }
      }
    }
    
    if (Object.keys(newFieldErrors).length > 0) {
      setFieldErrors(newFieldErrors)
      setSaving(false)
      
      // Focus on the first invalid field
      if (firstInvalidField) {
        setTimeout(() => {
          const element = document.getElementById(firstInvalidField!)
          if (element) {
            element.focus()
          }
        }, 100)
      }
      return
    }

    try {
      const response = await apiClient.updateDataSource(datasourceId, config)

      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Update Failed',
          message: response.error
        })
        setShowResultModal(true)
      } else {
        setResultModalData({
          type: 'success',
          title: 'Data Source Updated',
          message: 'Data source has been successfully updated'
        })
        setShowResultModal(true)
        // Redirect back to product detail page after a short delay
        setTimeout(() => {
          navigate(`/app/products/${productId}`)
        }, 1500)
      }
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Update Failed',
        message: 'Failed to update data source'
      })
      setShowResultModal(true)
    } finally {
      setSaving(false)
    }
  }

  const renderConfigField = (field: any) => {
    const value = config[field.name] || ''
    const hasError = fieldErrors[field.name]
    const errorClass = hasError ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : ''

    switch (field.type) {
      case 'textarea':
        return (
          <Textarea
            id={field.name}
            value={value}
            onChange={(e) => handleConfigChange(field.name, e.target.value)}
            placeholder={field.name === 'headers' ? '{"User-Agent": "MyBot/1.0"}' : ''}
            className={`mt-1 ${errorClass}`}
          />
        )
      case 'checkbox':
        return (
          <input
            type="checkbox"
            id={field.name}
            checked={value}
            onChange={(e) => handleConfigChange(field.name, e.target.checked)}
            className="mt-1 h-4 w-4 text-[#C8102E] focus:ring-[#C8102E] border-gray-300 rounded"
          />
        )
      case 'number':
        return (
          <Input
            id={field.name}
            type="number"
            value={value}
            onChange={(e) => handleConfigChange(field.name, parseInt(e.target.value) || '')}
            className={`mt-1 ${errorClass}`}
          />
        )
      default:
        return (
          <Input
            id={field.name}
            type={field.type}
            value={value}
            onChange={(e) => handleConfigChange(field.name, e.target.value)}
            className={`mt-1 ${errorClass}`}
          />
        )
    }
  }

  return (
    <AppLayout>
      <div className="p-6">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link to="/app/products" className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Products
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <Link to={`/app/products/${productId}`} className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            {product?.name || 'Product'}
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">Edit Data Source</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center">
            <div className="bg-[#F5E6E8] rounded-lg p-2 mr-4">
              <Database className="h-6 w-6 text-[#C8102E]" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Edit Data Source</h1>
              <p className="text-sm text-gray-500 mt-1">Update data source configuration</p>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="max-w-4xl">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div className="flex items-center mb-4">
              <span className="text-2xl mr-3">
                {selectedDataSourceType?.icon && <selectedDataSourceType.icon className="h-8 w-8" />}
              </span>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  {selectedDataSourceType?.name} Configuration
                </h2>
                <p className="text-sm text-gray-600">{selectedDataSourceType?.description}</p>
              </div>
            </div>

            {selectedDataSourceType?.configFields.map((field) => (
              <div key={field.name} className="mb-4">
                <Label htmlFor={field.name} className="block text-sm font-medium text-gray-700">
                  {field.label} {field.required && <span className="text-red-500">*</span>}
                </Label>
                {renderConfigField(field)}
                {fieldErrors[field.name] && (
                  <p className="text-sm text-red-600 mt-1">{fieldErrors[field.name]}</p>
                )}
                {(field as any).description && (
                  <p className="mt-2 text-sm text-gray-500">{(field as any).description}</p>
                )}
              </div>
            ))}
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-red-600">{error}</p>
            </div>
          )}

          {testResult && (
            <div className={`border rounded-lg p-4 ${
              testResult.success 
                ? 'bg-green-50 border-green-200' 
                : 'bg-red-50 border-red-200'
            }`}>
              <div className="flex items-center">
                <div className={`flex-shrink-0 h-5 w-5 ${
                  testResult.success ? 'text-green-400' : 'text-red-400'
                }`}>
                  {testResult.success ? (
                    <svg fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                  ) : (
                    <svg fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                  )}
                </div>
                <div className="ml-3">
                  <p className={`text-sm font-medium ${
                    testResult.success ? 'text-green-800' : 'text-red-800'
                  }`}>
                    {testResult.success ? 'Configuration Valid' : 'Configuration Invalid'}
                  </p>
                  <p className={`text-sm ${
                    testResult.success ? 'text-green-700' : 'text-red-700'
                  }`}>
                    {testResult.message}
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-between items-center">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate(`/app/products/${productId}`)}
              disabled={saving || testing}
            >
              Cancel
            </Button>
            
            <div className="flex space-x-3">
              <Button
                type="button"
                variant="outline"
                onClick={handleTestConnection}
                disabled={saving || testing || !selectedDataSourceType?.configFields.every(field => 
                  !field.required || (config[field.name] && config[field.name].toString().trim())
                )}
              >
                {testing ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></div>
                    Testing...
                  </>
                ) : (
                  'Test Configuration'
                )}
              </Button>
              
              <Button
                type="submit"
                disabled={saving || testing}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </div>
        </form>
      </div>

      {/* Result Modal */}
      {resultModalData && (
        <ResultModal
          isOpen={showResultModal}
          onClose={() => {
            setShowResultModal(false)
            setResultModalData(null)
          }}
          title={resultModalData.title}
          message={resultModalData.message}
          type={resultModalData.type}
        />
      )}
      </div>
    </AppLayout>
  )
}
