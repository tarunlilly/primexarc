
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  HelpCircle,
  BookOpen,
  BarChart3,
  Database,
  Zap,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Info,
  Lightbulb,
  Target,
  Rocket,
  TrendingUp,
  Shield,
  Layers,
  FileText,
  Sparkles,
  Cpu,
  Globe,
  Settings,
  Search,
  ArrowLeft,
  Activity,
  XCircle,
  ChevronRight,
  Code,
  Star,
  CheckCircle,
  GitBranch,
  Eye,
  Users
} from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function HelpPage() {
  const navigate = useNavigate()
  
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    gettingStarted: true,
    understandingScores: true,  // Expanded by default for beginners
    metricsExplained: true,      // Expanded by default for beginners
    qualityImprovement: true,    // Expanded by default to show value
    playbookAutoDetection: true, // Expanded by default to show feature
    preprocessingDetails: false, // Detailed preprocessing documentation
    dataQualityRules: false,
    fingerprintArtifacts: false,
    aiLineage: true,             // AI Data Lineage - Expanded by default to showcase feature
    vectorization: false,
    contextEngineering: false,
    troubleshooting: false,
    bestPractices: false,
  })

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  const scrollTo = (id: string, expandKey?: string) => {
    if (expandKey) {
      setExpandedSections(prev => ({ ...prev, [expandKey]: true }))
    }
    // Let state update flush before scroll
    setTimeout(() => {
      const element = document.getElementById(id)
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }, 100)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-white via-white to-rose-100">
      <div className="container mx-auto px-3 sm:px-4 lg:px-6 py-12 max-w-7xl">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-[#C8102E] rounded-full mb-6">
            <HelpCircle className="h-10 w-10 text-white" />
          </div>
          <h1 className="text-5xl font-bold text-gray-900 mb-4">Help Center</h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Comprehensive guide to using PrimeData effectively
          </p>
        </div>

        {/* Top Actions */}
        <div className="flex items-center justify-between mb-8">
          <Button
            type="button"
            variant="outline"
            className="border-[#C8102E] text-[#C8102E] hover:bg-[#F5E6E8]"
            onClick={() => navigate(-1)}
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          {/* Left Sidebar Index */}
          <aside className="lg:w-72 flex-shrink-0">
            <div className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-5 sticky top-6">
              <h2 className="text-lg font-bold text-gray-900 mb-4">Topics</h2>
              <div className="space-y-2">
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('gettingStarted', 'gettingStarted')}
                >
                  Getting Started
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('understandingScores', 'understandingScores')}
                >
                  Understanding Scores
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('metricsExplained', 'metricsExplained')}
                >
                  Metrics Explained
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('qualityImprovement', 'qualityImprovement')}
                >
                  Quality Improvement Dashboard
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('playbookAutoDetection', 'playbookAutoDetection')}
                >
                  Playbook Auto-Detection
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('preprocessingDetails', 'preprocessingDetails')}
                >
                  Preprocessing Technical Details
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('dataQualityRules', 'dataQualityRules')}
                >
                  Data Quality Rules
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('fingerprintArtifacts', 'fingerprintArtifacts')}
                >
                  Fingerprint Artifacts
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('aiLineage', 'aiLineage')}
                >
                  AI Data Lineage
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('vectorization', 'vectorization')}
                >
                  Vectorization
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('contextEngineering', 'contextEngineering')}
                >
                  Context Engineering
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('troubleshooting', 'troubleshooting')}
                >
                  Troubleshooting
                </button>
                <button
                  className="w-full text-left px-3 py-2 rounded-lg border border-gray-200 hover:border-[#C8102E] hover:bg-[#F5E6E8]/40 transition-all text-sm font-medium text-gray-900"
                  onClick={() => scrollTo('bestPractices', 'bestPractices')}
                >
                  Best Practices
                </button>
              </div>
            </div>
          </aside>

          {/* Main Content */}
          <div className="flex-1 space-y-6">
          {/* Getting Started */}
          <section id="gettingStarted" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('gettingStarted')}
              className="w-full flex items-center justify-between text-left"
            >
              <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                <div className="bg-[#C8102E]/10 rounded-xl p-3">
                  <Rocket className="h-6 w-6 text-[#C8102E]" />
                </div>
                Getting Started
              </h2>
              {expandedSections.gettingStarted ? (
                <ChevronUp className="h-5 w-5 text-gray-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-400" />
              )}
            </button>

            {expandedSections.gettingStarted && (
              <div className="mt-8 space-y-8 text-gray-700">
                <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-6">
                  <h3 className="text-lg font-bold text-gray-900 mb-4">Quick Start Guide</h3>
                  <ol className="space-y-4 list-decimal list-inside">
                    <li className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">1</span>
                      <div>
                        <strong>Create a Data Product:</strong> Navigate to Products → New Product and provide a name and description.
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">2</span>
                      <div>
                        <strong>Add Data Sources:</strong> Connect your data sources (Index Factory for Vector DB, EDB for enterprise data zones, local folders, AWS S3, Azure Blob Storage, Google Drive).
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">3</span>
                      <div>
                        <strong>Configure Processing:</strong> Select a playbook and configure chunking/embedding settings.
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">4</span>
                      <div>
                        <strong>Run Pipeline:</strong> Start the pipeline to process your data.
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">5</span>
                      <div>
                        <strong>Review Scores:</strong> Check the AI Trust Score and detailed metrics.
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">6</span>
                      <div>
                        <strong>Export Vectors:</strong> Once ready, export your vector embeddings for use in RAG applications.
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">7</span>
                      <div>
                        <strong>Test in Playground:</strong> Use the Playground to test retrieval and RAG queries.
                      </div>
                    </li>
                  </ol>
                </div>

                {/* Beginner Quickstart Banner */}
                <div className="bg-gradient-to-r from-blue-500 to-indigo-600 rounded-xl p-6 text-white shadow-lg">
                  <div className="flex items-start gap-4">
                    <Lightbulb className="h-8 w-8 flex-shrink-0 mt-1" />
                    <div>
                      <h3 className="text-xl font-bold mb-2">New to PrimeData Metrics?</h3>
                      <p className="text-blue-100 mb-4">
                        Focus on these three "must-have" metrics first. Everything else is for optimization.
                      </p>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4 border border-white/20">
                          <div className="flex items-center gap-2 mb-2">
                            <Shield className="h-5 w-5" />
                            <div className="font-bold text-lg">1. Security</div>
                          </div>
                          <div className="text-sm text-blue-100 mb-1">Must be 100%</div>
                          <div className="text-xs text-blue-200">No sensitive data (PII) leaked</div>
                        </div>
                        <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4 border border-white/20">
                          <div className="flex items-center gap-2 mb-2">
                            <CheckCircle2 className="h-5 w-5" />
                            <div className="font-bold text-lg">2. Completeness</div>
                          </div>
                          <div className="text-sm text-blue-100 mb-1">Must be 100%</div>
                          <div className="text-xs text-blue-200">All content present & readable</div>
                        </div>
                        <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4 border border-white/20">
                          <div className="flex items-center gap-2 mb-2">
                            <Zap className="h-5 w-5" />
                            <div className="font-bold text-lg">3. Embedding Success</div>
                          </div>
                          <div className="text-sm text-blue-100 mb-1">Must be 100%</div>
                          <div className="text-xs text-blue-200">All chunks converted to vectors</div>
                        </div>
                      </div>
                      <p className="text-xs text-blue-200 mt-4">
                        💡 These are "hard blockers" - if any of these fail, your data won't work in AI applications.
                        Once these are at 100%, work on improving other metrics to enhance performance.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Database className="h-5 w-5 text-[#C8102E]" />
                    Data Processing Pipeline Architecture
                  </h3>
                  <p className="mb-4 text-gray-700">
                    PrimeData uses an 8-stage pipeline to transform raw data into production-ready AI assets:
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">1. Ingestion</h4>
                      <p className="text-sm text-gray-700">Download/upload files to object storage and create metadata records.</p>
                    </div>
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">2. Preprocessing</h4>
                      <p className="text-sm text-gray-700">Text normalization, OCR correction, metadata extraction, content type detection.</p>
                    </div>
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">3. Chunking</h4>
                      <p className="text-sm text-gray-700">Intelligent document chunking with multiple strategies (fixed-size, semantic, recursive).</p>
                    </div>
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">4. Scoring</h4>
                      <p className="text-sm text-gray-700">Comprehensive quality metrics calculation: Security, Completeness, Accuracy, Quality, Context Quality, Metadata Presence, Knowledge Base Ready, and technical metrics (Avg Chunk Coherence, Avg Noise-Free Score, Chunk Boundary Quality).</p>
                    </div>
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">5. Embedding</h4>
                      <p className="text-sm text-gray-700">Generate vector embeddings using OpenAI or open-source models.</p>
                    </div>
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">6. Indexing</h4>
                      <p className="text-sm text-gray-700">Store vectors in Qdrant vector database with metadata.</p>
                    </div>
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">7. Fingerprinting</h4>
                      <p className="text-sm text-gray-700">Generate comprehensive AI readiness fingerprint with all metrics.</p>
                    </div>
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">8. Validation</h4>
                      <p className="text-sm text-gray-700">Data quality validation and policy compliance checks.</p>
                    </div>
                  </div>
                </div>

                {/* Playbooks Section */}
                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Database className="h-5 w-5 text-[#C8102E]" />
                    Playbooks & Text Optimization
                  </h3>
                  <p className="mb-4 text-gray-700">
                    Playbooks are domain-specific configuration profiles that optimize data processing for different content types. Each playbook contains specialized text normalization rules, chunking strategies, and quality thresholds tailored to specific industries and document formats.
                  </p>

                  <div className="bg-blue-50 border-l-4 border-blue-500 rounded-lg p-5 mb-6">
                    <h4 className="font-bold text-gray-900 mb-3">What Playbooks Do</h4>
                    <ul className="list-disc list-inside space-y-2 text-sm text-gray-700 ml-2">
                      <li><strong>Text Normalization</strong> - Clean and standardize text (remove soft hyphens, fix line breaks, normalize quotes/dashes)</li>
                      <li><strong>Pattern Matching</strong> - Detect document type using domain-specific keywords and structures</li>
                      <li><strong>Header Detection</strong> - Identify section headers and document structure (markdown, numbered headings, all-caps)</li>
                      <li><strong>Chunking Configuration</strong> - Set optimal chunk sizes and overlap for the content type</li>
                      <li><strong>Quality Thresholds</strong> - Define minimum sections, boundary quality, and coherence requirements</li>
                      <li><strong>Noise Removal</strong> - Filter out boilerplate, page numbers, headers, footers, and navigation elements</li>
                    </ul>
                  </div>

                  <h4 className="font-bold text-gray-900 mb-3">Built-in Playbooks</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-4">
                      <h5 className="font-bold text-gray-900 mb-2">TECH</h5>
                      <p className="text-sm text-gray-700 mb-2">Technical documentation, APIs, architecture guides, best practices</p>
                      <p className="text-xs text-gray-600">• Sentence-based chunking (800 tokens)</p>
                      <p className="text-xs text-gray-600">• Detects: code blocks, markdown headings, technical terms</p>
                    </div>

                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-4">
                      <h5 className="font-bold text-gray-900 mb-2">LEGAL</h5>
                      <p className="text-sm text-gray-700 mb-2">Contracts, briefs, regulations with clause preservation</p>
                      <p className="text-xs text-gray-600">• Sentence-based chunking (1800 tokens)</p>
                      <p className="text-xs text-gray-600">• Detects: whereas, hereby, section numbers, legal terms</p>
                    </div>

                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-4">
                      <h5 className="font-bold text-gray-900 mb-2">FINANCIAL</h5>
                      <p className="text-sm text-gray-700 mb-2">Financial reports, earnings statements, investment documents</p>
                      <p className="text-xs text-gray-600">• Optimized for tables, numbers, and financial terminology</p>
                    </div>

                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-4">
                      <h5 className="font-bold text-gray-900 mb-2">HEALTHCARE</h5>
                      <p className="text-sm text-gray-700 mb-2">Medical records, clinical notes, research papers</p>
                      <p className="text-xs text-gray-600">• Preserves medical terminology and diagnostic codes</p>
                    </div>

                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-4">
                      <h5 className="font-bold text-gray-900 mb-2">REGULATORY</h5>
                      <p className="text-sm text-gray-700 mb-2">Compliance documents, policies, standards, audit reports</p>
                      <p className="text-xs text-gray-600">• Maintains regulatory structure and references</p>
                    </div>

                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-4">
                      <h5 className="font-bold text-gray-900 mb-2">SCANNED</h5>
                      <p className="text-sm text-gray-700 mb-2">OCR documents with formatting artifacts and scanning noise</p>
                      <p className="text-xs text-gray-600">• Aggressive text normalization and OCR correction</p>
                    </div>

                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-4">
                      <h5 className="font-bold text-gray-900 mb-2">ACADEMIC</h5>
                      <p className="text-sm text-gray-700 mb-2">Research papers, theses, educational materials</p>
                      <p className="text-xs text-gray-600">• Preserves citations, references, and academic structure</p>
                    </div>

                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-4">
                      <h5 className="font-bold text-gray-900 mb-2">ECOMMERCE & RETAIL</h5>
                      <p className="text-sm text-gray-700 mb-2">Product catalogs, descriptions, customer reviews</p>
                      <p className="text-xs text-gray-600">• Optimized for product attributes and metadata</p>
                    </div>
                  </div>

                  <div className="bg-green-50 border-l-4 border-green-500 rounded-lg p-5 mb-6">
                    <h4 className="font-bold text-gray-900 mb-3">Custom Playbooks</h4>
                    <p className="text-sm text-gray-700 mb-3">
                      You can create custom playbooks tailored to your specific domain or document type. Custom playbooks allow you to:
                    </p>
                    <ul className="list-disc list-inside space-y-1 text-sm text-gray-700 ml-2">
                      <li>Define custom text normalization patterns (regex-based)</li>
                      <li>Configure domain-specific probes and keywords</li>
                      <li>Set custom chunking parameters (token size, overlap)</li>
                      <li>Define section aliases and header detection rules</li>
                      <li>Specify audience rules for content categorization</li>
                      <li>Customize quality gates and coherence thresholds</li>
                    </ul>
                    <p className="text-xs text-gray-600 mt-3">
                      <strong>To create a custom playbook:</strong> Navigate to Settings → Playbooks → Create Custom Playbook, or use the API endpoint <code className="bg-white px-1 py-0.5 rounded">/api/v1/playbooks/custom</code>
                    </p>
                  </div>

                  <div className="bg-orange-50 border-l-4 border-orange-500 rounded-lg p-5">
                    <h4 className="font-bold text-gray-900 mb-3">Text Optimization Methods</h4>
                    <p className="text-sm text-gray-700 mb-3">
                      All playbooks apply these text optimization techniques during preprocessing:
                    </p>
                    <ul className="list-disc list-inside space-y-1 text-sm text-gray-700 ml-2">
                      <li><strong>Soft Hyphen Removal</strong> - Removes invisible soft hyphens (\\u00AD) that break word continuity</li>
                      <li><strong>Line Break Normalization</strong> - Joins hyphenated words across line breaks ("exam-\\nple" → "example")</li>
                      <li><strong>Smart Quote Normalization</strong> - Converts smart quotes (\\u2018\\u2019) to standard ASCII quotes</li>
                      <li><strong>Dash Normalization</strong> - Standardizes en-dashes (–) and em-dashes (—) to hyphens</li>
                      <li><strong>Whitespace Cleanup</strong> - Collapses multiple spaces/tabs, removes blank lines</li>
                      <li><strong>Page Marker Removal</strong> - Strips "Page X of Y", page breaks, and form feeds</li>
                      <li><strong>Mid-Sentence Hard Wrap Reduction</strong> - Joins lines that break mid-sentence while preserving paragraph breaks</li>
                      <li><strong>Boilerplate Filtering</strong> - Removes copyright notices, confidentiality headers, navigation elements</li>
                    </ul>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Understanding Scores */}
          <section id="understandingScores" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('understandingScores')}
              className="w-full flex items-center justify-between text-left"
            >
              <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                <div className="bg-[#C8102E]/10 rounded-xl p-3">
                  <BarChart3 className="h-6 w-6 text-[#C8102E]" />
                </div>
                Understanding Scores
              </h2>
              {expandedSections.understandingScores ? (
                <ChevronUp className="h-5 w-5 text-gray-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-400" />
              )}
            </button>

            {expandedSections.understandingScores && (
              <div className="mt-8 space-y-8 text-gray-700">
                {/* Beginner-friendly Score Interpretation Guide */}
                <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-6">
                  <h3 className="text-lg font-bold text-gray-900 mb-3">📊 How to Read Scores (0-100%)</h3>
                  <p className="text-sm text-gray-700 mb-4">
                    All metrics and scores are displayed as percentages from 0% to 100%. Here's what each range means:
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                    <div className="bg-white rounded-lg p-4 border-2 border-green-300">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                        <strong className="text-gray-900">90-100%</strong>
                      </div>
                      <p className="text-sm text-gray-700">Excellent - Production-ready quality. Safe to use in production AI applications.</p>
                    </div>
                    <div className="bg-white rounded-lg p-4 border-2 border-blue-300">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                        <strong className="text-gray-900">75-89%</strong>
                      </div>
                      <p className="text-sm text-gray-700">Good - Minor improvements recommended. Generally acceptable for production use.</p>
                    </div>
                    <div className="bg-white rounded-lg p-4 border-2 border-yellow-300">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-3 h-3 bg-yellow-500 rounded-full"></div>
                        <strong className="text-gray-900">60-74%</strong>
                      </div>
                      <p className="text-sm text-gray-700">Fair - Quality issues may affect retrieval and RAG outputs. Review recommended.</p>
                    </div>
                    <div className="bg-white rounded-lg p-4 border-2 border-red-300">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-3 h-3 bg-red-500 rounded-full"></div>
                        <strong className="text-gray-900">&lt; 60%</strong>
                      </div>
                      <p className="text-sm text-gray-700">Needs Work - Significant improvements required before production use.</p>
                    </div>
                  </div>
                  <div className="bg-white rounded-lg p-4 border border-[#C8102E]/30">
                    <p className="text-sm font-semibold text-[#C8102E] mb-2">💡 Quick Tip for Beginners:</p>
                    <p className="text-sm text-gray-700">
                      Focus first on <strong>Security</strong>, <strong>Completeness</strong>, and <strong>Embedding Success Rate</strong>.
                      These are "hard blockers" - if any of these fail, your data won't work well in AI applications. Once these are at 100%,
                      work on improving <strong>Avg Chunk Coherence</strong> and <strong>Quality</strong> to enhance RAG performance.
                    </p>
                  </div>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">AI Trust Score</h3>
                  <p className="mb-4 text-gray-700">
                    The AI Trust Score is a single number (0-100%) that tells you if your data is ready for AI applications.
                    Think of it like a health checkup score - higher is better!
                  </p>

                  {/* Simple Explanation */}
                  <div className="bg-blue-50 border-l-4 border-blue-500 rounded-lg p-5 mb-6">
                    <div className="flex items-start gap-3">
                      <Info className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <h4 className="font-bold text-gray-900 mb-2">How It Works (Simple Version)</h4>
                        <p className="text-sm text-gray-700 mb-3">
                          Your AI Trust Score is calculated by checking many different aspects of your data and combining them with weighted importance.
                          Some checks are more critical than others.
                        </p>
                        <p className="text-sm text-gray-700">
                          <strong>The formula:</strong> Take each metric score (0-100%), multiply by its importance weight, then add them all together.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Visual Weight Breakdown */}
                  <h4 className="font-bold text-gray-900 mb-4">What Goes Into Your Score</h4>
                  <div className="space-y-4 mb-6">
                    {/* Core Trust - 60% */}
                    <div className="bg-gradient-to-r from-blue-50 to-blue-100 rounded-lg p-4 border-2 border-blue-200">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <Shield className="h-5 w-5 text-blue-600" />
                          <span className="font-bold text-gray-900">Core Trust Metrics</span>
                        </div>
                        <span className="text-sm font-bold bg-blue-600 text-white px-3 py-1 rounded-full">60% weight</span>
                      </div>
                      <p className="text-xs text-gray-600 mb-3">These are the foundation - security, completeness, and quality of your content</p>
                      <div className="space-y-2 ml-4">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">🎯 Accuracy (Spelling & validation)</span>
                          <span className="font-mono font-semibold text-blue-700">15%</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">🔒 Security (No PII leaks)</span>
                          <span className="font-mono font-semibold text-blue-700">15%</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">✨ Quality (Readability)</span>
                          <span className="font-mono font-semibold text-blue-700">15%</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">📝 Completeness (Content present)</span>
                          <span className="font-mono font-semibold text-blue-700">10%</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">🔍 Context Quality (Rich details)</span>
                          <span className="font-mono font-semibold text-blue-700">5%</span>
                        </div>
                      </div>
                    </div>

                    {/* Technical Quality - 30% */}
                    <div className="bg-gradient-to-r from-purple-50 to-purple-100 rounded-lg p-4 border-2 border-purple-200">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <Layers className="h-5 w-5 text-purple-600" />
                          <span className="font-bold text-gray-900">Technical Quality Metrics</span>
                        </div>
                        <span className="text-sm font-bold bg-purple-600 text-white px-3 py-1 rounded-full">30% weight</span>
                      </div>
                      <p className="text-xs text-gray-600 mb-3">How well chunks are structured and connected</p>
                      <div className="space-y-2 ml-4">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">🧩 Avg Chunk Coherence (Sentences flow together)</span>
                          <span className="font-mono font-semibold text-purple-700">15%</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">🧹 Avg Noise-Free Score (Clean content)</span>
                          <span className="font-mono font-semibold text-purple-700">10%</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">📏 Chunk Boundary Quality (Good splits)</span>
                          <span className="font-mono font-semibold text-purple-700">5%</span>
                        </div>
                      </div>
                    </div>

                    {/* Governance - 10% */}
                    <div className="bg-gradient-to-r from-green-50 to-green-100 rounded-lg p-4 border-2 border-green-200">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <FileText className="h-5 w-5 text-green-600" />
                          <span className="font-bold text-gray-900">Governance Metrics</span>
                        </div>
                        <span className="text-sm font-bold bg-green-600 text-white px-3 py-1 rounded-full">10% weight</span>
                      </div>
                      <p className="text-xs text-gray-600 mb-3">Metadata and documentation completeness</p>
                      <div className="space-y-2 ml-4">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">📋 Metadata Presence (Tags & labels)</span>
                          <span className="font-mono font-semibold text-green-700">5%</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-700">✅ Knowledge Base Ready (Structured data)</span>
                          <span className="font-mono font-semibold text-green-700">5%</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Additional Metrics Note */}
                  <div className="bg-yellow-50 border-l-4 border-yellow-400 rounded-lg p-4 mb-6">
                    <div className="flex items-start gap-2">
                      <Info className="h-4 w-4 text-yellow-600 flex-shrink-0 mt-0.5" />
                      <div className="text-sm text-yellow-800">
                        <p className="font-semibold mb-1">Additional Monitoring Metrics</p>
                        <p>
                          <strong>Vector Metrics</strong> (Embedding Success, Dimension Consistency, Vector Quality) and
                          <strong> RAG Performance Metrics</strong> (Recall@K, Precision@K) are displayed separately in the dashboard
                          for monitoring but don't directly contribute to the AI Trust Score. They help you understand search performance.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Example Calculation */}
                  <div className="bg-gradient-to-r from-indigo-50 to-indigo-100 border-2 border-indigo-200 rounded-lg p-5">
                    <h4 className="font-bold text-gray-900 mb-3 flex items-center gap-2">
                      <Sparkles className="h-5 w-5 text-indigo-600" />
                      Example Calculation
                    </h4>
                    <p className="text-sm text-gray-700 mb-3">
                      Let's say your metrics are:
                    </p>
                    <div className="bg-white rounded-lg p-4 mb-3 text-sm space-y-1">
                      <div className="flex justify-between">
                        <span>Accuracy: <strong>95%</strong></span>
                        <span className="text-gray-500">× 15% weight = 14.25</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Security: <strong>100%</strong></span>
                        <span className="text-gray-500">× 15% weight = 15.00</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Quality: <strong>88%</strong></span>
                        <span className="text-gray-500">× 15% weight = 13.20</span>
                      </div>
                      <div className="flex justify-between text-gray-600">
                        <span>... (all other metrics)</span>
                        <span>= their contributions</span>
                      </div>
                      <div className="border-t-2 border-indigo-300 mt-2 pt-2 flex justify-between font-bold text-indigo-700">
                        <span>Final AI Trust Score:</span>
                        <span className="text-xl">87.5%</span>
                      </div>
                    </div>
                    <p className="text-xs text-gray-600">
                      This score means your data is <strong>production-ready</strong> (above 80%) with room for optimization.
                    </p>
                  </div>

                  {/* Technical Formula (Collapsed by default) */}
                  <details className="mt-6 bg-gray-50 rounded-lg p-4 border border-gray-200">
                    <summary className="cursor-pointer font-semibold text-gray-900 flex items-center gap-2">
                      <Cpu className="h-4 w-4" />
                      Technical Formula (For Developers)
                    </summary>
                    <div className="mt-3 font-mono text-xs text-gray-800 bg-white rounded p-3">
                      <strong>AI_Trust_Score = Σ(metric<sub>i</sub> × weight<sub>i</sub>)</strong>
                      <br /><br />where:
                      <br />• metric<sub>i</sub> = individual metric value (normalized to 0-1)
                      <br />• weight<sub>i</sub> = configured weight for metric i
                      <br />• Σ = sum of all weighted metrics
                      <br />• All weights sum to 1.0 (100%)
                      <br /><br />
                      Result is clipped to [0, 1] range and multiplied by 100 for percentage display.
                    </div>
                  </details>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <div className="flex-shrink-0 w-7 h-7 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">1</div>
                    Step 1: Chunk-Level Scoring
                  </h3>
                  <div className="space-y-4">
                    <p className="text-sm text-gray-700 mb-4">
                      Each text chunk is evaluated against 13 core data quality metrics (0-100 scale). Each metric is calculated independently using specific algorithms:
                    </p>
                    
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <p className="font-semibold text-gray-900 mb-2">Chunk-Level Metric Calculation</p>
                      <div className="bg-white rounded-lg p-3 font-mono text-xs text-gray-800 mb-2">
                        For each chunk c:
                        <br />Completeness(c) = 100 if len(c.strip()) &gt; 0, else 0
                        <br />Security(c) = 100 if PII_detected == 0, else 75
                        <br />Quality(c) = f(avg_sentence_length, reading_ease, vocabulary_diversity)
                        <br />Accuracy(c) = (valid_patterns / total_patterns) × 100
                        <br />Context_Quality(c) = base_score + structure_bonus + info_density
                        <br />Metadata_Presence(c) = (populated_fields / expected_fields) × 100
                        <br />... (see Metrics Explained section for full formulas)
                      </div>
                      <p className="text-xs text-gray-600 mt-2">
                        All metrics are calculated on a per-chunk basis, producing a score between 0-100 for each metric.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <div className="flex-shrink-0 w-7 h-7 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">2</div>
                    Step 2: Chunk-Level AI Trust Score
                  </h3>
                  <div className="space-y-4">
                    <p className="text-sm text-gray-700 mb-4">
                      A weighted average of all chunk-level metrics creates the chunk's AI Trust Score. Default weights are configurable via <code className="bg-gray-100 px-1 rounded text-xs">backend/config/scoring_weights.json</code>.
                    </p>
                    
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <p className="font-semibold text-gray-900 mb-2">Chunk AI Trust Score Formula</p>
                      <div className="bg-white rounded-lg p-3 font-mono text-xs text-gray-800 mb-2">
                        <strong>Chunk_AI_Trust_Score(c) = Σ(metric<sub>i</sub>(c) × weight<sub>i</sub>)</strong>
                        <br />where:
                        <br />- c = chunk
                        <br />- i ranges over all 13 data quality metrics
                        <br />- weight<sub>i</sub> = configured weight for metric i (default: 1/13 ≈ 0.077)
                        <br />- Σ weight<sub>i</sub> = 1.0 (weights normalized)
                      </div>
                      <p className="text-xs text-gray-600 mt-2">
                        <strong>Example:</strong> If a chunk has Completeness=100, Security=100, Quality=80, and all other metrics=75 with equal weights (1/13):
                        <br />Chunk_AI_Trust_Score = (100×1/13) + (100×1/13) + (80×1/13) + ... + (75×1/13) ≈ 82.3
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <div className="flex-shrink-0 w-7 h-7 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">3</div>
                    Step 3: Product-Level Aggregation
                  </h3>
                  <div className="space-y-4">
                    <p className="text-sm text-gray-700 mb-4">
                      Chunk scores are aggregated to produce product-level metrics using arithmetic mean (average) across all chunks.
                    </p>
                    
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <p className="font-semibold text-gray-900 mb-2">Product-Level Metric Aggregation</p>
                      <div className="bg-white rounded-lg p-3 font-mono text-xs text-gray-800 mb-2">
                        <strong>Product_Metric = (1/n) × Σ metric(c<sub>j</sub>)</strong>
                        <br />where:
                        <br />- n = total number of chunks
                        <br />- j ranges from 0 to n-1
                        <br />- metric(c<sub>j</sub>) = metric value for chunk j
                      </div>
                      <p className="text-xs text-gray-600 mt-2">
                        <strong>Example:</strong> If you have 100 chunks with Quality scores: [80, 85, 75, 90, ...]
                        <br />Product_Quality = (80 + 85 + 75 + 90 + ...) / 100 = 81.5
                      </p>
                      <p className="text-xs text-gray-600 mt-2">
                        This applies to all 13 data quality metrics, producing product-level averages for each metric.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <div className="flex-shrink-0 w-7 h-7 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">4</div>
                    Step 4: AI-Ready & Vector Metrics
                  </h3>
                  <div className="space-y-4">
                    <p className="text-sm text-gray-700 mb-4">
                      After chunking and indexing, AI-Ready metrics and Vector metrics are calculated at the product level.
                    </p>
                    
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4 mb-4">
                      <p className="font-semibold text-gray-900 mb-2">AI-Ready Metrics</p>
                      <div className="bg-white rounded-lg p-3 font-mono text-xs text-gray-800 mb-2">
                        <strong>Chunk Coherence:</strong> (1/n) × Σ cos_sim(sentence<sub>i</sub>, sentence<sub>i+1</sub>)
                        <br /><strong>Noise-Free Score:</strong> (clean_content_length / total_content_length) × 100
                        <br /><strong>Boundary Quality:</strong> 100 - (mid_sentence_breaks / total_boundaries) × 100
                      </div>
                    </div>
                    
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <p className="font-semibold text-gray-900 mb-2">Vector Metrics (Post-Indexing)</p>
                      <div className="bg-white rounded-lg p-3 font-mono text-xs text-gray-800 mb-2">
                        <strong>Dimension Consistency:</strong> (vectors_with_correct_dim / total_vectors) × 100
                        <br /><strong>Success Rate:</strong> (successfully_embedded_chunks / total_chunks) × 100
                        <br /><strong>Vector Quality:</strong> 0.4×valid_ratio + 0.3×non_zero_ratio + 0.3×norm_health
                        <br /><strong>Model Health:</strong> f(embedding_variance, outlier_rate, api_error_rate)
                        <br /><strong>Semantic Search Readiness:</strong> 0.25×dim_consistency + 0.35×vector_quality + 0.25×model_health + 0.15×success_rate
                      </div>
                      <p className="text-xs text-gray-600 mt-2">
                        These metrics require successful vector indexing and are calculated after embeddings are generated and stored.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <div className="flex-shrink-0 w-7 h-7 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">5</div>
                    Step 5: Final AI Trust Score Calculation
                  </h3>
                  <div className="space-y-4">
                    <p className="text-sm text-gray-700 mb-4">
                      The final AI Trust Score combines all aggregated metrics (data quality, AI-ready, vector, and RAG metrics) with their respective weights.
                    </p>
                    
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <p className="font-semibold text-gray-900 mb-2">Final AI Trust Score Formula</p>
                      <div className="bg-white rounded-lg p-3 font-mono text-xs text-gray-800 mb-2">
                        <strong>AI_Trust_Score = Σ(metric<sub>i</sub> × weight<sub>i</sub>)</strong>
                        <br />
                        <br /><strong>Weight Breakdown:</strong>
                        <br />• Core Trust (60%): Accuracy(15%) + Secure(15%) + Quality(15%) + Completeness(10%) + Context_Quality(5%)
                        <br />• Technical Quality (30%): Avg_Chunk_Coherence(15%) + Avg_Noise_Free(10%) + Chunk_Boundary_Quality(5%)
                        <br />• Governance (10%): Metadata_Presence(5%) + KnowledgeBase_Ready(5%)
                        <br />
                        <br /><strong>Removed Metrics (No Longer Contribute):</strong>
                        <br />• Timeliness, Token_Count, Audience_Intentionality, Diversity, Audience_Accessibility
                        <br />• These metrics are no longer displayed in the UI
                      </div>
                      <p className="text-xs text-gray-600 mt-2">
                        <strong>Final Score Range:</strong> 0-100%, where 100% indicates perfect AI readiness across all active dimensions. Vector and RAG metrics are displayed separately for monitoring but do not contribute to the overall AI Trust Score.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Metrics Explained */}
          <section id="metricsExplained" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('metricsExplained')}
              className="w-full flex items-center justify-between text-left"
            >
              <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                <div className="bg-[#C8102E]/10 rounded-xl p-3">
                  <Target className="h-6 w-6 text-[#C8102E]" />
                </div>
                Metrics Explained
              </h2>
              {expandedSections.metricsExplained ? (
                <ChevronUp className="h-5 w-5 text-gray-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-400" />
              )}
            </button>

            {expandedSections.metricsExplained && (
              <div className="mt-8 space-y-6">
                {/* Governance Metrics */}
                <div className="bg-white border-2 border-blue-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-3">
                    <Shield className="h-6 w-6 text-[#C8102E]" />
                    Governance & Compliance Metrics
                  </h3>
                  <div className="space-y-6">
                    <div className="bg-blue-50 border-l-4 border-blue-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Security (Secure)</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Evaluates data privacy and security compliance by detecting personally identifiable information (PII).
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Binary classification based on PII detection patterns (emails, phone numbers, SSN, credit card numbers).
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula:</strong> Security = 100% if PII_count == 0, else 75% (penalty for detected PII)
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> ≥ 95% = Excellent, ≥ 75% = Good, &lt; 75% = Needs Review
                      </p>
                    </div>

                    <div className="bg-blue-50 border-l-4 border-blue-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Completeness</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Measures how complete and non-empty the content is. Essential for data quality assessment.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Content presence validation based on text length and non-whitespace characters.
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula:</strong> Completeness = 100% if len(text.strip()) &gt; 0, else 0%
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> 100% = Required (non-negotiable for valid content)
                      </p>
                    </div>

                    {/* Accuracy - Three-Tier Explanation */}
                    <div className="bg-blue-50 border-l-4 border-blue-500 rounded-lg p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <CheckCircle className="h-5 w-5 text-blue-600" />
                        <h4 className="font-bold text-gray-900">Accuracy: Is Your Data Valid & Correctly Formatted?</h4>
                      </div>

                      {/* Tier 1: Always Visible - Beginner-Friendly */}
                      <div className="mb-4">
                        <p className="text-sm text-gray-700 mb-3">
                          Accuracy checks if your data follows expected rules and patterns—like making sure dates are formatted correctly, phone numbers have the right digits, and values make logical sense.
                        </p>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <CheckCircle2 className="h-4 w-4 text-green-600" />
                              <span className="text-sm font-bold text-green-900">Accurate (95%)</span>
                            </div>
                            <p className="text-xs text-gray-700 mb-2">
                              "Contract dated 2024-01-15, value $50,000, contact: john@company.com, phone: (555) 123-4567"
                            </p>
                            <p className="text-xs text-green-700">✓ Valid date format, email, phone, currency</p>
                          </div>

                          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <XCircle className="h-4 w-4 text-red-600" />
                              <span className="text-sm font-bold text-red-900">Inaccurate (60%)</span>
                            </div>
                            <p className="text-xs text-gray-700 mb-2">
                              "Contract dated 2024-13-45, value $50000abc, contact: johncompany.com, phone: 555"
                            </p>
                            <p className="text-xs text-red-700">✗ Invalid date, malformed email, incomplete phone</p>
                          </div>
                        </div>

                        <div className="bg-white border border-blue-200 rounded-lg p-4 mb-4">
                          <p className="text-sm font-bold text-blue-900 mb-3">What We Validate:</p>
                          <div className="grid grid-cols-2 gap-2 text-xs text-gray-700">
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-blue-600 mt-0.5" />
                              <span>Date & time formats (ISO 8601)</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-blue-600 mt-0.5" />
                              <span>Email addresses (valid structure)</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-blue-600 mt-0.5" />
                              <span>Phone numbers (regional formats)</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-blue-600 mt-0.5" />
                              <span>Currency values (proper symbols)</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-blue-600 mt-0.5" />
                              <span>URLs (valid protocols)</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-blue-600 mt-0.5" />
                              <span>Data type consistency</span>
                            </div>
                          </div>
                        </div>

                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Lightbulb className="h-4 w-4 text-blue-600" />
                            <span className="text-sm font-bold text-blue-900">To Improve</span>
                          </div>
                          <ul className="text-xs text-gray-700 space-y-1">
                            <li>• Clean source data before ingestion (validate externally)</li>
                            <li>• Fix OCR errors that corrupt formatted data</li>
                            <li>• Ensure consistent date/time formats across documents</li>
                            <li>• Use structured data sources (JSON, XML) when possible</li>
                          </ul>
                        </div>
                      </div>

                      {/* Tier 2: Expandable - How It Works */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-sm font-semibold text-blue-700 hover:text-blue-900 flex items-center gap-2">
                          <ChevronRight className="h-4 w-4" />
                          How We Calculate It (Click to expand)
                        </summary>
                        <div className="mt-3 pl-6 space-y-3">
                          <p className="text-sm text-gray-700">
                            We run pattern-matching rules on your content and count how many pass:
                          </p>

                          <div className="bg-blue-100 border border-blue-300 rounded-lg p-3">
                            <p className="text-xs font-bold text-blue-900 mb-2">Example Validation Check:</p>
                            <div className="space-y-1 text-xs text-gray-700">
                              <p><strong>Chunk contains:</strong></p>
                              <p>• 10 dates → 9 valid ✓, 1 malformed ✗</p>
                              <p>• 5 emails → 5 valid ✓</p>
                              <p>• 3 phone numbers → 2 valid ✓, 1 incomplete ✗</p>
                              <p>• 8 URLs → 7 valid ✓, 1 broken ✗</p>
                              <p className="mt-2 pt-2 border-t border-blue-400 font-bold text-blue-700">
                                → Total: 23 valid / 26 total patterns = <span className="text-lg">88.5%</span> ✓
                              </p>
                            </div>
                          </div>

                          <p className="text-xs text-gray-600 italic">
                            Think of it like spell-check, but for data patterns instead of words.
                          </p>
                        </div>
                      </details>

                      {/* Tier 3: Technical Details - Nested Collapsible */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-xs font-semibold text-gray-600 hover:text-gray-900 flex items-center gap-2">
                          <Code className="h-3 w-3" />
                          Technical Details (For developers)
                        </summary>
                        <div className="mt-3 pl-6 bg-gray-50 rounded-lg p-3 font-mono text-xs text-gray-800">
                          <p className="mb-2"><strong>Implementation:</strong></p>
                          <ul className="list-disc list-inside space-y-1 mb-3">
                            <li>Regex pattern matching for common data types</li>
                            <li>ISO 8601 date/time validation</li>
                            <li>RFC 5322 email validation</li>
                            <li>Libphonenumber for phone number parsing</li>
                            <li>Domain-specific rule engines (extensible)</li>
                          </ul>

                          <p className="mb-2"><strong>Formula:</strong></p>
                          <div className="bg-white rounded p-2 mb-2">
                            <p>Accuracy = (valid_patterns / total_patterns) × 100</p>
                          </div>

                          <p className="mb-1"><strong>Source:</strong> <code>scoring_utils.py</code></p>
                        </div>
                      </details>

                      {/* Threshold Guide */}
                      <div className="text-xs text-gray-600 bg-white rounded-lg p-3 border border-gray-200">
                        <strong>Score Guide:</strong> ≥ 90% = Excellent | ≥ 75% = Good | &lt; 75% = Needs Improvement
                      </div>
                    </div>

                    <div className="bg-blue-50 border-l-4 border-blue-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Metadata Presence</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Quantifies the presence and richness of metadata (source, timestamp, section, author, etc.). Critical for traceability.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Percentage of expected metadata fields populated with non-null values.
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula:</strong> Metadata_Presence = (populated_fields / expected_fields) × 100
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> ≥ 80% = Excellent, ≥ 60% = Good, &lt; 60% = Needs Enhancement
                      </p>
                    </div>
                  </div>
                </div>

                {/* Content Quality Metrics */}
                <div className="bg-white border-2 border-green-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-3">
                    <FileText className="h-6 w-6 text-[#C8102E]" />
                    Content Quality Metrics
                  </h3>
                  <div className="space-y-6">
                    {/* Quality - Three-Tier Explanation */}
                    <div className="bg-green-50 border-l-4 border-green-500 rounded-lg p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Star className="h-5 w-5 text-green-600" />
                        <h4 className="font-bold text-gray-900">Quality: Is Your Content Easy to Read & Understand?</h4>
                      </div>

                      {/* Tier 1: Always Visible - Beginner-Friendly */}
                      <div className="mb-4">
                        <p className="text-sm text-gray-700 mb-3">
                          Great content uses clear sentences, varied vocabulary, and readable structure. Think of quality like readability—can your audience easily understand and process the information?
                        </p>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <CheckCircle2 className="h-4 w-4 text-green-600" />
                              <span className="text-sm font-bold text-green-900">High Quality (85%)</span>
                            </div>
                            <p className="text-xs text-gray-700 italic mb-2">
                              "Our platform simplifies data management. Users can upload, process, and analyze files in minutes. The intuitive interface requires no technical expertise."
                            </p>
                            <p className="text-xs text-green-700">✓ Clear sentences, varied words, good flow</p>
                          </div>

                          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <XCircle className="h-4 w-4 text-red-600" />
                              <span className="text-sm font-bold text-red-900">Low Quality (50%)</span>
                            </div>
                            <p className="text-xs text-gray-700 italic mb-2">
                              "The data data system system works works well well and and also also helps helps users users."
                            </p>
                            <p className="text-xs text-red-700">✗ Repetitive, unclear, poor structure</p>
                          </div>
                        </div>

                        <div className="bg-white border border-green-200 rounded-lg p-4 mb-4">
                          <p className="text-sm font-bold text-green-900 mb-3">What We Check:</p>
                          <div className="space-y-2 text-xs text-gray-700">
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-green-600 mt-0.5" />
                              <div>
                                <span className="font-semibold">Sentence Length:</span> 10-30 words is optimal (not too short, not too long)
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-green-600 mt-0.5" />
                              <div>
                                <span className="font-semibold">Readability:</span> Clear language that's easy to understand
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-green-600 mt-0.5" />
                              <div>
                                <span className="font-semibold">Vocabulary Variety:</span> Uses diverse words (not repetitive)
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Lightbulb className="h-4 w-4 text-blue-600" />
                            <span className="text-sm font-bold text-blue-900">To Improve</span>
                          </div>
                          <ul className="text-xs text-gray-700 space-y-1">
                            <li>• Use source documents with proper editing and proofreading</li>
                            <li>• Avoid OCR errors that create garbled text</li>
                            <li>• Break up run-on sentences (aim for 15-25 words)</li>
                            <li>• Ensure diverse vocabulary (not copy-paste repetition)</li>
                          </ul>
                        </div>
                      </div>

                      {/* Tier 2: Expandable - How It Works */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-sm font-semibold text-green-700 hover:text-green-900 flex items-center gap-2">
                          <ChevronRight className="h-4 w-4" />
                          How We Calculate It (Click to expand)
                        </summary>
                        <div className="mt-3 pl-6 space-y-3">
                          <p className="text-sm text-gray-700">
                            We combine three readability signals:
                          </p>

                          <div className="space-y-2">
                            <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                              <p className="text-xs font-bold text-green-900 mb-1">1. Sentence Length Check</p>
                              <p className="text-xs text-gray-700 mb-2">Optimal range: 10-30 words per sentence</p>
                              <p className="text-xs text-gray-600 italic">
                                Too short ({'<'}10): Choppy, feels abrupt<br />
                                Just right (10-30): Natural, easy to follow<br />
                                Too long ({'>'}30): Hard to follow, loses reader
                              </p>
                            </div>

                            <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                              <p className="text-xs font-bold text-green-900 mb-1">2. Reading Ease (Flesch Score)</p>
                              <p className="text-xs text-gray-700">Measures how easy text is to understand (considers word complexity and sentence length)</p>
                            </div>

                            <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                              <p className="text-xs font-bold text-green-900 mb-1">3. Vocabulary Richness</p>
                              <p className="text-xs text-gray-700">Do you use many different words, or repeat the same ones?</p>
                            </div>
                          </div>

                          <div className="bg-green-100 border border-green-300 rounded-lg p-3 mt-3">
                            <p className="text-xs font-bold text-green-900 mb-2">Example:</p>
                            <div className="space-y-1 text-xs text-gray-700">
                              <p><strong>Chunk:</strong> 10 sentences, avg 18 words each ✓</p>
                              <p><strong>Flesch Score:</strong> 65 (Standard readability) ✓</p>
                              <p><strong>Unique Words:</strong> 85% (high variety) ✓</p>
                              <p className="mt-2 pt-2 border-t border-green-400 font-bold text-green-700">
                                → Quality Score: <span className="text-lg">82%</span> ✓
                              </p>
                            </div>
                          </div>
                        </div>
                      </details>

                      {/* Tier 3: Technical Details - Nested Collapsible */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-xs font-semibold text-gray-600 hover:text-gray-900 flex items-center gap-2">
                          <Code className="h-3 w-3" />
                          Technical Details (For developers)
                        </summary>
                        <div className="mt-3 pl-6 bg-gray-50 rounded-lg p-3 font-mono text-xs text-gray-800">
                          <p className="mb-2"><strong>Implementation:</strong></p>
                          <ul className="list-disc list-inside space-y-1 mb-3">
                            <li>Flesch Reading Ease formula for readability</li>
                            <li>Sentence length analysis with optimal range scoring</li>
                            <li>Type-Token Ratio (TTR) for vocabulary diversity</li>
                          </ul>

                          <p className="mb-2"><strong>Formula:</strong></p>
                          <div className="bg-white rounded p-2 mb-2">
                            <p>Quality = f(avg_sentence_length, reading_ease_score, vocabulary_richness)</p>
                            <p className="text-xs text-gray-600 mt-1">where optimal sentence length ∈ [10, 30] words</p>
                          </div>

                          <p className="mb-1"><strong>Source:</strong> <code>scoring_utils.py</code></p>
                        </div>
                      </details>

                      {/* Threshold Guide */}
                      <div className="text-xs text-gray-600 bg-white rounded-lg p-3 border border-gray-200">
                        <strong>Score Guide:</strong> ≥ 80% = Excellent | ≥ 65% = Good | &lt; 65% = Needs Improvement
                      </div>
                    </div>

                    {/* Context Quality - Three-Tier Explanation */}
                    <div className="bg-green-50 border-l-4 border-green-500 rounded-lg p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <FileText className="h-5 w-5 text-green-600" />
                        <h4 className="font-bold text-gray-900">Context Quality: How Rich & Informative Is Your Content?</h4>
                      </div>

                      {/* Tier 1: Always Visible - Beginner-Friendly */}
                      <div className="mb-4">
                        <p className="text-sm text-gray-700 mb-3">
                          Great content isn't just grammatically correct—it's packed with useful details like numbers, dates, references, and well-structured information. This metric checks if your chunks have enough substance to be valuable.
                        </p>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <CheckCircle2 className="h-4 w-4 text-green-600" />
                              <span className="text-sm font-bold text-green-900">Rich Context (88%)</span>
                            </div>
                            <p className="text-xs text-gray-700 italic mb-2">
                              "In Q4 2023, revenue reached $2.5M (15% YoY growth). Key drivers included: 1) Enterprise sales (+40%), 2) Product launches in EU markets. See Appendix A for methodology."
                            </p>
                            <p className="text-xs text-green-700">✓ Numbers, dates, structure, references</p>
                          </div>

                          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <XCircle className="h-4 w-4 text-red-600" />
                              <span className="text-sm font-bold text-red-900">Poor Context (45%)</span>
                            </div>
                            <p className="text-xs text-gray-700 italic mb-2">
                              "Revenue increased last year. Sales were good. The company grew."
                            </p>
                            <p className="text-xs text-red-700">✗ Vague, no specifics, no structure</p>
                          </div>
                        </div>

                        <div className="bg-white border border-green-200 rounded-lg p-4 mb-4">
                          <p className="text-sm font-bold text-green-900 mb-3">What Makes Context "Rich"?</p>
                          <div className="grid grid-cols-2 gap-2 text-xs text-gray-700">
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-green-600 mt-0.5" />
                              <span>Specific numbers & metrics</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-green-600 mt-0.5" />
                              <span>Clear structure (lists, paragraphs)</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-green-600 mt-0.5" />
                              <span>Dates & temporal context</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-green-600 mt-0.5" />
                              <span>References & citations</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-green-600 mt-0.5" />
                              <span>Technical terms & jargon</span>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-3 w-3 text-green-600 mt-0.5" />
                              <span>Contextual keywords</span>
                            </div>
                          </div>
                        </div>

                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Lightbulb className="h-4 w-4 text-blue-600" />
                            <span className="text-sm font-bold text-blue-900">To Improve</span>
                          </div>
                          <ul className="text-xs text-gray-700 space-y-1">
                            <li>• Ensure source documents include specific data (numbers, dates)</li>
                            <li>• Preserve formatting (lists, tables, section headers)</li>
                            <li>• Avoid over-processing that strips rich context</li>
                            <li>• Use playbooks that preserve structural elements</li>
                          </ul>
                        </div>
                      </div>

                      {/* Tier 2: Expandable - How It Works */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-sm font-semibold text-green-700 hover:text-green-900 flex items-center gap-2">
                          <ChevronRight className="h-4 w-4" />
                          How We Calculate It (Click to expand)
                        </summary>
                        <div className="mt-3 pl-6 space-y-3">
                          <p className="text-sm text-gray-700">
                            We analyze chunks for multiple quality signals and combine them:
                          </p>

                          <div className="space-y-2">
                            <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                              <p className="text-xs font-bold text-green-900 mb-1">1. Base Score (40%)</p>
                              <p className="text-xs text-gray-700">Minimum quality threshold—ensures basic readability and structure</p>
                            </div>

                            <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                              <p className="text-xs font-bold text-green-900 mb-1">2. Structure Bonus (20%)</p>
                              <p className="text-xs text-gray-700">Has paragraphs, lists, headings? (+10-20 points)</p>
                            </div>

                            <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                              <p className="text-xs font-bold text-green-900 mb-1">3. Information Density (15%)</p>
                              <p className="text-xs text-gray-700">Contains numbers, percentages, dates, measurements? (+5-15 points)</p>
                            </div>

                            <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                              <p className="text-xs font-bold text-green-900 mb-1">4. References (10%)</p>
                              <p className="text-xs text-gray-700">Mentions sources, citations, "See Section X"? (+5-10 points)</p>
                            </div>

                            <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                              <p className="text-xs font-bold text-green-900 mb-1">5. Contextual Keywords (15%)</p>
                              <p className="text-xs text-gray-700">Uses domain-specific terms and technical vocabulary? (+5-15 points)</p>
                            </div>
                          </div>

                          <div className="bg-green-100 border border-green-300 rounded-lg p-3 mt-3">
                            <p className="text-xs font-bold text-green-900 mb-2">Example Calculation:</p>
                            <div className="space-y-1 text-xs text-gray-700 font-mono">
                              <p>Base Score: 80/100 points</p>
                              <p>+ Structure: Has 3 lists → +15 points</p>
                              <p>+ Info Density: 12 numbers, 4 dates → +12 points</p>
                              <p>+ References: 2 citations → +8 points</p>
                              <p>+ Keywords: 8 technical terms → +10 points</p>
                              <p className="mt-2 pt-2 border-t border-green-400 font-bold text-green-700">
                                → Total: (80×0.4) + (15×0.2) + (12×0.15) + (8×0.1) + (10×0.15) = <span className="text-lg">86%</span> ✓
                              </p>
                            </div>
                          </div>
                        </div>
                      </details>

                      {/* Tier 3: Technical Details - Nested Collapsible */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-xs font-semibold text-gray-600 hover:text-gray-900 flex items-center gap-2">
                          <Code className="h-3 w-3" />
                          Technical Details (For developers)
                        </summary>
                        <div className="mt-3 pl-6 bg-gray-50 rounded-lg p-3 font-mono text-xs text-gray-800">
                          <p className="mb-2"><strong>Implementation:</strong></p>
                          <ul className="list-disc list-inside space-y-1 mb-3">
                            <li>Regex pattern matching for structural elements</li>
                            <li>Numeric entity extraction (dates, numbers, percentages)</li>
                            <li>Reference detection (citations, cross-references)</li>
                            <li>TF-IDF for contextual keyword scoring</li>
                          </ul>

                          <p className="mb-2"><strong>Formula:</strong></p>
                          <div className="bg-white rounded p-2 mb-2">
                            <p>Context_Quality = base_score(40%) + structure_bonus(20%) + info_density(15%) + references(10%) + contextual_keywords(15%)</p>
                          </div>

                          <p className="mb-1"><strong>Source:</strong> <code>scoring_utils.py</code></p>
                        </div>
                      </details>

                      {/* Threshold Guide */}
                      <div className="text-xs text-gray-600 bg-white rounded-lg p-3 border border-gray-200">
                        <strong>Score Guide:</strong> ≥ 85% = Excellent | ≥ 70% = Good | &lt; 70% = Needs Enhancement
                      </div>
                    </div>

                    <div className="bg-green-50 border-l-4 border-green-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Knowledge Base Ready</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Composite readiness score for knowledge base ingestion. Combines metadata, quality, and context quality.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Weighted combination of metadata presence (40%), content quality (40%), and context quality (20%).
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula:</strong> KBR = 0.4 × Metadata_Presence + 0.4 × Quality + 0.2 × Context_Quality
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> ≥ 85% = Ready, ≥ 70% = Acceptable, &lt; 70% = Needs Improvement
                      </p>
                    </div>
                  </div>
                </div>

                {/* Chunking Metrics */}
                <div className="bg-white border-2 border-purple-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-3">
                    <Layers className="h-6 w-6 text-[#C8102E]" />
                    Chunking & Structure Metrics
                  </h3>
                  <div className="space-y-6">
                    {/* Avg Chunk Coherence - Three-Tier Explanation */}
                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <BookOpen className="h-5 w-5 text-purple-600" />
                        <h4 className="font-bold text-gray-900">Avg Chunk Coherence: How Well Ideas Flow Together</h4>
                      </div>

                      {/* Tier 1: Always Visible - Beginner-Friendly */}
                      <div className="mb-4">
                        <p className="text-sm text-gray-700 mb-3">
                          Think of reading a book where each sentence naturally connects to the next. Good coherence means your content flows logically, making it easier for AI to understand and retrieve relevant information.
                        </p>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <CheckCircle2 className="h-4 w-4 text-green-600" />
                              <span className="text-sm font-bold text-green-900">Good (75%)</span>
                            </div>
                            <p className="text-xs text-gray-700 italic">
                              "The company reported strong Q4 earnings. Revenue increased 15% year-over-year. This growth was driven by new product launches."
                            </p>
                            <p className="text-xs text-green-700 mt-2">✓ Each sentence builds on the previous one</p>
                          </div>

                          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <XCircle className="h-4 w-4 text-red-600" />
                              <span className="text-sm font-bold text-red-900">Bad (35%)</span>
                            </div>
                            <p className="text-xs text-gray-700 italic">
                              "The company reported earnings. Our vacation policy changed. The weather is nice."
                            </p>
                            <p className="text-xs text-red-700 mt-2">✗ Random topics, no connection</p>
                          </div>
                        </div>

                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Lightbulb className="h-4 w-4 text-blue-600" />
                            <span className="text-sm font-bold text-blue-900">To Improve</span>
                          </div>
                          <ul className="text-xs text-gray-700 space-y-1">
                            <li>• Use semantic chunking (splits by topic, not arbitrary size)</li>
                            <li>• Increase overlap to 15-20% between chunks</li>
                            <li>• Choose content-appropriate playbook (TECH, LEGAL, etc.)</li>
                            <li>• Avoid mixing unrelated topics in the same document</li>
                          </ul>
                        </div>
                      </div>

                      {/* Tier 2: Expandable - How It Works */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-sm font-semibold text-purple-700 hover:text-purple-900 flex items-center gap-2">
                          <ChevronRight className="h-4 w-4" />
                          How We Calculate It (Click to expand)
                        </summary>
                        <div className="mt-3 pl-6 space-y-3">
                          <p className="text-sm text-gray-700">
                            We measure how similar consecutive sentences are to each other:
                          </p>
                          <ol className="text-sm text-gray-700 space-y-2 list-decimal list-inside">
                            <li><strong>Break chunk into sentences</strong> - Split text into individual sentences</li>
                            <li><strong>Compare each sentence to the next</strong> - Measure similarity using AI embeddings</li>
                            <li><strong>Ask: "How similar are these two sentences?"</strong> - Score from 0% (completely different) to 100% (identical)</li>
                            <li><strong>Average all comparisons</strong> - Calculate mean similarity across the chunk</li>
                          </ol>

                          <div className="bg-purple-100 border border-purple-300 rounded-lg p-3">
                            <p className="text-xs font-bold text-purple-900 mb-2">Example Comparison:</p>
                            <p className="text-xs text-gray-700 mb-1">
                              Sentence 1: <span className="italic">"AI transforms healthcare delivery"</span>
                            </p>
                            <p className="text-xs text-gray-700 mb-2">
                              Sentence 2: <span className="italic">"Machine learning improves diagnosis accuracy"</span>
                            </p>
                            <p className="text-xs text-green-700 font-bold">
                              → 82% similar (both about AI in medical field)
                            </p>
                          </div>

                          <p className="text-xs text-gray-600 italic">
                            The product-level score is the average coherence across all chunks in your dataset.
                          </p>
                        </div>
                      </details>

                      {/* Tier 3: Technical Details - Nested Collapsible */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-xs font-semibold text-gray-600 hover:text-gray-900 flex items-center gap-2">
                          <Code className="h-3 w-3" />
                          Technical Details (For developers)
                        </summary>
                        <div className="mt-3 pl-6 bg-gray-50 rounded-lg p-3 font-mono text-xs text-gray-800">
                          <p className="mb-2"><strong>Implementation:</strong></p>
                          <ul className="list-disc list-inside space-y-1 mb-3">
                            <li>Sentence embeddings using <code>all-MiniLM-L6-v2</code> model</li>
                            <li>Adaptive windowing (3-5 sentences) for context</li>
                            <li>Fallback to n-gram similarity if embeddings unavailable</li>
                          </ul>

                          <p className="mb-2"><strong>Formula:</strong></p>
                          <div className="bg-white rounded p-2 mb-2">
                            <p>Per-Chunk: Coherence(chunk) = (1/n) × Σ cos_sim(sentence<sub>i</sub>, sentence<sub>i+1</sub>)</p>
                            <p>where cos_sim(a, b) = (a · b) / (||a|| × ||b||)</p>
                            <p className="mt-2">Product-Level: Avg_Chunk_Coherence = (1/m) × Σ Coherence(chunk<sub>j</sub>)</p>
                            <p>where m = total number of chunks</p>
                          </div>

                          <p className="mb-1"><strong>Source:</strong> <code>chunk_coherence.py</code></p>
                        </div>
                      </details>

                      {/* Threshold Guide */}
                      <div className="text-xs text-gray-600 bg-white rounded-lg p-3 border border-gray-200">
                        <strong>Score Guide:</strong> ≥ 70% = Excellent | ≥ 50% = Good | &lt; 50% = Needs Improvement
                      </div>
                    </div>

                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Avg Noise-Free Score</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Average percentage of content free from boilerplate, navigation elements, headers, footers, and other non-informative noise across all chunks.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Product-level average of chunk-level noise-free scores. Each chunk is evaluated for noise patterns (copyright notices, navigation menus, page numbers, etc.) and scored based on clean content ratio.
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Per-Chunk Formula:</strong> Noise_Free_Score(chunk) = (clean_content_length / total_content_length) × 100
                        <br />where clean_content = total_content - noise_pattern_matches
                        <br />
                        <br /><strong>Product-Level Formula:</strong> Avg_Noise_Free_Score = (1/m) × Σ Noise_Free_Score(chunk<sub>j</sub>)
                        <br />where m = total number of chunks
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> ≥ 95% = Excellent, ≥ 85% = Good, &lt; 85% = Needs Cleaning
                      </p>
                      <p className="text-xs text-gray-600 mt-2">
                        <strong>Note:</strong> This is displayed as "Avg Noise-Free Score" in the UI (product-level average). Per-chunk values are stored internally but not shown.
                      </p>
                    </div>

                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Chunk Boundary Quality</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Measures quality of chunk boundaries across the entire product. Fewer mid-sentence breaks indicate better boundary placement, preserving semantic integrity and improving RAG performance.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Inverse of mid-sentence boundary rate across all chunks. Penalizes chunks that split sentences inappropriately.
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula:</strong> Boundary_Quality = 100% - (mid_sentence_breaks / total_boundaries) × 100
                        <br />Ideal: 0% mid-sentence breaks = 100% score
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> ≥ 95% = Excellent, ≥ 85% = Good, &lt; 85% = Needs Boundary Adjustment
                      </p>
                    </div>
                  </div>
                </div>

                {/* Vector Metrics */}
                <div className="bg-white border-2 border-orange-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-3">
                    <Database className="h-6 w-6 text-[#C8102E]" />
                    Vector & Embedding Metrics
                  </h3>
                  <div className="space-y-6">
                    <div className="bg-orange-50 border-l-4 border-orange-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Embedding Dimension Consistency</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Percentage of vectors with expected embedding dimension. Critical for vector database compatibility and retrieval consistency.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Ratio of vectors with correct dimension (e.g., 384 for MiniLM, 1536 for OpenAI ada-002) to total vectors.
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula:</strong> Dimension_Consistency = (vectors_with_correct_dim / total_vectors) × 100
                        <br />Expected dimensions: MiniLM=384, OpenAI-3-small=1536, OpenAI-3-large=3072
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> 100% = Required (must match configured model dimension)
                      </p>
                    </div>

                    {/* Vector Quality Score - Three-Tier Explanation */}
                    <div className="bg-orange-50 border-l-4 border-orange-500 rounded-lg p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Activity className="h-5 w-5 text-orange-600" />
                        <h4 className="font-bold text-gray-900">Vector Quality Score: Health Check for Your Data Fingerprints</h4>
                      </div>

                      {/* Tier 1: Always Visible - Beginner-Friendly */}
                      <div className="mb-4">
                        <p className="text-sm text-gray-700 mb-3">
                          Every chunk gets converted to a "data fingerprint" (vector) that AI uses to search and understand your content. This metric is like quality control in manufacturing—it checks if those fingerprints are valid and ready to use.
                        </p>

                        <div className="bg-white border border-orange-200 rounded-lg p-4 mb-4">
                          <p className="text-sm font-bold text-orange-900 mb-3">What We Check (Weighted Checklist):</p>
                          <div className="space-y-2">
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5" />
                              <div className="flex-1">
                                <p className="text-sm font-semibold text-gray-800">Valid Check (40%)</p>
                                <p className="text-xs text-gray-600">No broken data (NaN, Infinity, corrupted values)</p>
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5" />
                              <div className="flex-1">
                                <p className="text-sm font-semibold text-gray-800">Non-Zero Check (30%)</p>
                                <p className="text-xs text-gray-600">Fingerprints contain actual data (not empty)</p>
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5" />
                              <div className="flex-1">
                                <p className="text-sm font-semibold text-gray-800">Distribution Check (30%)</p>
                                <p className="text-xs text-gray-600">Sizes are consistent (no weird outliers)</p>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Lightbulb className="h-4 w-4 text-blue-600" />
                            <span className="text-sm font-bold text-blue-900">To Improve</span>
                          </div>
                          <ul className="text-xs text-gray-700 space-y-1">
                            <li>• Verify your API key is valid and active</li>
                            <li>• Check embedding model status (OpenAI, Azure, etc.)</li>
                            <li>• Re-run ingestion pipeline if vectors are corrupted</li>
                            <li>• Ensure consistent embedding model across all chunks</li>
                          </ul>
                        </div>
                      </div>

                      {/* Tier 2: Expandable - How It Works */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-sm font-semibold text-orange-700 hover:text-orange-900 flex items-center gap-2">
                          <ChevronRight className="h-4 w-4" />
                          How We Calculate It (Click to expand)
                        </summary>
                        <div className="mt-3 pl-6 space-y-3">
                          <p className="text-sm text-gray-700">
                            We run a three-part quality check and combine the results:
                          </p>

                          <div className="bg-orange-100 border border-orange-300 rounded-lg p-3">
                            <p className="text-xs font-bold text-orange-900 mb-2">Example Calculation:</p>
                            <div className="space-y-2 text-xs text-gray-700">
                              <p><strong>Sample Dataset:</strong> 1,000 chunks total</p>
                              <p>1️⃣ Valid Check: 980 valid / 1,000 = 98.0% ✓</p>
                              <p>2️⃣ Non-Zero Check: 995 non-zero / 1,000 = 99.5% ✓</p>
                              <p>3️⃣ Distribution Check: 95% healthy (5% outliers) ✓</p>
                              <p className="mt-2 pt-2 border-t border-orange-400 font-bold text-green-700">
                                → Score: (0.4 × 98) + (0.3 × 99.5) + (0.3 × 95) = <span className="text-lg">97.4%</span> ✓
                              </p>
                            </div>
                          </div>

                          <p className="text-xs text-gray-600 italic">
                            Think of it like a product inspection: each test has different importance (weights), and the final score tells you if the batch passes quality control.
                          </p>
                        </div>
                      </details>

                      {/* Tier 3: Technical Details - Nested Collapsible */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-xs font-semibold text-gray-600 hover:text-gray-900 flex items-center gap-2">
                          <Code className="h-3 w-3" />
                          Technical Details (For developers)
                        </summary>
                        <div className="mt-3 pl-6 bg-gray-50 rounded-lg p-3 font-mono text-xs text-gray-800">
                          <p className="mb-2"><strong>Implementation:</strong></p>
                          <ul className="list-disc list-inside space-y-1 mb-3">
                            <li>Valid vectors: Checks for NaN, Inf, null values</li>
                            <li>Non-zero: Validates L2 norm {'>'} 0 (actual content present)</li>
                            <li>Norm health: Uses Modified Z-score with MAD (Median Absolute Deviation) to detect outliers</li>
                          </ul>

                          <p className="mb-2"><strong>Formula:</strong></p>
                          <div className="bg-white rounded p-2 mb-2">
                            <p>VQS = 0.4 × valid_ratio + 0.3 × non_zero_ratio + 0.3 × norm_health</p>
                            <p className="mt-1">where norm_health ≈ 1 - outlier_rate(norms)</p>
                            <p className="text-xs text-gray-600 mt-1">(robustly measured via MAD / modified z-score)</p>
                          </div>

                          <p className="mb-1"><strong>Source:</strong> <code>scoring_utils.py</code></p>
                        </div>
                      </details>

                      {/* Threshold Guide */}
                      <div className="text-xs text-gray-600 bg-white rounded-lg p-3 border border-gray-200">
                        <strong>Score Guide:</strong> ≥ 95% = Excellent | ≥ 85% = Good | &lt; 85% = Needs Investigation
                      </div>
                    </div>

                    <div className="bg-orange-50 border-l-4 border-orange-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Embedding Success Rate</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Percentage of chunks successfully embedded and stored in the vector database (Qdrant). Indicates embedding pipeline reliability. Calculated in real-time from Qdrant collection metadata.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Ratio of indexed vectors in Qdrant to total vectors attempted. This metric is enriched dynamically by querying Qdrant, ensuring it reflects the current state of the vector database.
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula:</strong> Success_Rate = (indexed_vectors_count / points_count) × 100
                        <br />Calculated from: qdrant.get_collection_info(collection_name)
                        <br />Includes validation: dimension check, storage confirmation, metadata persistence
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> 100% = Required (all chunks must be embedded successfully)
                      </p>
                      <p className="text-xs text-gray-600 mt-2">
                        <strong>Note:</strong> This metric is enriched from Qdrant when displayed in the UI. If it shows 0% or "Not Evaluated", the vector database may be inaccessible or indexing hasn't completed.
                      </p>
                    </div>

                    <div className="bg-orange-50 border-l-4 border-orange-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Embedding Model Health</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Health score of the embedding model based on output consistency and dimension matching. Monitors model performance and detects degradation. Calculated dynamically from Qdrant metadata.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Based on dimension consistency and vector quality. Set to 100% if dimension consistency is achieved, 0% otherwise. This is a lightweight health check focused on the most critical indicator: dimension matching.
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula (current implementation):</strong>
                        <br />Model_Health = 100% if actual_dim == expected_dim, else 0%
                        <br />
                        <br />where:
                        <br />- actual_dim = dimension from Qdrant collection config
                        <br />- expected_dim = configured embedding dimension (384 for MiniLM, 1536 for OpenAI-3-small)
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> 100% = Healthy, 0% = Degraded (dimension mismatch or model failure)
                      </p>
                      <p className="text-xs text-gray-600 mt-2">
                        <strong>Note:</strong> This metric is enriched from Qdrant when displayed in the UI. Extended health metrics (API errors, fallback rate, variance) may be added in future releases.
                      </p>
                    </div>

                    <div className="bg-orange-50 border-l-4 border-orange-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Semantic Search Readiness</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Composite RAG readiness score combining all vector health indicators. Indicates overall readiness for production semantic search. Calculated dynamically from Qdrant metadata.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Weighted combination of dimension consistency, vector quality, model health, and success rate. All component metrics are enriched from Qdrant in real-time.
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula:</strong>
                        <br />Semantic_Search_Readiness = (dim_consistency + success_rate + vector_quality + model_health) / 4
                        <br />
                        <br />where:
                        <br />- dim_consistency = Embedding_Dimension_Consistency (from Qdrant)
                        <br />- success_rate = Embedding_Success_Rate (from Qdrant indexed_vectors_count)
                        <br />- vector_quality = 0.5 × dim_consistency + 0.5 × success_rate (lightweight composite)
                        <br />- model_health = Embedding_Model_Health (dimension check)
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> ≥ 90% = Ready for Production, ≥ 75% = Acceptable, &lt; 75% = Needs Improvement
                      </p>
                      <p className="text-xs text-gray-600 mt-2">
                        <strong>Note:</strong> This metric is always recalculated when viewed in the UI to ensure it reflects current Qdrant state. It provides a real-time health check of your RAG system.
                      </p>
                    </div>
                  </div>
                </div>

                {/* RAG Performance Metrics */}
                <div className="bg-white border-2 border-red-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-3">
                    <Search className="h-6 w-6 text-[#C8102E]" />
                    RAG Performance Metrics
                  </h3>
                  <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 text-sm text-gray-700">
                    <strong>Note:</strong> Unless you have a curated evaluation set (queries + relevance labels), PrimeData computes these as a <em>self-retrieval proxy</em>:
                    each query is derived from a chunk, and the chunk is treated as the single relevant document. This validates indexing/search correctness, but it is not a full “production RAG” benchmark.
                  </div>
                  <div className="space-y-6">
                    {/* Retrieval Recall@K - Three-Tier Explanation */}
                    <div className="bg-red-50 border-l-4 border-red-500 rounded-lg p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Search className="h-5 w-5 text-red-600" />
                        <h4 className="font-bold text-gray-900">Retrieval Recall@K: How Good Is Your Search?</h4>
                      </div>

                      {/* Tier 1: Always Visible - Beginner-Friendly */}
                      <div className="mb-4">
                        <p className="text-sm text-gray-700 mb-3">
                          When you search for something, how often do you find what you need? This metric measures search success—like checking if Google shows you relevant results.
                        </p>

                        <div className="bg-white border border-red-200 rounded-lg p-4 mb-4">
                          <p className="text-sm font-bold text-red-900 mb-3">Think of it like a library search:</p>
                          <div className="space-y-2 text-sm text-gray-700">
                            <p>📚 You search for <span className="italic font-semibold">"climate change impacts"</span></p>
                            <p>📖 System shows top 10 books (K=10)</p>
                            <p>✓ 8 out of 10 are actually relevant to your query</p>
                            <p className="mt-2 pt-2 border-t border-red-300 font-bold text-green-700">
                              → Recall@10 = <span className="text-lg">80%</span> ✓
                            </p>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <CheckCircle2 className="h-4 w-4 text-green-600" />
                              <span className="text-sm font-bold text-green-900">Good (85%)</span>
                            </div>
                            <p className="text-xs text-gray-700">Search for "API authentication" → 9 of top 10 results are about API security</p>
                          </div>

                          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <XCircle className="h-4 w-4 text-red-600" />
                              <span className="text-sm font-bold text-red-900">Bad (40%)</span>
                            </div>
                            <p className="text-xs text-gray-700">Search for "API authentication" → Only 4 of top 10 results are relevant</p>
                          </div>
                        </div>

                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Lightbulb className="h-4 w-4 text-blue-600" />
                            <span className="text-sm font-bold text-blue-900">To Improve</span>
                          </div>
                          <ul className="text-xs text-gray-700 space-y-1">
                            <li>• Ensure Security is 100% (no blocked/redacted content)</li>
                            <li>• Improve Chunk Coherence (better content flow)</li>
                            <li>• Use high-quality embeddings (OpenAI, Azure)</li>
                            <li>• Increase K value to retrieve more results</li>
                          </ul>
                        </div>
                      </div>

                      {/* Tier 2: Expandable - How It Works */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-sm font-semibold text-red-700 hover:text-red-900 flex items-center gap-2">
                          <ChevronRight className="h-4 w-4" />
                          How We Calculate It (Click to expand)
                        </summary>
                        <div className="mt-3 pl-6 space-y-3">
                          <p className="text-sm text-gray-700">
                            We test your search system with sample queries:
                          </p>
                          <ol className="text-sm text-gray-700 space-y-2 list-decimal list-inside">
                            <li><strong>Take a sample query</strong> - e.g., "data retention policies"</li>
                            <li><strong>Search and get top K results</strong> - Usually top 10 (K=10)</li>
                            <li><strong>Count relevant results</strong> - How many actually answer the query?</li>
                            <li><strong>Calculate percentage</strong> - Relevant found / Total relevant</li>
                          </ol>

                          <div className="bg-red-100 border border-red-300 rounded-lg p-3">
                            <p className="text-xs font-bold text-red-900 mb-2">Example:</p>
                            <div className="space-y-1 text-xs text-gray-700">
                              <p><strong>Query:</strong> "GDPR compliance requirements"</p>
                              <p><strong>System returns top 10 chunks</strong></p>
                              <p>Results: 8 relevant + 2 off-topic</p>
                              <p className="mt-2 font-bold text-green-700">Recall@10 = 8/10 = 80% ✓</p>
                            </div>
                          </div>

                          <p className="text-xs text-gray-600 italic">
                            The "K" in Recall@K is how many results you check. Common values: K=5, K=10, K=20.
                          </p>
                        </div>
                      </details>

                      {/* Tier 3: Technical Details - Nested Collapsible */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-xs font-semibold text-gray-600 hover:text-gray-900 flex items-center gap-2">
                          <Code className="h-3 w-3" />
                          Technical Details (For developers)
                        </summary>
                        <div className="mt-3 pl-6 bg-gray-50 rounded-lg p-3 font-mono text-xs text-gray-800">
                          <p className="mb-2"><strong>Implementation:</strong></p>
                          <ul className="list-disc list-inside space-y-1 mb-3">
                            <li>Standard information retrieval metric</li>
                            <li>Evaluated using synthetic query generation</li>
                            <li>Typical K values: K=5, K=10, K=20</li>
                          </ul>

                          <p className="mb-2"><strong>Formula:</strong></p>
                          <div className="bg-white rounded p-2 mb-2">
                            <p>Recall@K = |&#123;relevant_docs&#125; ∩ &#123;retrieved_top_k&#125;| / |&#123;relevant_docs&#125;|</p>
                            <p className="text-xs text-gray-600 mt-1">Set intersection: relevant docs found in top K / total relevant docs</p>
                          </div>

                          <p className="mb-1"><strong>Source:</strong> Industry-standard IR metric, referenced in literature</p>
                        </div>
                      </details>

                      {/* Threshold Guide */}
                      <div className="text-xs text-gray-600 bg-white rounded-lg p-3 border border-gray-200">
                        <strong>Score Guide:</strong> ≥ 80% = Excellent | ≥ 65% = Good | &lt; 65% = Needs Tuning (varies by K)
                      </div>
                    </div>

                    {/* Average Precision@K - Three-Tier Explanation */}
                    <div className="bg-red-50 border-l-4 border-red-500 rounded-lg p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <Target className="h-5 w-5 text-red-600" />
                        <h4 className="font-bold text-gray-900">Average Precision@K: Search Accuracy & Ranking Quality</h4>
                      </div>

                      {/* Tier 1: Always Visible - Beginner-Friendly */}
                      <div className="mb-4">
                        <p className="text-sm text-gray-700 mb-3">
                          Not all search results are equal—finding relevant results <span className="font-bold">at the top</span> is more valuable than finding them buried at position 20. This metric rewards systems that show the best results first.
                        </p>

                        <div className="bg-white border border-red-200 rounded-lg p-4 mb-4">
                          <p className="text-sm font-bold text-red-900 mb-3">Why position matters:</p>
                          <div className="space-y-2 text-sm text-gray-700">
                            <p className="flex items-center gap-2">
                              <span className="text-green-700 font-bold">✓ Better:</span>
                              <span>Relevant docs at positions 1, 2, 3</span>
                            </p>
                            <p className="flex items-center gap-2">
                              <span className="text-orange-700 font-bold">✗ Worse:</span>
                              <span>Same docs at positions 15, 18, 19</span>
                            </p>
                            <p className="text-xs text-gray-600 mt-2 italic">
                              Users rarely scroll past the first few results, so ranking quality matters!
                            </p>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <CheckCircle2 className="h-4 w-4 text-green-600" />
                              <span className="text-sm font-bold text-green-900">Good (90%)</span>
                            </div>
                            <p className="text-xs text-gray-700">Top 3 results are relevant, position 7 is relevant → High precision</p>
                          </div>

                          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <XCircle className="h-4 w-4 text-red-600" />
                              <span className="text-sm font-bold text-red-900">Bad (50%)</span>
                            </div>
                            <p className="text-xs text-gray-700">Relevant docs scattered at positions 8, 14, 19 → Low precision</p>
                          </div>
                        </div>

                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Lightbulb className="h-4 w-4 text-blue-600" />
                            <span className="text-sm font-bold text-blue-900">To Improve</span>
                          </div>
                          <ul className="text-xs text-gray-700 space-y-1">
                            <li>• Use advanced reranking models (cross-encoder)</li>
                            <li>• Improve embedding quality (OpenAI text-embedding-3)</li>
                            <li>• Enhance metadata for better filtering</li>
                            <li>• Tune relevance scoring thresholds</li>
                          </ul>
                        </div>
                      </div>

                      {/* Tier 2: Expandable - How It Works */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-sm font-semibold text-red-700 hover:text-red-900 flex items-center gap-2">
                          <ChevronRight className="h-4 w-4" />
                          How We Calculate It (Click to expand)
                        </summary>
                        <div className="mt-3 pl-6 space-y-3">
                          <p className="text-sm text-gray-700">
                            We calculate precision at each relevant result position, then average:
                          </p>

                          <div className="bg-red-100 border border-red-300 rounded-lg p-3">
                            <p className="text-xs font-bold text-red-900 mb-2">Example Search Results (K=10):</p>
                            <div className="space-y-1 text-xs text-gray-700 font-mono">
                              <p>Position 1: ✓ Relevant → Precision@1 = 1/1 = 100%</p>
                              <p>Position 2: ✗ Not relevant</p>
                              <p>Position 3: ✓ Relevant → Precision@3 = 2/3 = 67%</p>
                              <p>Position 4: ✓ Relevant → Precision@4 = 3/4 = 75%</p>
                              <p>Position 5-10: Not relevant</p>
                              <p className="mt-2 pt-2 border-t border-red-400 font-bold text-green-700">
                                Average Precision = (100% + 67% + 75%) / 3 = <span className="text-lg">80.7%</span> ✓
                              </p>
                            </div>
                          </div>

                          <p className="text-xs text-gray-600 italic">
                            Higher AP@K means relevant results appear early in the ranking.
                          </p>
                        </div>
                      </details>

                      {/* Tier 3: Technical Details - Nested Collapsible */}
                      <details className="mb-3">
                        <summary className="cursor-pointer text-xs font-semibold text-gray-600 hover:text-gray-900 flex items-center gap-2">
                          <Code className="h-3 w-3" />
                          Technical Details (For developers)
                        </summary>
                        <div className="mt-3 pl-6 bg-gray-50 rounded-lg p-3 font-mono text-xs text-gray-800">
                          <p className="mb-2"><strong>Implementation:</strong></p>
                          <ul className="list-disc list-inside space-y-1 mb-3">
                            <li>Mean Average Precision (MAP) metric</li>
                            <li>Position-aware relevance scoring</li>
                            <li>Standard in information retrieval evaluations</li>
                          </ul>

                          <p className="mb-2"><strong>Formula:</strong></p>
                          <div className="bg-white rounded p-2 mb-2">
                            <p>AP@K = (1/|relevant|) × Σ (precision_at_i × relevance_i)</p>
                            <p className="mt-1">MAP = mean(AP@K across all queries)</p>
                            <p className="text-xs text-gray-600 mt-1">where i = position, relevance_i ∈ &#123;0,1&#125;</p>
                          </div>

                          <p className="mb-1"><strong>Source:</strong> Industry-standard IR metric (MAP)</p>
                        </div>
                      </details>

                      {/* Threshold Guide */}
                      <div className="text-xs text-gray-600 bg-white rounded-lg p-3 border border-gray-200">
                        <strong>Score Guide:</strong> ≥ 75% = Excellent | ≥ 60% = Good | &lt; 60% = Needs Tuning
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> ≥ 0.75 = Excellent, ≥ 0.60 = Good, &lt; 0.60 = Needs Improvement
                      </p>
                    </div>

                    <div className="bg-red-50 border-l-4 border-red-500 rounded-lg p-5">
                      <h4 className="font-bold text-gray-900 mb-3">Query Coverage</h4>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Description:</strong> Percentage of queries with at least one relevant result retrieved. Measures system robustness across diverse queries.
                      </p>
                      <p className="text-sm text-gray-700 mb-3">
                        <strong>Calculation:</strong> Ratio of queries with recall &gt; 0 to total queries. Higher coverage indicates better query handling diversity.
                      </p>
                      <div className="bg-white rounded-lg p-3 mb-3 font-mono text-xs text-gray-800">
                        <strong>Formula:</strong> Query_Coverage = (queries_with_relevant_results / total_queries) × 100
                        <br />Coverage = 1 if ∃ relevant_doc in retrieved@K, else 0
                      </div>
                      <p className="text-xs text-gray-600">
                        <strong>Threshold:</strong> ≥ 90% = Excellent, ≥ 75% = Good, &lt; 75% = Needs Broadening
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Quality Improvement Dashboard */}
          <section id="qualityImprovement" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('qualityImprovement')}
              className="w-full flex items-center justify-between text-left"
            >
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-gradient-to-br from-green-500 to-emerald-600 rounded-xl flex items-center justify-center">
                  <TrendingUp className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-gray-900">Data Quality Improvement Dashboard</h2>
                  <p className="text-sm text-gray-600 mt-1">See how PrimeData transforms your raw data into AI-ready data</p>
                </div>
              </div>
              {expandedSections.qualityImprovement ? (
                <ChevronUp className="h-6 w-6 text-gray-400" />
              ) : (
                <ChevronDown className="h-6 w-6 text-gray-400" />
              )}
            </button>

            {expandedSections.qualityImprovement && (
              <div className="mt-8 space-y-8">
                <div className="bg-gradient-to-br from-green-50 to-emerald-50 border-2 border-green-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Sparkles className="h-6 w-6 text-green-600" />
                    What is the Quality Improvement Dashboard?
                  </h3>
                  <p className="text-gray-700 leading-relaxed mb-4">
                    The Quality Improvement Dashboard demonstrates the <strong>measurable value</strong> PrimeData delivers by comparing your raw data quality (before transformation) with the final AI-ready data quality (after transformation).
                  </p>
                  <p className="text-gray-700 leading-relaxed">
                    This feature helps you <strong>demonstrate ROI</strong>, build trust with stakeholders, and understand exactly how PrimeData transforms low-quality data into production-ready AI datasets.
                  </p>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Target className="h-5 w-5 text-[#C8102E]" />
                    How It Works
                  </h3>
                  <div className="space-y-4">
                    {[
                      { step: '1', title: 'Baseline Assessment', desc: 'When files are first ingested, the system automatically calculates baseline quality metrics for your raw data before any transformations. This establishes the "before" snapshot.' },
                      { step: '2', title: 'Transformation Pipeline', desc: 'Your data flows through the complete AIRD pipeline: preprocessing, chunking, quality scoring, and embedding generation. PrimeData applies all configured rules and optimizations.' },
                      { step: '3', title: 'Final Assessment', desc: 'After transformation, final quality scores are calculated using the AI Readiness Fingerprint. These scores represent the "after" state of your data.' },
                      { step: '4', title: 'Improvement Comparison', desc: 'The dashboard compares baseline vs final scores to show the measurable improvement delivered by PrimeData, displayed as both point increases and percentage improvements.' },
                    ].map(({ step, title, desc }) => (
                      <div key={step} className="flex items-start gap-4 bg-gray-50 border border-gray-200 rounded-lg p-4">
                        <div className="flex-shrink-0 w-8 h-8 bg-[#C8102E] text-white rounded-full flex items-center justify-center font-bold">{step}</div>
                        <div>
                          <h4 className="font-bold text-gray-900 mb-1">{title}</h4>
                          <p className="text-sm text-gray-700">{desc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-[#C8102E]" />
                    Quality Dimensions Tracked
                  </h3>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="bg-blue-50 border-l-4 border-blue-500 rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2 flex items-center gap-2"><CheckCircle className="h-5 w-5 text-blue-600" />Completeness</h4>
                      <p className="text-sm text-gray-700">Measures metadata population and field coverage. Higher completeness means your data has all necessary fields for AI applications.</p>
                    </div>
                    <div className="bg-purple-50 border-l-4 border-purple-500 rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2 flex items-center gap-2"><AlertTriangle className="h-5 w-5 text-purple-600" />Noise Reduction</h4>
                      <p className="text-sm text-gray-700">Detects and removes special characters, garbled text, and formatting issues. Lower noise means cleaner, more reliable AI training data.</p>
                    </div>
                    <div className="bg-green-50 border-l-4 border-green-500 rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2 flex items-center gap-2"><Layers className="h-5 w-5 text-green-600" />Structure Score</h4>
                      <p className="text-sm text-gray-700">Assesses document formatting, sections, and readability. Better structure means AI models can understand document hierarchy.</p>
                    </div>
                    <div className="bg-amber-50 border-l-4 border-amber-500 rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2 flex items-center gap-2"><FileText className="h-5 w-5 text-amber-600" />Duplication</h4>
                      <p className="text-sm text-gray-700">Detection and handling of duplicate content. Lower duplication prevents model bias and reduces storage waste.</p>
                    </div>
                  </div>
                </div>

                <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Eye className="h-5 w-5 text-[#C8102E]" />
                    Where to Find It
                  </h3>
                  <p className="text-gray-700 leading-relaxed mb-4">
                    The Data Quality Improvement Dashboard appears as a <strong>prominent hero card</strong> at the top of each product's <strong>Overview tab</strong>. It's the first thing you'll see when viewing a product, immediately demonstrating the value PrimeData has added to your data.
                  </p>
                  <p className="text-sm text-gray-600 italic">
                    💡 Tip: Click "View Detailed Breakdown" to see improvement metrics for each individual quality dimension.
                  </p>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Rocket className="h-5 w-5 text-[#C8102E]" />
                    Example Results
                  </h3>
                  <div className="space-y-3">
                    {[
                      { label: 'Technical Documentation', range: '60-70% baseline → 90-98% AI-ready', pts: '+40 to +60 pts', color: 'green' },
                      { label: 'Customer Support Data', range: '55-65% baseline → 85-95% AI-ready', pts: '+35 to +55 pts', color: 'blue' },
                      { label: 'Product Manuals', range: '50-60% baseline → 90-98% AI-ready', pts: '+45 to +65 pts', color: 'purple' },
                    ].map(({ label, range, pts, color }) => (
                      <div key={label} className={`bg-gradient-to-r from-${color}-50 to-${color === 'green' ? 'emerald' : color === 'blue' ? 'sky' : 'violet'}-50 border border-${color}-200 rounded-lg p-4 flex items-center justify-between`}>
                        <div>
                          <h4 className="font-bold text-gray-900">{label}</h4>
                          <p className="text-sm text-gray-600">{range}</p>
                        </div>
                        <div className={`text-2xl font-bold text-${color}-600`}>{pts}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-gradient-to-br from-amber-50 to-yellow-50 border-2 border-amber-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Target className="h-6 w-6 text-amber-600" />
                    Business Value
                  </h3>
                  <div className="grid md:grid-cols-2 gap-4">
                    {[
                      { title: 'Demonstrate ROI', desc: 'Clearly show stakeholders how PrimeData transforms low-quality data into AI-ready data with measurable metrics' },
                      { title: 'Build Trust', desc: 'Transparent quality metrics build confidence in your AI applications and data quality' },
                      { title: 'Optimize Processing', desc: 'Understand which data sources need additional preprocessing to achieve maximum quality' },
                      { title: 'Sales & Marketing', desc: 'Use quality improvement screenshots to demonstrate platform value to prospects and customers' },
                    ].map(({ title, desc }) => (
                      <div key={title} className="flex items-start gap-3">
                        <CheckCircle2 className="h-5 w-5 text-amber-600 flex-shrink-0 mt-1" />
                        <div>
                          <h4 className="font-bold text-gray-900 mb-1">{title}</h4>
                          <p className="text-sm text-gray-700">{desc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Playbook Auto-Detection */}
          <section id="playbookAutoDetection" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('playbookAutoDetection')}
              className="w-full flex items-center justify-between text-left"
            >
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center">
                  <GitBranch className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-gray-900">Intelligent Playbook Auto-Detection</h2>
                  <p className="text-sm text-gray-600 mt-1">Automatic selection of optimal processing strategy</p>
                </div>
              </div>
              {expandedSections.playbookAutoDetection ? (
                <ChevronUp className="h-6 w-6 text-gray-400" />
              ) : (
                <ChevronDown className="h-6 w-6 text-gray-400" />
              )}
            </button>

            {expandedSections.playbookAutoDetection && (
              <div className="mt-8 space-y-8">
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border-2 border-blue-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Sparkles className="h-6 w-6 text-blue-600" />
                    What is Playbook Auto-Detection?
                  </h3>
                  <p className="text-gray-700 leading-relaxed mb-4">
                    PrimeData automatically selects the optimal processing playbook based on your document content and filename. This ensures that each document type receives the most appropriate <strong>preprocessing, normalization, and chunking strategy</strong>.
                  </p>
                  <p className="text-gray-700 leading-relaxed">
                    The system analyzes the first 1000 characters of your document and filename to identify domain-specific keywords, then routes to the best-matching playbook.
                  </p>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <BookOpen className="h-5 w-5 text-[#C8102E]" />
                    Available Playbooks
                  </h3>
                  <div className="space-y-4">
                    {[
                      { letter: 'H', name: 'HEALTHCARE', color: 'red', desc: 'Medical records, clinical notes, patient data with HIPAA compliance', keywords: ['healthcare', 'medical', 'patient', 'diagnosis', 'treatment', 'clinical', 'hospital', 'physician', 'medication', 'ehr', 'hipaa', 'phi'], uses: 'Electronic health records, clinical notes, patient summaries, medical research' },
                      { letter: 'T', name: 'TECH', color: 'blue', desc: 'Technical documentation, software guides, API docs, AI/ML content', keywords: ['ai', 'machine learning', 'deep learning', 'neural network', 'llm', 'gpt', 'transformer', 'api', 'software'], uses: 'Software documentation, API references, AI/ML papers, technical manuals' },
                      { letter: 'F', name: 'FINANCIAL', color: 'green', desc: 'Banking, finance, capital markets documentation', keywords: ['banking', 'financial', 'finance', 'capital', 'liquidity', 'basel', 'balance sheet', 'audit'], uses: 'Annual reports, financial statements, banking regulations' },
                      { letter: 'R', name: 'REGULATORY', color: 'purple', desc: 'Compliance documents, regulatory submissions', keywords: ['fda approved', 'regulatory submission', 'compliance report', 'supervisory review'], uses: 'FDA submissions, regulatory filings, compliance reports' },
                      { letter: 'S', name: 'SCANNED', color: 'amber', desc: 'OCR documents, scanned PDFs, image-based content', keywords: ['scanned', 'ocr', 'image', 'tesseract'], uses: 'Scanned documents, image PDFs, historical documents' },
                    ].map(({ letter, name, color, desc, keywords, uses }) => (
                      <div key={name} className={`bg-gradient-to-r from-${color}-50 to-${color === 'red' ? 'pink' : color === 'blue' ? 'cyan' : color === 'green' ? 'emerald' : color === 'purple' ? 'violet' : 'yellow'}-50 border-l-4 border-${color}-500 rounded-lg p-5`}>
                        <div className="flex items-start gap-3">
                          <div className={`flex-shrink-0 w-10 h-10 bg-${color}-500 text-white rounded-lg flex items-center justify-center font-bold`}>{letter}</div>
                          <div className="flex-1">
                            <h4 className="font-bold text-gray-900 text-lg mb-2">{name}</h4>
                            <p className="text-sm text-gray-700 mb-3">{desc}</p>
                            <p className="text-xs font-semibold text-gray-600 mb-1">KEYWORDS:</p>
                            <div className="flex flex-wrap gap-1 mb-3">
                              {keywords.map(kw => (
                                <span key={kw} className={`inline-block bg-${color}-100 text-${color}-800 text-xs px-2 py-0.5 rounded`}>{kw}</span>
                              ))}
                            </div>
                            <div className="text-xs text-gray-600"><strong>Use cases:</strong> {uses}</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Target className="h-5 w-5 text-[#C8102E]" />
                    How It Works
                  </h3>
                  <div className="space-y-3">
                    {[
                      { step: '1', label: 'Content Analysis', desc: 'Scans the first 1000 characters for domain-specific keywords' },
                      { step: '2', label: 'Filename Analysis', desc: 'Checks the filename for relevant indicators' },
                      { step: '3', label: 'Playbook Matching', desc: 'Selects the best-matching playbook based on keyword presence' },
                      { step: '4', label: 'Fallback', desc: 'Defaults to TECH playbook if no specific match is found' },
                    ].map(({ step, label, desc }) => (
                      <div key={step} className="flex items-start gap-3">
                        <div className="flex-shrink-0 w-6 h-6 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">{step}</div>
                        <p className="text-sm text-gray-700"><strong>{label}:</strong> {desc}</p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-4 text-sm text-gray-600 italic">
                    💡 Tip: You can manually override the auto-detected playbook when creating a product if needed.
                  </p>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <CheckCircle className="h-5 w-5 text-[#C8102E]" />
                    Benefits
                  </h3>
                  <div className="grid md:grid-cols-2 gap-4">
                    {[
                      { title: 'Automatic Optimization', desc: 'Each document type gets the most appropriate preprocessing without manual configuration' },
                      { title: 'Domain-Specific Quality', desc: 'Specialized playbooks preserve domain terminology and document structure' },
                      { title: 'Consistent Results', desc: 'Same document types always get the same processing strategy' },
                      { title: 'Time Savings', desc: 'No manual playbook selection required for common document types' },
                    ].map(({ title, desc }) => (
                      <div key={title} className="bg-white border border-gray-200 rounded-lg p-4">
                        <h4 className="font-bold text-gray-900 mb-2">{title}</h4>
                        <p className="text-sm text-gray-700">{desc}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Preprocessing Technical Details */}
          <section id="preprocessingDetails" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('preprocessingDetails')}
              className="w-full flex items-center justify-between text-left"
            >
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-gradient-to-br from-[#C8102E] to-rose-600 rounded-xl flex items-center justify-center">
                  <FileText className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-gray-900">Preprocessing Stage: Technical Details</h2>
                  <p className="text-sm text-gray-600 mt-1">11+ operations that transform raw data into AI-ready format</p>
                </div>
              </div>
              {expandedSections.preprocessingDetails ? (
                <ChevronUp className="h-6 w-6 text-gray-400" />
              ) : (
                <ChevronDown className="h-6 w-6 text-gray-400" />
              )}
            </button>

            {expandedSections.preprocessingDetails && (
              <div className="mt-6 space-y-6">
                <div className="bg-blue-50 border-l-4 border-blue-500 rounded-lg p-5">
                  <h3 className="font-bold text-gray-900 mb-3 flex items-center gap-2">
                    <Info className="h-5 w-5 text-blue-600" />
                    What is Preprocessing?
                  </h3>
                  <p className="text-sm text-gray-700">
                    Preprocessing is the <strong>critical second stage</strong> in the PrimeData pipeline that transforms raw ingested documents into normalized, structured, and chunked data optimized for AI/ML applications. It ensures text is clean, consistent, and properly formatted for embedding models.
                  </p>
                </div>

                <div>
                  <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Layers className="h-5 w-5 text-[#C8102E]" />
                    Core Operations (Always Applied)
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[
                      { n: '1', title: 'Text Extraction', bullets: ['PDF: PyPDF2/pypdf with page markers', 'DOCX: python-docx (paragraphs + tables)', 'PPTX: python-pptx with slide markers', 'XML/HTML: BeautifulSoup4 tag stripping', 'TXT/CSV/JSON: Direct UTF-8 reading'] },
                      { n: '2', title: 'Encoding Normalization', bullets: ['Unicode NFC normalization', 'Mojibake fixing (Ã©→é, â€™→\')', 'Zero-width character removal', 'BOM (byte order mark) removal'] },
                      { n: '3', title: 'Whitespace Normalization', bullets: ['Tab → 4 spaces conversion', 'Line break normalization (CRLF/CR → LF)', 'Trailing whitespace removal', 'Multiple spaces → single space', 'Empty line reduction (max 2)'] },
                      { n: '4', title: 'Line Unwrapping', bullets: ['Joins split sentences across lines', 'Detects wrapped lines (no punctuation + lowercase start)', 'Preserves intentional paragraph breaks'] },
                      { n: '5', title: 'PII Redaction', bullets: ['Email addresses → [EMAIL]', 'Phone numbers → [PHONE]', 'SSNs → [SSN]', 'Credit cards → [CC]', 'IP addresses → [IP]'] },
                      { n: '6', title: 'Special Character Handling', bullets: ['Smart quotes → Regular quotes', 'Em/En dashes → Hyphens', 'Bullets (•◦▪) → Hyphens', 'Math symbols (×÷±≈) → ASCII', 'Non-breaking spaces → Spaces'] },
                    ].map(({ n, title, bullets }) => (
                      <div key={n} className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                        <h4 className="font-bold text-gray-900 mb-2">{n}. {title}</h4>
                        <ul className="text-xs text-gray-600 list-disc list-inside space-y-1">
                          {bullets.map(b => <li key={b}>{b}</li>)}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-[#C8102E]" />
                    Advanced Features (Conditional)
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[
                      { n: '7', title: 'OCR Error Correction', note: 'For SCANNED playbook:', bullets: ['0/O confusion fixes', '1/I/l confusion fixes', 'rn/m confusion fixes', 'Common word corrections (tlie→the)', 'Double-space word fixing (w o r d→word)'] },
                      { n: '8', title: 'PDF Corruption Fix', note: 'Auto-detected:', bullets: ['Detects space-between-chars (ratio >0.3)', 'Fixes: "B e z o s" → "Bezos"', 'Preserves intentional spaces', 'Per-page detection'] },
                      { n: '9', title: 'Table Extraction', note: '3 detection methods:', bullets: ['Markdown tables (| col | col |)', 'ASCII art (+----|---+)', 'Tab-separated values', 'Extracts headers and rows', 'Linearizes or preserves structure'] },
                      { n: '10', title: 'Citation Normalization', note: '5 formats supported:', bullets: ['APA: (Author, Year)', 'MLA: (Author Page)', 'IEEE: [N]', 'Chicago: Footnotes', 'Harvard: Author (Year)'] },
                      { n: '11', title: 'Section Detection', note: 'Intelligent identification:', bullets: ['Headers (bold, ALL CAPS, numbered)', 'Table of Contents', 'References/Bibliography', 'Appendix sections', 'Abstract/Summary'] },
                      { n: '12', title: 'Metadata Extraction', note: 'Enhanced enrichment:', bullets: ['Dates (created, modified, published)', 'Authors/contributors', 'Version numbers', 'Language detection', 'Page/word counts'] },
                    ].map(({ n, title, note, bullets }) => (
                      <div key={n} className="bg-green-50 border border-green-200 rounded-lg p-4">
                        <h4 className="font-bold text-gray-900 mb-2">{n}. {title}</h4>
                        <p className="text-sm text-gray-700 mb-2">{note}</p>
                        <ul className="text-xs text-gray-600 list-disc list-inside space-y-1">
                          {bullets.map(b => <li key={b}>{b}</li>)}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-gradient-to-r from-[#F5E6E8] to-white border-2 border-[#C8102E] rounded-xl p-6">
                  <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Settings className="h-5 w-5 text-[#C8102E]" />
                    Playbook-Specific Processing
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[
                      { name: 'HEALTHCARE Playbook', items: ['Medical term preservation (BP, HR, O2)', 'Medication name handling', 'HIPAA-compliant aggressive PII redaction', 'Clinical section recognition (CC, HPI, ROS, A&P)'] },
                      { name: 'FINANCIAL Playbook', items: ['Currency standardization ($1,000 → 1000 USD)', 'Percentage normalization (5% → 0.05)', 'Financial ratio preservation (P/E, ROE)', 'Basel/IFRS section detection'] },
                      { name: 'SCANNED Playbook', items: ['Aggressive OCR error correction', 'Scan artifact removal', 'Background noise character cleanup', 'Double-space word fixing'] },
                      { name: 'TECH Playbook', items: ['Code block preservation (formatting)', 'API endpoint handling (/api/v1/...)', 'HTTP method preservation (GET, POST)', 'JSON/YAML formatting maintenance'] },
                    ].map(({ name, items }) => (
                      <div key={name} className="bg-white border border-gray-200 rounded-lg p-4">
                        <h4 className="font-bold text-[#C8102E] mb-2">{name}</h4>
                        <ul className="text-xs text-gray-600 list-disc list-inside space-y-1">
                          {items.map(i => <li key={i}>{i}</li>)}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-yellow-50 border-l-4 border-yellow-500 rounded-lg p-5">
                  <h4 className="font-bold text-gray-900 mb-3 flex items-center gap-2">
                    <Lightbulb className="h-5 w-5 text-yellow-600" />
                    Best Practices for Technical Readers
                  </h4>
                  <ul className="space-y-2 text-sm text-gray-700">
                    {[
                      { bold: 'Choose correct playbook:', rest: 'HEALTHCARE for medical, SCANNED for OCR docs, TECH for API docs' },
                      { bold: 'Enable metadata extraction:', rest: 'Critical for time-series data and compliance tracking' },
                      { bold: 'Monitor preprocessing metrics:', rest: 'Check chunk count, token distribution, section coverage' },
                      { bold: 'Balance PII redaction:', rest: 'Aggressive for healthcare, minimal for internal docs' },
                    ].map(({ bold, rest }) => (
                      <li key={bold} className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                        <span><strong>{bold}</strong> {rest}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </section>

          {/* Data Quality Rules */}
          <section id="dataQualityRules" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('dataQualityRules')}
              className="w-full flex items-center justify-between text-left"
            >
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-gradient-to-br from-[#C8102E] to-rose-600 rounded-xl flex items-center justify-center">
                  <Shield className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-gray-900">Data Quality Rules for AI-Ready Data</h2>
                  <p className="text-sm text-gray-600 mt-1">Comprehensive quality assurance for production AI systems</p>
                </div>
              </div>
              {expandedSections.dataQualityRules ? (
                <ChevronUp className="h-6 w-6 text-gray-400" />
              ) : (
                <ChevronDown className="h-6 w-6 text-gray-400" />
              )}
            </button>

            {expandedSections.dataQualityRules && (
              <div className="mt-6 space-y-8">
                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border-l-4 border-blue-500 rounded-lg p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-blue-600" />
                    What Are Data Quality Rules?
                  </h3>
                  <p className="mb-4 text-gray-700">
                    Data Quality Rules are automated validation checks that ensure your data meets production standards for AI/ML applications. PrimeData includes 14 recommended rules across 7 categories, all evaluated automatically during pipeline execution.
                  </p>
                  <div className="bg-white rounded-lg p-4">
                    <p className="font-semibold text-gray-900 mb-2">Why Quality Rules Matter:</p>
                    <ul className="list-disc list-inside space-y-2 text-sm text-gray-700 ml-2">
                      <li><strong>Prevent AI Failures</strong>: Catch data issues before they cause production problems</li>
                      <li><strong>Ensure Consistency</strong>: Maintain uniform data quality across all pipeline runs</li>
                      <li><strong>Regulatory Compliance</strong>: Meet GDPR, SOX, HIPAA requirements with audit trails</li>
                      <li><strong>Faster Troubleshooting</strong>: Identify root causes instantly with violation reports</li>
                      <li><strong>Cost Savings</strong>: Reduce storage waste and compute inefficiencies</li>
                    </ul>
                  </div>
                </div>

                <div className="bg-gradient-to-r from-green-50 to-emerald-50 border-l-4 border-green-500 rounded-lg p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Rocket className="h-5 w-5 text-green-600" />
                    Quick Setup: Seed Recommended Rules
                  </h3>
                  <div className="bg-white rounded-lg p-4 space-y-3">
                    {[
                      { n: '1', title: 'Navigate to Data Quality', desc: 'Go to your Product → Data Quality tab → Click "Manage Rules"' },
                      { n: '2', title: 'Seed Recommended Rules', desc: 'Click the "Seed Recommended Rules" button with sparkle icon' },
                      { n: '3', title: 'Save and Run Pipeline', desc: '14 rules are automatically added. Save and run your pipeline to evaluate them' },
                      { n: '4', title: 'Review Violations', desc: 'Check the Data Quality tab for any violations with detailed reports' },
                    ].map(({ n, title, desc }) => (
                      <div key={n} className="flex items-start gap-3">
                        <div className="flex-shrink-0 w-7 h-7 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">{n}</div>
                        <div>
                          <p className="font-semibold text-gray-900">{title}</p>
                          <p className="text-sm text-gray-600">{desc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-[#C8102E]" />
                    The 14 Recommended Rules for AI-Ready Data
                  </h3>
                  {[
                    { cat: '1. Required Fields', color: 'blue', icon: <Database className="h-5 w-5 text-blue-600" />, rules: [
                      { level: 'ERROR', title: 'AI-Ready Metadata Completeness', checks: 'chunk_text, chunk_index, document_id, product_id, version, created_at', why: 'RAG systems require these core fields for retrieval, ranking, and traceability.' },
                      { level: 'WARNING', title: 'Enhanced AI Metadata', checks: 'page_number, section_title, audience, AI_Trust_Score', why: 'Improves search quality, enables citations, and allows targeted retrieval.' },
                    ]},
                    { cat: '2. Duplicate Rate', color: 'purple', icon: <Layers className="h-5 w-5 text-purple-600" />, rules: [
                      { level: 'ERROR', title: 'Training Data Uniqueness', checks: 'Max 15% duplicate rate', why: 'High duplication causes model overfitting and biased retrieval results.' },
                      { level: 'WARNING', title: 'Optimal Data Diversity', checks: 'Max 5% duplicate rate (best practice)', why: 'Ensures maximum data diversity for highest model quality.' },
                    ]},
                    { cat: '3. Chunk Coverage', color: 'green', icon: <Target className="h-5 w-5 text-green-600" />, rules: [
                      { level: 'ERROR', title: 'Complete Document Coverage', checks: 'Min 85% coverage of original content', why: 'Prevents information loss during chunking.' },
                      { level: 'WARNING', title: 'Ideal Document Coverage', checks: 'Min 95% coverage (best practice)', why: 'Maximum completeness ensures AI has access to all relevant information.' },
                    ]},
                    { cat: '4. Bad File Extensions', color: 'red', icon: <AlertTriangle className="h-5 w-5 text-red-600" />, rules: [
                      { level: 'ERROR', title: 'AI-Unsafe File Extensions', checks: '.exe, .dll, .bat, .sh, .cmd, .scr, .vbs, .js, .jar, .app', why: 'Executables pose security risks and cannot provide meaningful text for AI.' },
                      { level: 'WARNING', title: 'Low-Quality Data Formats', checks: '.tmp, .log, .cache, .bak, .old, .swp, .DS_Store', why: 'Temporary/system files have little AI value and waste storage.' },
                    ]},
                    { cat: '5. Data Freshness', color: 'yellow', icon: <BarChart3 className="h-5 w-5 text-yellow-600" />, rules: [
                      { level: 'ERROR', title: 'Production AI Freshness', checks: 'Max 180 days (6 months) old', why: 'Stale data leads to outdated AI responses and hallucinations.' },
                      { level: 'WARNING', title: 'Premium AI Data Freshness', checks: 'Max 90 days (3 months) old', why: 'Ideal for customer-facing AI systems requiring current information.' },
                    ]},
                    { cat: '6. File Size', color: 'indigo', icon: <FileText className="h-5 w-5 text-indigo-600" />, rules: [
                      { level: 'ERROR', title: 'AI Processing Size Limit', checks: '1KB - 100MB', why: 'Files >100MB cause memory issues. Files <1KB lack meaningful content.' },
                      { level: 'WARNING', title: 'Optimal AI File Size', checks: '10KB - 50MB (best practice)', why: 'Optimal size range for efficient processing and minimal latency.' },
                    ]},
                    { cat: '7. Content Length', color: 'pink', icon: <Settings className="h-5 w-5 text-pink-600" />, rules: [
                      { level: 'ERROR', title: 'Embedding-Ready Chunk Length', checks: '50 - 8,000 characters', why: 'Matches embedding model limits. Chunks <50 chars lack semantic meaning.' },
                      { level: 'WARNING', title: 'Optimal RAG Chunk Size', checks: '200 - 2,000 characters (research-backed)', why: 'Research shows 512-1024 tokens provides best retrieval accuracy for RAG.' },
                    ]},
                  ].map(({ cat, color, icon, rules }) => (
                    <div key={cat} className={`mb-6 bg-${color}-50 border-l-4 border-${color}-500 rounded-lg p-5`}>
                      <h4 className="font-bold text-gray-900 mb-3 flex items-center gap-2">{icon}{cat}</h4>
                      <div className="space-y-3">
                        {rules.map(({ level, title, checks, why }) => (
                          <div key={title} className="bg-white rounded-lg p-4">
                            <div className="flex items-center gap-2 mb-2">
                              <span className={`px-2 py-1 text-xs font-bold rounded ${level === 'ERROR' ? 'bg-red-100 text-red-800' : 'bg-orange-100 text-orange-800'}`}>{level}</span>
                              <span className="font-semibold text-gray-900">{title}</span>
                            </div>
                            <p className="text-sm text-gray-700 mb-2"><strong>Checks:</strong> {checks}</p>
                            <p className="text-sm text-gray-600"><strong>Why:</strong> {why}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="bg-gradient-to-r from-rose-50 to-pink-50 border-l-4 border-[#C8102E] rounded-lg p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-[#C8102E]" />
                    Business Impact
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {['⚡ 3-5x Fewer AI Failures|Catch data issues before production deployment', '🚀 40% Faster Troubleshooting|Instant root cause identification with violation reports', '💰 30% Storage Savings|Eliminate duplicates and low-value files', '✅ 100% Audit Compliance|Complete audit trails for GDPR, SOX, HIPAA'].map(item => {
                      const [title, desc] = item.split('|')
                      return (
                        <div key={title} className="bg-white rounded-lg p-4">
                          <p className="font-semibold text-gray-900 mb-2">{title}</p>
                          <p className="text-sm text-gray-600">{desc}</p>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Fingerprint Artifacts */}
          <section id="fingerprintArtifacts" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('fingerprintArtifacts')}
              className="w-full flex items-center justify-between text-left"
            >
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-xl flex items-center justify-center">
                  <FileText className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-gray-900">AI Readiness Fingerprint Artifacts</h2>
                  <p className="text-sm text-gray-600 mt-1">Comprehensive quality signatures for production AI deployments</p>
                </div>
              </div>
              {expandedSections.fingerprintArtifacts ? (
                <ChevronUp className="h-6 w-6 text-gray-400" />
              ) : (
                <ChevronDown className="h-6 w-6 text-gray-400" />
              )}
            </button>

            {expandedSections.fingerprintArtifacts && (
              <div className="mt-6 space-y-8">
                <div className="bg-gradient-to-r from-purple-50 to-indigo-50 border-l-4 border-purple-500 rounded-lg p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-purple-600" />
                    What is a Fingerprint Artifact?
                  </h3>
                  <p className="mb-4 text-gray-700">
                    A <strong>fingerprint artifact</strong> is a comprehensive JSON report that captures the complete quality signature of your AI-ready data. Generated during every pipeline run, it provides instant visibility into <strong>13 critical dimensions</strong> that determine whether your data is suitable for production AI applications.
                  </p>
                  <div className="bg-white rounded-lg p-4">
                    <p className="font-semibold text-gray-900 mb-3">📊 Each Fingerprint Contains:</p>
                    <ul className="list-disc list-inside space-y-2 text-sm text-gray-700 ml-2">
                      <li><strong>13 AI-Ready Metrics</strong>: Completeness, Accuracy, Security, Quality, Timeliness, Token Count, GPT Confidence, Chunk Boundary Quality, Format Consistency, Metadata Completeness, Privacy Compliance, Processing Efficiency, Knowledge Base Readiness</li>
                      <li><strong>Aggregated Scores</strong>: Each metric rated 0-100 based on chunk-level analysis</li>
                      <li><strong>AI Trust Score</strong>: Overall readiness score combining all dimensions</li>
                      <li><strong>Version Tracking</strong>: Links to specific product version and pipeline run</li>
                      <li><strong>Full Lineage</strong>: Traceability to raw files and transformations</li>
                    </ul>
                  </div>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-purple-600" />
                    Why Fingerprints Matter for AI-Ready Data
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[
                      { icon: <CheckCircle className="h-6 w-6 text-green-600 flex-shrink-0 mt-0.5" />, bg: 'from-green-50 to-emerald-50 border-green-200', title: 'Instant Quality Assessment', desc: 'View complete data quality profile without running expensive queries. Make decisions in seconds, not minutes.' },
                      { icon: <Shield className="h-6 w-6 text-blue-600 flex-shrink-0 mt-0.5" />, bg: 'from-blue-50 to-cyan-50 border-blue-200', title: 'Production Deployment Confidence', desc: 'Use Trust Score ≥ 50% as deployment gate. Verify PII handling meets compliance (Security ≥ 90%).' },
                      { icon: <AlertTriangle className="h-6 w-6 text-yellow-600 flex-shrink-0 mt-0.5" />, bg: 'from-yellow-50 to-orange-50 border-yellow-200', title: 'Quality Monitoring & Alerts', desc: 'Detect quality regressions between versions. Track improvements over time.' },
                      { icon: <GitBranch className="h-6 w-6 text-purple-600 flex-shrink-0 mt-0.5" />, bg: 'from-purple-50 to-pink-50 border-purple-200', title: 'Artifact Lineage & Traceability', desc: 'Full provenance linking to pipeline runs, raw files. Recreate exact data state.' },
                    ].map(({ icon, bg, title, desc }) => (
                      <div key={title} className={`bg-gradient-to-br ${bg} border rounded-lg p-4`}>
                        <div className="flex items-start gap-3">
                          {icon}
                          <div>
                            <p className="font-semibold text-gray-900 mb-2">{title}</p>
                            <p className="text-sm text-gray-700">{desc}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4">Key Metrics Explained</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse border border-gray-300">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="border border-gray-300 px-4 py-3 text-left text-sm font-semibold text-gray-900">Metric</th>
                          <th className="border border-gray-300 px-4 py-3 text-left text-sm font-semibold text-gray-900">What It Measures</th>
                          <th className="border border-gray-300 px-4 py-3 text-left text-sm font-semibold text-gray-900">Threshold</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white">
                        {[
                          { name: 'AI Trust Score', desc: 'Overall production readiness', threshold: '≥ 50%', color: 'green' },
                          { name: 'Completeness', desc: 'All required fields present', threshold: '≥ 80%', color: 'blue' },
                          { name: 'Security', desc: 'PII detection & handling compliance', threshold: '≥ 90%', color: 'red' },
                          { name: 'Quality', desc: 'Text quality, noise level', threshold: '≥ 70%', color: 'yellow' },
                          { name: 'Chunk Boundary Quality', desc: 'Clean sentence/paragraph breaks', threshold: '≥ 80%', color: 'blue' },
                          { name: 'Knowledge Base Readiness', desc: 'Suitability for RAG/search applications', threshold: '≥ 50%', color: 'green' },
                        ].map(({ name, desc, threshold, color }, i) => (
                          <tr key={name} className={i % 2 === 1 ? 'bg-gray-50' : ''}>
                            <td className="border border-gray-300 px-4 py-3 text-sm font-medium text-gray-900">{name}</td>
                            <td className="border border-gray-300 px-4 py-3 text-sm text-gray-700">{desc}</td>
                            <td className="border border-gray-300 px-4 py-3 text-sm">
                              <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold bg-${color}-100 text-${color}-800`}>{threshold}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="bg-gray-900 rounded-lg p-6">
                  <h3 className="text-xl font-bold text-white mb-4">Example Fingerprint JSON</h3>
                  <pre className="text-xs text-green-400 overflow-x-auto">{`{
  "fingerprint": {
    "AI_Trust_Score": 89.5,
    "Completeness": 100.0,
    "Accuracy": 99.8,
    "Secure": 100.0,
    "Quality": 85.2,
    "Timeliness": 50.0,
    "Token_Count": 60.8,
    "Context_Quality": 88.0,
    "Metadata_Completeness": 95.0,
    "Privacy_Compliance": 100.0,
    "Processing_Efficiency": 88.5,
    "Knowledge_Base_Ready": 86.3,
    "Avg_Chunk_Coherence": 82.4,
    "Avg_Noise_Free_Score": 91.2,
    "Chunk_Boundary_Quality": 78.5,
    "Format_Consistency": 100.0
  }
}`}</pre>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4">Use Cases by Role</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[
                      { icon: <Users className="h-5 w-5" />, role: 'Data Science Teams', items: ['Validate training data quality before model training', 'Compare dataset versions for quality improvements', 'Document quality for model cards and reports'] },
                      { icon: <Settings className="h-5 w-5" />, role: 'MLOps Engineers', items: ['Automate deployment gates based on Trust Score', 'Monitor quality degradation in production pipelines', 'Trigger re-training when thresholds are exceeded'] },
                      { icon: <Shield className="h-5 w-5" />, role: 'Compliance Officers', items: ['Demonstrate PII detection and handling (Security Score)', 'Provide audit trail of data quality validation', 'Track compliance with data governance policies'] },
                      { icon: <TrendingUp className="h-5 w-5" />, role: 'Product Managers', items: ['Understand data readiness status at a glance', 'Make go/no-go decisions on feature releases', 'Communicate quality to stakeholders with clear metrics'] },
                    ].map(({ icon, role, items }) => (
                      <div key={role} className="bg-white border-2 border-gray-200 rounded-lg p-5">
                        <p className="font-semibold text-[#C8102E] mb-3 flex items-center gap-2">{icon}{role}</p>
                        <ul className="list-disc list-inside space-y-1.5 text-sm text-gray-700 ml-1">
                          {items.map(i => <li key={i}>{i}</li>)}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* AI Data Lineage */}
          <section id="aiLineage" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('aiLineage')}
              className="w-full flex items-center justify-between text-left"
            >
              <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                <div className="bg-[#C8102E]/10 rounded-xl p-3">
                  <GitBranch className="h-6 w-6 text-[#C8102E]" />
                </div>
                AI Data Lineage
              </h2>
              {expandedSections.aiLineage ? (
                <ChevronUp className="h-5 w-5 text-gray-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-400" />
              )}
            </button>

            {expandedSections.aiLineage && (
              <div className="mt-8 space-y-8 text-gray-700">
                <div className="bg-gradient-to-br from-purple-50 to-blue-50 border-2 border-purple-200 rounded-lg p-6">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0 bg-purple-100 rounded-full p-3">
                      <GitBranch className="h-6 w-6 text-purple-600" />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-gray-900 mb-3">What is AI Data Lineage?</h3>
                      <p className="text-gray-700 mb-4">
                        AI Data Lineage provides <strong>complete visibility</strong> into how your data transforms from raw files into AI-ready vectors. Track every operation, measure quality improvements, and maintain full audit trails for governance and debugging.
                      </p>
                      <div className="flex items-center gap-2 text-sm text-purple-700">
                        <Eye className="h-4 w-4" />
                        <span className="font-semibold">Access: Product Overview → "View Full AI Lineage Graph"</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Layers className="h-5 w-5 text-[#C8102E]" />
                    Two-Layer Architecture
                  </h3>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="bg-gradient-to-br from-blue-50 to-cyan-50 border border-blue-200 rounded-lg p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <div className="bg-blue-500 text-white px-3 py-1 rounded-full text-xs font-bold">Layer 1</div>
                        <span className="font-semibold text-gray-900">AI-Ready Chunks</span>
                      </div>
                      <p className="text-sm text-gray-700 mb-3">Transform raw files into clean, scored JSONL chunks</p>
                      <div className="space-y-1 text-xs text-gray-600">
                        {['Preprocessing & Cleaning', 'Quality Scoring', 'Fingerprinting', 'Policy & Validation'].map(item => (
                          <div key={item} className="flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3 text-blue-600" />
                            <span>{item}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="bg-gradient-to-br from-green-50 to-emerald-50 border border-green-200 rounded-lg p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <div className="bg-green-500 text-white px-3 py-1 rounded-full text-xs font-bold">Layer 2</div>
                        <span className="font-semibold text-gray-900">AI-Ready Vectors</span>
                      </div>
                      <p className="text-sm text-gray-700 mb-3">Transform chunks into searchable vector embeddings</p>
                      <div className="space-y-1 text-xs text-gray-600">
                        {['Embedding Generation', 'Vector Preparation', 'Qdrant Collection Setup', 'Batch Vector Upload'].map(item => (
                          <div key={item} className="flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3 text-green-600" />
                            <span>{item}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Target className="h-5 w-5 text-[#C8102E]" />
                    Sub-Stage Tracking
                  </h3>
                  <p className="text-gray-700 mb-4">Get fine-grained visibility into operations within each stage:</p>
                  <div className="bg-gray-50 rounded-lg p-4 mb-4">
                    <h4 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                      <FileText className="h-4 w-4 text-blue-600" />
                      Preprocessing Sub-Stages
                    </h4>
                    <div className="grid md:grid-cols-2 gap-2 text-sm">
                      {[['extract_text', 'PDF/DOCX text extraction'], ['fix_pdf_corruption', 'Fix spacing issues'], ['apply_normalizers', 'Text cleaning'], ['route_playbook', 'Auto-detect playbook'], ['detect_sections_and_chunk', 'Intelligent chunking'], ['classify_audience', 'Audience targeting']].map(([key, desc]) => (
                        <div key={key} className="flex items-center gap-2">
                          <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                          <span><strong>{key}</strong>: {desc}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <h4 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                      <Database className="h-4 w-4 text-green-600" />
                      Indexing Sub-Stages (Layer 2)
                    </h4>
                    <div className="grid md:grid-cols-2 gap-2 text-sm">
                      {[['load_ai_ready_chunks', 'Load from Layer 1'], ['generate_embeddings', 'Create vectors'], ['prepare_vectors', 'Format for Qdrant'], ['create_collection', 'Setup Qdrant collection'], ['upload_to_qdrant', 'Batch upload vectors']].map(([key, desc]) => (
                        <div key={key} className="flex items-center gap-2">
                          <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                          <span><strong>{key}</strong>: {desc}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Lightbulb className="h-5 w-5 text-[#C8102E]" />
                    Key Use Cases
                  </h3>
                  <div className="space-y-3">
                    {[
                      { icon: <Search className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />, bg: 'bg-blue-50 border-blue-200', title: 'Pipeline Debugging', desc: 'Quickly identify which operation failed and why. View error details, input data, and metrics at failure point.' },
                      { icon: <TrendingUp className="h-5 w-5 text-purple-600 flex-shrink-0 mt-0.5" />, bg: 'bg-purple-50 border-purple-200', title: 'Performance Optimization', desc: 'Identify slow operations, optimize batch sizes, and choose better models based on duration metrics.' },
                      { icon: <Shield className="h-5 w-5 text-green-600 flex-shrink-0 mt-0.5" />, bg: 'bg-green-50 border-green-200', title: 'Compliance & Audit', desc: 'Complete audit trail from raw files to vectors. Document all transformations for regulatory requirements.' },
                      { icon: <BarChart3 className="h-5 w-5 text-orange-600 flex-shrink-0 mt-0.5" />, bg: 'bg-orange-50 border-orange-200', title: 'Quality Assurance', desc: 'Track quality improvements at each stage. Verify baseline vs final scores and transformation impact.' },
                    ].map(({ icon, bg, title, desc }) => (
                      <div key={title} className={`flex items-start gap-3 ${bg} border rounded-lg p-4`}>
                        {icon}
                        <div>
                          <h4 className="font-semibold text-gray-900 mb-1">{title}</h4>
                          <p className="text-sm text-gray-700">{desc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-[#C8102E]/5 border-2 border-[#C8102E]/20 rounded-lg p-6">
                  <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-[#C8102E]" />
                    Pro Tips
                  </h3>
                  <ul className="space-y-3 text-sm">
                    {[
                      { bold: 'Use Sub-Stage View for debugging:', rest: 'Click failed nodes to see detailed error information and metrics at failure point' },
                      { bold: 'Filter by layer:', rest: 'Focus on chunk creation (Layer 1) or vectorization (Layer 2) separately for clarity' },
                      { bold: 'Monitor duration trends:', rest: 'Track sub-stage durations over time to identify performance degradation' },
                      { bold: 'Export for stakeholders:', rest: 'Screenshot lineage graphs to demonstrate data transformation in presentations' },
                    ].map(({ bold, rest }) => (
                      <li key={bold} className="flex items-start gap-2">
                        <CheckCircle2 className="h-5 w-5 text-[#C8102E] flex-shrink-0 mt-0.5" />
                        <span><strong>{bold}</strong> {rest}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </section>

          {/* Context Engineering */}
          <section id="contextEngineering" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('contextEngineering')}
              className="w-full flex items-center justify-between text-left"
            >
              <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                <div className="bg-[#C8102E]/10 rounded-xl p-3">
                  <Sparkles className="h-6 w-6 text-[#C8102E]" />
                </div>
                Context Engineering
              </h2>
              {expandedSections.contextEngineering ? (
                <ChevronUp className="h-5 w-5 text-gray-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-400" />
              )}
            </button>

            {expandedSections.contextEngineering && (
              <div className="mt-8 space-y-8">
                <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-5">
                  <h3 className="text-lg font-bold text-gray-900 mb-2">What is Context Engineering?</h3>
                  <p className="text-sm text-gray-700">
                    Context engineering is the process of assembling, enriching, and structuring data so that the context window fed to an LLM is maximally informative — fresh, attributed, deduplicated, and coherently ordered. PrimeData provides four context engineering capabilities built directly into the pipeline and API.
                  </p>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">1. Context Freshness Score (14th Quality Dimension)</h3>
                  <p className="text-sm text-gray-700 mb-4">
                    Every chunk now carries a <strong>Context Freshness Score</strong> (0–100) — a continuous per-chunk measure of temporal relevance for AI consumption, using domain-aware exponential decay.
                  </p>
                  <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 font-mono text-sm text-gray-800 mb-4">
                    score = 100 × 0.5 ^ (age_days / half_life_days)
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="bg-gray-100">
                          <th className="border border-gray-200 px-3 py-2 text-left font-semibold">Domain</th>
                          <th className="border border-gray-200 px-3 py-2 text-left font-semibold">Half-Life</th>
                          <th className="border border-gray-200 px-3 py-2 text-left font-semibold">Rationale</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          { domain: 'Regulatory', hl: '60 days', why: 'Regulations change frequently' },
                          { domain: 'Finance / Banking', hl: '90 days', why: 'Market and policy changes' },
                          { domain: 'Legal', hl: '180 days', why: 'Case law evolves over months' },
                          { domain: 'Technical', hl: '365 days', why: 'Specs stable but version-tracked' },
                          { domain: 'Academic', hl: '730 days', why: 'Research has longer shelf life' },
                        ].map(({ domain, hl, why }, i) => (
                          <tr key={domain} className={i % 2 === 1 ? 'bg-gray-50' : ''}>
                            <td className="border border-gray-200 px-3 py-2">{domain}</td>
                            <td className="border border-gray-200 px-3 py-2">{hl}</td>
                            <td className="border border-gray-200 px-3 py-2">{why}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-xs text-gray-500 mt-3">
                    The score is stored in every Qdrant payload as <code className="bg-gray-100 px-1 rounded">context_freshness_score</code> and is included as the 14th dimension of the AI readiness fingerprint.
                  </p>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">2. Context Assembly API</h3>
                  <p className="text-sm text-gray-700 mb-4">
                    Instead of retrieving raw chunks, use <code className="bg-gray-100 px-1 rounded">POST /api/v1/playground/context</code> to receive a pre-formatted, LLM-ready context block in a single call.
                  </p>
                  <div className="space-y-3">
                    {[
                      { step: '1', title: 'Retrieve', desc: 'Semantic search fetches top-k chunks from your collection' },
                      { step: '2', title: 'Deduplicate', desc: 'Near-identical chunks are merged — only the highest-scoring copy is kept' },
                      { step: '3', title: 'Order', desc: 'Chunks are sorted by source document → page → chunk index for coherent reading order' },
                      { step: '4', title: 'Detect Conflicts', desc: 'Chunks with semantically opposing claims are flagged for review' },
                      { step: '5', title: 'Truncate', desc: 'Chunks are added until the token budget (max_tokens) is consumed' },
                      { step: '6', title: 'Format', desc: 'Each chunk is emitted with a source header for attribution — ready to inject into an LLM prompt' },
                    ].map(({ step, title, desc }) => (
                      <div key={step} className="flex items-start gap-3">
                        <span className="flex-shrink-0 w-7 h-7 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">{step}</span>
                        <div><strong>{title}:</strong> <span className="text-gray-700 text-sm">{desc}</span></div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 bg-gray-50 border border-gray-200 rounded-lg p-4">
                    <p className="text-xs font-semibold text-gray-600 mb-2">Response includes:</p>
                    <ul className="text-xs text-gray-700 space-y-1 list-disc list-inside">
                      <li><code className="bg-gray-100 px-1 rounded">context_text</code> — formatted, attributed context block</li>
                      <li><code className="bg-gray-100 px-1 rounded">sources</code> — per-chunk attribution with freshness score</li>
                      <li><code className="bg-gray-100 px-1 rounded">freshness_summary</code> — min/max/mean freshness + stale chunk count</li>
                      <li><code className="bg-gray-100 px-1 rounded">conflicts</code> — list of conflicting chunk pairs to review</li>
                      <li><code className="bg-gray-100 px-1 rounded">assembly_metadata</code> — dedup count, strategy used, token estimate</li>
                    </ul>
                  </div>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">3. Use-Case Context Mapping</h3>
                  <p className="text-sm text-gray-700 mb-4">
                    Set a <code className="bg-gray-100 px-1 rounded">use_case_config</code> on your product to get per-use-case AI readiness scores alongside the overall score.
                  </p>
                  <div className="overflow-x-auto mb-4">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="bg-gray-100">
                          <th className="border border-gray-200 px-3 py-2 text-left font-semibold">Use Case</th>
                          <th className="border border-gray-200 px-3 py-2 text-left font-semibold">Key Quality Factors</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          { uc: 'RAG', factors: 'Small chunks (≤512 tokens), high coherence, fresh' },
                          { uc: 'Fine-Tuning', factors: 'Large volume, domain consistency, low noise' },
                          { uc: 'Classification', factors: 'Balanced examples, clear labels, low noise' },
                          { uc: 'Agentic', factors: 'Structured data, tool-call-friendly format' },
                          { uc: 'Summarization', factors: 'High completeness, good structure' },
                        ].map(({ uc, factors }, i) => (
                          <tr key={uc} className={i % 2 === 1 ? 'bg-gray-50' : ''}>
                            <td className="border border-gray-200 px-3 py-2 font-medium">{uc}</td>
                            <td className="border border-gray-200 px-3 py-2">{factors}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">4. External Data Augmentation (Opt-In)</h3>
                  <p className="text-sm text-gray-700 mb-4">
                    Enable the augmentation pipeline stage to enrich chunks with related external context snippets at index time. This broadens retrieval context without modifying your source documents.
                  </p>
                  <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4 mb-4">
                    <p className="text-sm font-semibold text-gray-900 mb-1">Disabled by default</p>
                    <p className="text-sm text-gray-700">Augmentation must be explicitly enabled in your product's <code className="bg-white px-1 rounded">use_case_config</code> or <code className="bg-white px-1 rounded">augmentation_config</code>.</p>
                  </div>
                  <div className="space-y-2 text-sm text-gray-700">
                    <p><strong>How it works:</strong></p>
                    <ol className="list-decimal list-inside space-y-1 ml-2">
                      <li>Pipeline extracts 3–5 keywords per chunk</li>
                      <li>Queries DuckDuckGo Instant Answer API (no API key required)</li>
                      <li>Stores the snippet as <code className="bg-gray-100 px-1 rounded">external_context</code> in the Qdrant payload</li>
                      <li>Context assembly surfaces <code className="bg-gray-100 px-1 rounded">external_context</code> alongside internal chunk content</li>
                    </ol>
                  </div>
                  <div className="mt-4 bg-gray-50 border border-gray-200 rounded-lg p-3">
                    <p className="text-xs font-semibold text-gray-600 mb-1">Configuration:</p>
                    <pre className="text-xs text-gray-800 overflow-x-auto">{`"augmentation_config": {
  "enabled": true,
  "max_chunks_to_augment": 50
}`}</pre>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Vectorization */}
          <section id="vectorization" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('vectorization')}
              className="w-full flex items-center justify-between text-left"
            >
              <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                <div className="bg-[#C8102E]/10 rounded-xl p-3">
                  <Sparkles className="h-6 w-6 text-[#C8102E]" />
                </div>
                Vectorization
              </h2>
              {expandedSections.vectorization ? (
                <ChevronUp className="h-5 w-5 text-gray-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-400" />
              )}
            </button>

            {expandedSections.vectorization && (
              <div className="mt-8 space-y-6">
                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">How Vectorization Works</h3>
                  <div className="space-y-4">
                    <div className="flex items-start gap-4">
                      <div className="flex-shrink-0 w-8 h-8 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">1</div>
                      <div>
                        <p className="font-semibold text-gray-900">Text Chunking</p>
                        <p className="text-sm text-gray-700">Documents are split into chunks using configurable strategies (fixed-size, semantic, recursive).</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-4">
                      <div className="flex-shrink-0 w-8 h-8 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">2</div>
                      <div>
                        <p className="font-semibold text-gray-900">Embedding Generation</p>
                        <p className="text-sm text-gray-700">Each chunk is converted to a vector embedding using OpenAI API or local models (MiniLM, MPNet, etc.).</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-4">
                      <div className="flex-shrink-0 w-8 h-8 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">3</div>
                      <div>
                        <p className="font-semibold text-gray-900">Vector Storage</p>
                        <p className="text-sm text-gray-700">Vectors are stored in Qdrant vector database with metadata (chunk ID, source, section, etc.).</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-4">
                      <div className="flex-shrink-0 w-8 h-8 bg-[#C8102E] text-white rounded-full flex items-center justify-center text-sm font-bold">4</div>
                      <div>
                        <p className="font-semibold text-gray-900">Quality Validation</p>
                        <p className="text-sm text-gray-700">Vector metrics are calculated to ensure quality and consistency.</p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">Embedding Models</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">OpenAI (Recommended)</h4>
                      <ul className="text-sm text-gray-700 space-y-1">
                        <li>• text-embedding-3-small: 1536 dimensions</li>
                        <li>• text-embedding-3-large: 3072 dimensions</li>
                        <li>• Requires API key, saves ~500MB-1GB memory</li>
                        <li>• Best for production use</li>
                      </ul>
                    </div>
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <h4 className="font-bold text-gray-900 mb-2">Open Source (Local)</h4>
                      <ul className="text-sm text-gray-700 space-y-1">
                        <li>• MiniLM: 384 dimensions</li>
                        <li>• MPNet, BGE, GTE, E5: 768-1024 dimensions</li>
                        <li>• Works offline, requires more memory</li>
                        <li>• Good for development/testing</li>
                      </ul>
                    </div>
                  </div>
                </div>

                <div className="bg-amber-50 border-l-4 border-amber-400 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold text-amber-900 mb-1">Fallback Mode</p>
                      <p className="text-sm text-amber-800">
                        If embedding models fail to load or API keys are missing, PrimeData falls back to hash-based embeddings. This provides basic functionality but won't support semantic search. Ensure your embedding model is properly configured for production use.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Troubleshooting */}
          <section id="troubleshooting" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('troubleshooting')}
              className="w-full flex items-center justify-between text-left"
            >
              <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                <div className="bg-[#C8102E]/10 rounded-xl p-3">
                  <AlertTriangle className="h-6 w-6 text-[#C8102E]" />
                </div>
                Troubleshooting
              </h2>
              {expandedSections.troubleshooting ? (
                <ChevronUp className="h-5 w-5 text-gray-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-400" />
              )}
            </button>

            {expandedSections.troubleshooting && (
              <div className="mt-8 space-y-6">
                <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                  <h3 className="text-lg font-bold text-gray-900 mb-4">Common Issues</h3>
                  <div className="space-y-4">
                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <p className="font-semibold text-gray-900 mb-2">Low AI Trust Score</p>
                      <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside ml-2">
                        <li>Check individual metric scores to identify weak areas</li>
                        <li>Review recommendations in the AI Readiness section</li>
                        <li>Try different chunking strategies or playbooks</li>
                        <li>Ensure preprocessing playbook is appropriate for your content type</li>
                      </ul>
                    </div>

                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <p className="font-semibold text-gray-900 mb-2">Pipeline Failures</p>
                      <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside ml-2">
                        <li>Check Airflow logs for detailed error messages</li>
                        <li>Verify all services (PostgreSQL, Qdrant, MinIO) are running</li>
                        <li>Ensure sufficient disk space and memory</li>
                        <li>Check API keys (OpenAI, cloud storage) are configured correctly</li>
                      </ul>
                    </div>

                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <p className="font-semibold text-gray-900 mb-2">Vector Metrics Show 0% or "Not Evaluated"</p>
                      <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside ml-2">
                        <li>Vector metrics are enriched in real-time from Qdrant when viewed in the UI</li>
                        <li>0% values indicate either: Qdrant is inaccessible from the backend, indexing hasn't completed, or no vectors were successfully created</li>
                        <li>Ensure the indexing stage completed successfully in the Airflow pipeline</li>
                        <li>Check Qdrant connection: verify Qdrant service is running and accessible at configured host:port</li>
                        <li>Verify embedding model is properly configured (API key for OpenAI, or model loaded for local embeddings)</li>
                        <li>If indexing completed but metrics still show 0%, restart the backend service to refresh the Qdrant client connection</li>
                      </ul>
                    </div>

                    <div className="bg-[#F5E6E8] border-l-4 border-[#C8102E] rounded-lg p-4">
                      <p className="font-semibold text-gray-900 mb-2">Memory Issues (8GB Systems)</p>
                      <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside ml-2">
                        <li>Use OpenAI API embeddings instead of local models (saves ~500MB-1GB)</li>
                        <li>Use test-only services for development (excludes Airflow)</li>
                        <li>Close other memory-intensive applications</li>
                        <li>Monitor memory usage with <code className="bg-gray-100 px-1 rounded">scripts/check_memory.sh</code> or <code className="bg-gray-100 px-1 rounded">scripts/check_memory.ps1</code></li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Best Practices */}
          <section id="bestPractices" className="bg-white rounded-xl shadow-lg border-2 border-gray-200 p-8">
            <button
              onClick={() => toggleSection('bestPractices')}
              className="w-full flex items-center justify-between text-left"
            >
              <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
                <div className="bg-[#C8102E]/10 rounded-xl p-3">
                  <CheckCircle2 className="h-6 w-6 text-[#C8102E]" />
                </div>
                Best Practices
              </h2>
              {expandedSections.bestPractices ? (
                <ChevronUp className="h-5 w-5 text-gray-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-400" />
              )}
            </button>

            {expandedSections.bestPractices && (
              <div className="mt-8 space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                    <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                      <Settings className="h-5 w-5 text-[#C8102E]" />
                      Chunking Best Practices
                    </h3>
                    <ul className="space-y-2 text-sm text-gray-700">
                      <li>• Use fixed-size chunking for general content (800-1000 tokens)</li>
                      <li>• Use semantic chunking for documents with clear structure</li>
                      <li>• Set chunk overlap to 10-20% for better context preservation</li>
                      <li>• Avoid chunks smaller than 100 tokens or larger than 2000 tokens</li>
                    </ul>
                  </div>

                  <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                    <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                      <Database className="h-5 w-5 text-[#C8102E]" />
                      Embedding Best Practices
                    </h3>
                    <ul className="space-y-2 text-sm text-gray-700">
                      <li>• Use OpenAI embeddings for production (better quality, saves memory)</li>
                      <li>• Use local models (MiniLM) for development/testing</li>
                      <li>• Ensure embedding dimension matches your vector database configuration</li>
                      <li>• Monitor embedding success rate - should be close to 100%</li>
                    </ul>
                  </div>

                  <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                    <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                      <FileText className="h-5 w-5 text-[#C8102E]" />
                      Content Quality Best Practices
                    </h3>
                    <ul className="space-y-2 text-sm text-gray-700">
                      <li>• Remove boilerplate and navigation elements before processing</li>
                      <li>• Ensure consistent formatting across documents</li>
                      <li>• Add metadata (titles, sections, authors) where possible</li>
                      <li>• Use appropriate playbooks for your content type (legal, financial, technical)</li>
                    </ul>
                  </div>

                  <div className="bg-white border-2 border-gray-200 rounded-xl p-6">
                    <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                      <Target className="h-5 w-5 text-[#C8102E]" />
                      Quality Targets
                    </h3>
                    <ul className="space-y-2 text-sm text-gray-700">
                      <li>• AI Trust Score: Aim for 80%+ for production use</li>
                      <li>• Security Score: Must be 100% (no PII detected)</li>
                      <li>• Semantic Search Readiness: Aim for 85%+ for RAG applications</li>
                      <li>• Embedding Success Rate: Should be 100% (all chunks embedded)</li>
                    </ul>
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
        </div>

        {/* Footer */}
        <div className="mt-12 text-center">
          <p className="text-gray-600 mb-4">Need more help?</p>
          <Link to="/app/settings">
            <Button className="bg-[#C8102E] text-white hover:bg-[#A00D24]">
              Contact Support
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}
