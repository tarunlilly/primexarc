
import { useState, useEffect } from 'react'
import { useDefaultUser } from '@/lib/default-user-context'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { ArrowLeft, Database, Globe, HardDrive, FileText, Folder, Share, Cloud, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ResultModal } from '@/components/ui/modal'
import { ComingSoonBadgeInline } from '@/components/ui/coming-soon-badge-inline'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'

const DATA_SOURCE_TYPES = [
  {
    id: 'index_factory',
    name: 'Index Factory',
    description: 'Connect to Vector DB to store vectors',
    icon: Database,
    implemented: true,
    configFields: [
      { name: 'connection_url', label: 'Vector DB Connection URL', type: 'text', required: true, placeholder: 'http://localhost:6333' },
      { name: 'api_key', label: 'API Key', type: 'password', required: false },
      { name: 'collection_name', label: 'Collection Name', type: 'text', required: true, placeholder: 'my_vectors' },
      { name: 'vector_dimensions', label: 'Vector Dimensions', type: 'number', required: true, placeholder: '1536' },
      { name: 'distance_metric', label: 'Distance Metric', type: 'text', required: true, placeholder: 'cosine, euclidean, or dot_product' },
    ]
  },
  {
    id: 'edb',
    name: 'EDB',
    description: 'Enterprise Data Bridge with Raw and Refine zones',
    icon: Database,
    implemented: true,
    configFields: [
      { name: 'zone_type', label: 'Zone Type', type: 'text', required: true, placeholder: 'raw_zone or refine_zone' },
      { name: 's3_bucket_name', label: 'S3 Bucket Name', type: 'text', required: true },
      { name: 's3_region', label: 'S3 Region', type: 'text', required: true, placeholder: 'us-east-1' },
      { name: 's3_prefix', label: 'S3 Prefix/Path', type: 'text', required: false, placeholder: 'data/raw/' },
      { name: 'inclusion_patterns', label: 'Inclusion Patterns (comma-separated)', type: 'text', required: false, placeholder: '*.csv, *.json, *.parquet' },
      { name: 'exclusion_patterns', label: 'Exclusion Patterns (comma-separated)', type: 'text', required: false, placeholder: '*.tmp, *.log' },
    ]
  },
  {
    id: 'folder',
    name: 'Local Folder',
    description: 'Import files from local directory or upload files',
    icon: Folder,
    implemented: true,
    configFields: [
      { name: 'path', label: 'Folder Path', type: 'text', required: false, placeholder: 'Enter full server folder path (optional - leave empty to upload files)' },
      { name: 'file_types', label: 'File Types (comma-separated)', type: 'text', required: false },
      { name: 'recursive', label: 'Include Subfolders', type: 'checkbox', required: false },
    ]
  },
  // {
  //   id: 'aws_s3',
  //   name: 'AWS S3',
  //   description: 'Connect to AWS S3 buckets',
  //   icon: Cloud,
  //   implemented: true,
  //   configFields: [
  //     { name: 'bucket_name', label: 'Bucket Name', type: 'text', required: true },
  //     { name: 'access_key_id', label: 'AWS Access Key ID', type: 'text', required: true },
  //     { name: 'secret_access_key', label: 'AWS Secret Access Key', type: 'password', required: true },
  //     { name: 'region', label: 'Region', type: 'text', required: false, placeholder: 'us-east-1' },
  //     { name: 'prefix', label: 'Prefix/Path', type: 'text', required: false },
  //   ]
  // },
  {
    id: 'azure_blob',
    name: 'Azure Blob Storage',
    description: 'Connect to Azure Blob Storage containers',
    icon: Cloud,
    implemented: true,
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
    implemented: true,
    configFields: [
      { name: 'folder_id', label: 'Folder ID', type: 'text', required: false, placeholder: 'Leave empty for root' },
      { name: 'credentials', label: 'OAuth Credentials (JSON)', type: 'textarea', required: true, placeholder: 'Paste OAuth credentials JSON here' },
    ]
  },
];

export default function NewDataSourcePage() {
  const { user } = useDefaultUser()
  const navigate = useNavigate()
  const params = useParams()
  const productId = params.id as string

  const [name, setName] = useState<string>('')
  const [selectedType, setSelectedType] = useState<string | null>(null)
  const [config, setConfig] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [workspaceId, setWorkspaceId] = useState<string | null>(null)
  const [loadingProduct, setLoadingProduct] = useState(true)
  const [uploadMode, setUploadMode] = useState<'path' | 'upload'>('upload')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])

  // Modal states
  const [showResultModal, setShowResultModal] = useState(false)
  const [resultModalData, setResultModalData] = useState<{
    type: 'success' | 'error' | 'warning' | 'info'
    title: string
    message: string
  } | null>(null)

  // Load product to get workspace_id
  useEffect(() => {
    const loadProduct = async () => {
      if (!productId) return

      try {
        setLoadingProduct(true)
        const response = await apiClient.getProduct(productId)

        if (response.error) {
          setError(`Failed to load product: ${response.error}`)
        } else if (response.data) {
          const product = response.data as any
          setWorkspaceId(product.workspace_id)
        }
      } catch (err) {
        console.error('Failed to load product:', err)
        setError('Failed to load product information')
      } finally {
        setLoadingProduct(false)
      }
    }

    if (productId) {
      loadProduct()
    }
  }, [productId])

  if (loadingProduct) {
    return (
      <AppLayout>
        <div className="p-6 flex items-center justify-center min-h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#C8102E] mx-auto mb-4"></div>
            <p className="text-gray-600">Loading...</p>
          </div>
        </div>
      </AppLayout>
    )
  }

  const selectedDataSourceType = DATA_SOURCE_TYPES.find(type => type.id === selectedType)

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
    if (!selectedType) return

    // Validate required fields before testing
    const requiredFields = selectedDataSourceType?.configFields.filter(field => field.required) || []
    const missingFields: string[] = []

    for (const field of requiredFields) {
      const value = config[field.name]
      const isEmpty = !value ||
        (typeof value === 'string' && !value.trim()) ||
        (typeof value === 'number' && isNaN(value)) ||
        (Array.isArray(value) && value.length === 0)

      if (isEmpty) {
        missingFields.push(field.label)
      }
    }

    if (missingFields.length > 0) {
      setTestResult({
        success: false,
        message: `Please fill in required fields: ${missingFields.join(', ')}`
      })
      return
    }

    setTesting(true)
    setTestResult(null)
    setError(null)

    try {
      // Call backend API to test configuration
      const backendType = selectedType === 'edb' ? 'aws_s3' : selectedType
      const response = await apiClient.testConfig(backendType, config)

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
    if (loading) return

    setLoading(true)
    setError(null)

    // Get workspace ID from product (product already exists, so workspace exists)
    if (!workspaceId) {
      setError('Workspace ID not found. Please refresh the page.')
      setLoading(false)
      return
    }

    // Clear previous errors
    setFieldErrors({})
    setError(null)

    // Validate name field
    if (!name || !name.trim()) {
      setFieldErrors({ name: 'Please enter a name for the data source' })
      setLoading(false)
      return
    }

    // Special validation for folder datasource with file upload
    if (selectedType === 'folder' && uploadMode === 'upload') {
      if (selectedFiles.length === 0) {
        setError('Please select at least one file to upload')
        setLoading(false)
        return
      }
    } else {
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
        setLoading(false)

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
    }

    try {
      // Handle folder datasource with file upload
      if (selectedType === 'folder' && uploadMode === 'upload' && selectedFiles.length > 0) {
        // Create datasource without path
        const createResponse = await apiClient.createDataSource({
          workspace_id: workspaceId,
          product_id: productId,
          type: 'folder',
          config: {
            // No path for upload mode
            file_types: config.file_types || '',
            recursive: config.recursive || false
          },
          name: name.trim()
        })

        if (createResponse.error) {
          setResultModalData({
            type: 'error',
            title: 'Creation Failed',
            message: createResponse.error
          })
          setShowResultModal(true)
          setLoading(false)
          return
        }

        // Upload files
        if (createResponse.data) {
          const datasourceId = createResponse.data.id
          const uploadResponse = await apiClient.uploadFilesToDataSource(
            datasourceId,
            selectedFiles
          )

          if (uploadResponse.error) {
            setResultModalData({
              type: 'error',
              title: 'Upload Failed',
              message: uploadResponse.error
            })
            setShowResultModal(true)
          } else {
            setResultModalData({
              type: 'success',
              title: 'Data Source Created',
              message: `Data source created and ${uploadResponse.data?.uploaded_count || 0} file(s) uploaded successfully`
            })
            setShowResultModal(true)
            setTimeout(() => {
              navigate(`/app/products/${productId}`)
            }, 1500)
          }
        }
      } else {
        // Regular datasource creation
        // EDB uses aws_s3 as the backend type (IAM role-based, no credentials needed)
        const backendType = selectedType === 'edb' ? 'aws_s3' : selectedType!
        const response = await apiClient.createDataSource({
          workspace_id: workspaceId,
          product_id: productId,
          type: backendType,
          config: config,
          name: name.trim()
        })

        if (response.error) {
          setResultModalData({
            type: 'error',
            title: 'Creation Failed',
            message: response.error
          })
          setShowResultModal(true)
        } else {
          setResultModalData({
            type: 'success',
            title: 'Data Source Created',
            message: 'Data source has been successfully created'
          })
          setShowResultModal(true)
          // Redirect back to product detail page after a short delay
          setTimeout(() => {
            navigate(`/app/products/${productId}`)
          }, 1500)
        }
      }
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Creation Failed',
        message: 'Failed to create data source'
      })
      setShowResultModal(true)
    } finally {
      setLoading(false)
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
            placeholder={field.placeholder || (field.name === 'headers' ? '{"User-Agent": "MyBot/1.0"}' : '')}
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
            placeholder={field.placeholder || ''}
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
            placeholder={field.placeholder || ''}
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
            Product Details
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">Add Data Source</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Add Data Source</h1>
            <p className="text-gray-600 mt-1">Connect a new data source to your product</p>
          </div>
        </div>

        <div className="max-w-4xl">
        {!selectedType ? (
          // Type Selection
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Choose Data Source Type</h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {DATA_SOURCE_TYPES.map((type) => {
                  const IconComponent = type.icon
                  const isImplemented = type.implemented !== false
                  return (
                    <button
                      key={type.id}
                      onClick={() => {
                        if (isImplemented) {
                          setSelectedType(type.id)
                        }
                      }}
                      disabled={!isImplemented}
                      className={`text-left border rounded-lg p-6 transition-colors relative ${
                        isImplemented
                          ? 'border-gray-200 hover:bg-gray-50 hover:border-[#C8102E] cursor-pointer'
                          : 'border-gray-200 bg-gray-50 opacity-60 cursor-not-allowed'
                      }`}
                    >
                      {!isImplemented && (
                        <ComingSoonBadgeInline className="absolute top-3 right-3" />
                      )}
                      <div className="flex items-center mb-3">
                        <div className={`rounded-lg p-2 mr-3 ${
                          isImplemented ? 'bg-[#F5E6E8]' : 'bg-gray-200'
                        }`}>
                          <IconComponent className={`h-6 w-6 ${
                            isImplemented ? 'text-[#C8102E]' : 'text-gray-400'
                          }`} />
                        </div>
                        <div>
                          <h3 className={`font-medium ${
                            isImplemented ? 'text-gray-900' : 'text-gray-500'
                          }`}>
                            {type.name}
                          </h3>
                        </div>
                      </div>
                      <p className={`text-sm ${
                        isImplemented ? 'text-gray-600' : 'text-gray-400'
                      }`}>
                        {type.description}
                      </p>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        ) : (
          // Configuration Form
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="flex items-center mb-6">
                <div className="bg-[#F5E6E8] rounded-lg p-2 mr-3">
                  {selectedDataSourceType && (
                    <selectedDataSourceType.icon className="h-6 w-6 text-[#C8102E]" />
                  )}
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">
                    Configure {selectedDataSourceType?.name} Data Source
                  </h2>
                  <p className="text-gray-600">{selectedDataSourceType?.description}</p>
                </div>
              </div>

              <div className="space-y-4">
                {/* Name Field */}
                <div>
                  <Label htmlFor="name" className="text-sm font-medium text-gray-700">
                    Data Source Name
                    <span className="text-red-500 ml-1">*</span>
                  </Label>
                  <Input
                    id="name"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g., Customer Documents, Legal Contracts"
                    className={`mt-1 ${fieldErrors.name ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : ''}`}
                  />
                  {fieldErrors.name && (
                    <p className="text-sm text-red-600 mt-1">{fieldErrors.name}</p>
                  )}
                </div>

                {/* Folder datasource: Mode selector */}
                {selectedType === 'folder' && (
                  <div className="mb-4">
                    <Label className="block text-sm font-medium text-gray-700 mb-2">
                      Data Source Mode
                    </Label>
                    <div className="flex space-x-4">
                      <label className="flex items-center">
                        <input
                          type="radio"
                          name="folderMode"
                          value="upload"
                          checked={uploadMode === 'upload'}
                          onChange={(e) => setUploadMode(e.target.value as 'path' | 'upload')}
                          className="mr-2"
                        />
                        Upload Files from Local System
                      </label>
                      <label className="flex items-center">
                        <input
                          type="radio"
                          name="folderMode"
                          value="path"
                          checked={uploadMode === 'path'}
                          onChange={(e) => setUploadMode(e.target.value as 'path' | 'upload')}
                          className="mr-2"
                        />
                        Server Folder Path
                      </label>
                    </div>
                  </div>
                )}

                {/* Folder datasource: File upload UI */}
                {selectedType === 'folder' && uploadMode === 'upload' ? (
                  <div className="mb-4">
                    <Label htmlFor="files" className="block text-sm font-medium text-gray-700 mb-2">
                      Select Files <span className="text-red-500">*</span>
                    </Label>
                    <input
                      type="file"
                      id="files"
                      multiple
                      onChange={(e) => {
                        if (e.target.files) {
                          setSelectedFiles(Array.from(e.target.files))
                        }
                      }}
                      className="block w-full text-sm text-gray-500
                        file:mr-4 file:py-2 file:px-4
                        file:rounded-full file:border-0
                        file:text-sm file:font-semibold
                        file:bg-[#F5E6E8] file:text-[#C8102E]
                        hover:file:bg-[#F5E6E8]"
                    />
                    {selectedFiles.length > 0 && (
                      <div className="mt-2">
                        <p className="text-sm text-gray-600">
                          {selectedFiles.length} file(s) selected
                        </p>
                        <ul className="mt-1 text-sm text-gray-500 list-disc list-inside max-h-32 overflow-y-auto">
                          {selectedFiles.map((file, idx) => (
                            <li key={idx}>{file.name} ({(file.size / 1024).toFixed(2)} KB)</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : (
                  /* Configuration Fields */
                  selectedDataSourceType?.configFields.map((field) => (
                    <div key={field.name}>
                      <Label htmlFor={field.name} className="text-sm font-medium text-gray-700">
                        {field.label}
                        {field.required && <span className="text-red-500 ml-1">*</span>}
                      </Label>
                      {renderConfigField(field)}
                      {fieldErrors[field.name] && (
                        <p className="text-sm text-red-600 mt-1">{fieldErrors[field.name]}</p>
                      )}
                    </div>
                  ))
                )}
              </div>
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
                      {testResult.success ? 'Connection Test Successful' : 'Connection Test Failed'}
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
                onClick={() => setSelectedType(null)}
                disabled={loading || testing}
              >
                Back
              </Button>

              <div className="flex justify-end space-x-3">
                <Link to={`/app/products/${productId}`}>
                  <Button type="button" variant="outline">
                    Cancel
                  </Button>
                </Link>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleTestConnection}
                        disabled={loading || testing || !selectedDataSourceType?.configFields.every(field =>
                          !field.required || (config[field.name] && config[field.name].toString().trim())
                        )}
                >
                  {testing ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></div>
                      Testing...
                    </>
                  ) : (
                    'Test Connection'
                  )}
                </Button>

                <Button
                  type="submit"
                  disabled={loading || testing}
                >
                  {loading ? 'Creating...' : 'Create Data Source'}
                </Button>
              </div>
            </div>
          </form>
        )}
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
