# PrimeData: Extraction & AI Ready Score Generation - Detailed Workflow

**Date**: 2026-03-31
**Purpose**: Comprehensive technical breakdown of how data extraction and AI readiness scores are generated

---

## Table of Contents

1. [High-Level Overview](#high-level-overview)
2. [Stage 1: Data Extraction & Preprocessing](#stage-1-data-extraction--preprocessing)
3. [Stage 2: Quality Scoring](#stage-2-quality-scoring)
4. [Stage 3: Fingerprinting & AI Readiness](#stage-3-fingerprinting--ai-readiness)
5. [AI Ready Score Calculation](#ai-ready-score-calculation)
6. [Quality Metrics & Drill-Down](#quality-metrics--drill-down)
7. [Complete Example Workflow](#complete-example-workflow)

---

## High-Level Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                     USER UPLOADS FILES                             │
│  (PDF, DOCX, XLSX, TXT - Multiple files supported)                 │
└────────────────────┬─────────────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────────────┐
│           AIRFLOW INGESTION PIPELINE TRIGGERED                      │
│              (Manual or Auto-scheduled)                             │
└────────────────────┬─────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌─────────────────────┐  ┌──────────────────────┐
│  STAGE 1: EXTRACT   │  │  STAGE 2: QUALITY    │
│  & PREPROCESS       │──│  SCORE               │
│                     │  │                      │
│ • Load from S3      │  │ • Calculate metrics  │
│ • Extract text      │  │ • Coherence score    │
│ • Normalize         │  │ • Noise score        │
│ • Chunk & split     │  │ • Confidence score   │
│ • Save processed    │  │ • Save metrics.json  │
└─────────────────────┘  └──────────────────────┘
        │                         │
        └────────────┬────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  STAGE 3: FINGERPRINT  │
        │  & AI READINESS        │
        │                        │
        │ • Aggregate metrics    │
        │ • Calculate trust      │
        │ • Generate readiness   │
        │ • Create fingerprint   │
        └────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  AI READY SCORE        │
        │  (0-100)               │
        │                        │
        │  Available in:         │
        │  • Fingerprint         │
        │  • Product metadata    │
        │  • API responses       │
        └────────────────────────┘
```

---

## Stage 1: Data Extraction & Preprocessing

### 1.1 File Ingestion

**Location**: `backend/src/primedata/api/datasources.py` → `POST /api/v1/datasources/{id}/upload-files`

**Process**:
```
User Upload
    │
    ├─ Endpoint: POST /api/v1/datasources/{id}/upload-files
    │
    ├─ Validation:
    │  ├─ Verify datasource exists
    │  ├─ Verify datasource type is FOLDER
    │  ├─ Verify user has access
    │  └─ Verify file types allowed
    │
    ├─ For each file:
    │  ├─ Read file content
    │  ├─ Calculate SHA256 checksum
    │  ├─ Determine content type (MIME)
    │  ├─ Upload to S3/GCS
    │  └─ Create RawFile record in PostgreSQL
    │
    └─ Database tables updated:
       └─ raw_files table:
          ├─ id (UUID)
          ├─ filename (original name)
          ├─ storage_bucket (s3 or gcs)
          ├─ storage_key (full path in storage)
          ├─ file_size (bytes)
          ├─ file_checksum (SHA256)
          ├─ status (ingested)
          └─ product_id, version, workspace_id
```

### 1.2 Preprocessing Stage

**Location**: `backend/src/primedata/ingestion_pipeline/aird_stages/preprocess.py`

**Purpose**: Extract text from files, normalize, and create chunks

**Process**:
```
Preprocessing Stage (Airflow Task)
    │
    ├─ Input: RawFile records (one per uploaded file)
    │
    ├─ For each file:
    │  │
    │  ├─ Step 1: Load from S3
    │  │  └─ Retrieve full document content from storage_key
    │  │
    │  ├─ Step 2: Format Detection & Extraction
    │  │  ├─ PDF: Extract text via PyPDF2/pdfplumber
    │  │  ├─ DOCX: Extract via python-docx
    │  │  ├─ XLSX: Extract via openpyxl
    │  │  ├─ TXT: Direct read
    │  │  └─ Preserve structure (sections, pages, tables)
    │  │
    │  ├─ Step 3: Normalization
    │  │  ├─ Remove headers/footers
    │  │  ├─ Remove extra whitespace
    │  │  ├─ Clean special characters
    │  │  ├─ Preserve section information
    │  │  └─ Preserve page numbers
    │  │
    │  ├─ Step 4: Structure Detection
    │  │  ├─ Identify sections (headings, subsections)
    │  │  ├─ Detect tables and lists
    │  │  ├─ Track page numbers
    │  │  ├─ Tag document sections
    │  │  └─ Create section hierarchy
    │  │
    │  └─ Step 5: Chunking Strategy
    │     ├─ Load chunking config from product
    │     ├─ Apply strategy:
    │     │  ├─ SENTENCE: Split on sentence boundaries
    │     │  ├─ PARAGRAPH: Split on paragraph boundaries
    │     │  ├─ CHARACTER: Split by fixed character count
    │     │  └─ HYBRID: Combination of above
    │     ├─ Ensure chunks have overlap (sliding window)
    │     ├─ Create chunk_index and ordering
    │     └─ Assign chunk_id based on file + section + index
    │
    ├─ Output: processed_chunks_{filename}.jsonl
    │  └─ One JSON object per line:
    │     {
    │       "chunk_id": "file1_section2_chunk45",
    │       "text": "Chunk content text...",
    │       "filename": "File1.pdf",
    │       "section": "Chapter 2",
    │       "page": 45,
    │       "chunk_order": 45,
    │       "document_id": "file1",
    │       "field_name": "content"
    │     }
    │
    └─ Register artifact: processed_chunks_{filename}.jsonl
       └─ File saved to S3 with metadata (size, checksum, etag)
```

### 1.3 Preprocessing Config

**Source**: Product configuration or playbook

**Available strategies**:
- **SENTENCE**: Split after sentence-ending punctuation (., !, ?)
- **PARAGRAPH**: Split on blank lines
- **CHARACTER**: Fixed size chunks (e.g., 512 chars)
- **RECURSIVE**: Try sentences first, then paragraphs if too long
- **SEMANTIC**: Use model-based sentence splitting

**Configuration example**:
```python
chunking_config = {
    "strategy": "sentence",
    "chunk_size": 512,        # Target size in characters
    "overlap": 50,            # Overlap between chunks
    "min_chunk_size": 100,    # Minimum chunk size
    "max_chunk_size": 2000,   # Maximum chunk size
}
```

---

## Stage 2: Quality Scoring

### 2.1 Scoring Stage Overview

**Location**: `backend/src/primedata/ingestion_pipeline/aird_stages/scoring.py`

**Purpose**: Calculate quality metrics for each chunk

**Process**:
```
Scoring Stage (Airflow Task)
    │
    ├─ Input: processed_chunks_*.jsonl files
    │
    ├─ For each chunk:
    │  │
    │  ├─ Score 1: CONFIDENCE
    │  │  ├─ What: How confident the extraction was
    │  │  ├─ Method:
    │  │  │  ├─ Check for extraction artifacts (OCR errors)
    │  │  │  ├─ Validate text encoding
    │  │  │  ├─ Check for suspicious patterns
    │  │  │  └─ Score: 0-100 (higher = more confident)
    │  │  └─ Default: 85 (good extraction quality)
    │  │
    │  ├─ Score 2: COHERENCE
    │  │  ├─ What: How well sentences flow together
    │  │  ├─ Method (from chunk_coherence.py):
    │  │  │  ├─ Split chunk into sentences
    │  │  │  ├─ Calculate semantic similarity between consecutive sentences
    │  │  │  │  (using sentence transformers or embeddings)
    │  │  │  ├─ If avg_similarity < 0.3: penalize heavily
    │  │  │  ├─ If 0.3 ≤ avg_similarity < 0.6: medium score
    │  │  │  ├─ If avg_similarity ≥ 0.6: good score
    │  │  │  └─ Formula:
    │  │  │     if avg_similarity < 0.3:
    │  │  │         score = (avg_similarity / 0.3) * 50
    │  │  │     else:
    │  │  │         score = 50 + ((avg_similarity - 0.3) / 0.7) * 50
    │  │  └─ Range: 0-100 (higher = more coherent)
    │  │
    │  ├─ Score 3: NOISE
    │  │  ├─ What: Amount of non-content characters/noise
    │  │  ├─ Method (from baseline_assessment.py):
    │  │  │  ├─ Count special characters ratio
    │  │  │  │  └─ noise += min(special_char_ratio * 400, 40)
    │  │  │  ├─ Count excessive whitespace ratio
    │  │  │  │  └─ noise += min(whitespace_ratio * 200, 20)
    │  │  │  ├─ Count non-ASCII characters ratio
    │  │  │  │  └─ noise += min(non_ascii_ratio * 100, 30)
    │  │  │  ├─ Count very long words (likely junk)
    │  │  │  │  └─ noise += min(long_words_ratio * 100, 10)
    │  │  │  └─ Cap at 100
    │  │  └─ Range: 0-100 (lower = less noise, better)
    │  │
    │  ├─ Score 4: TRUST/READINESS
    │  │  ├─ What: Overall trust score combining above metrics
    │  │  ├─ Formula:
    │  │  │  score = (0.4 * confidence) +
    │  │  │          (0.3 * coherence) +
    │  │  │          (0.3 * (100 - noise))
    │  │  └─ Range: 0-100
    │  │
    │  └─ Store in chunk record (for later access):
    │     {
    │       "chunk_id": "...",
    │       "confidence_score": 85.0,
    │       "coherence_score": 72.5,
    │       "noise_score": 15.2,
    │       "score": 75.3  // Trust score
    │     }
    │
    ├─ Output: metrics.json
    │  └─ Aggregated metrics for all chunks:
    │     {
    │       "total_chunks": 5000,
    │       "avg_confidence": 84.5,
    │       "avg_coherence": 70.8,
    │       "avg_noise": 18.3,
    │       "avg_trust_score": 73.2,
    │       "chunk_quality_distribution": {
    │         "excellent": 2500,  // score > 90
    │         "good": 1800,       // 70-90
    │         "fair": 600,        // 50-70
    │         "poor": 100         // < 50
    │       }
    │     }
    │
    └─ Register artifact: metrics.json
       └─ File saved to S3 with metadata
```

### 2.2 Quality Score Storage

**Where scores are stored**:
1. **In processed JSONL**: Each chunk record includes scores
2. **In metrics.json**: Aggregated statistics
3. **In OpenSearch**: When indexed for search (confidence_score, coherence_score, noise_score)
4. **In Database**: Product.trust_score is average of all chunk scores

---

## Stage 3: Fingerprinting & AI Readiness

### 3.1 Fingerprinting Stage

**Location**: `backend/src/primedata/ingestion_pipeline/aird_stages/fingerprint.py`

**Purpose**: Generate comprehensive quality fingerprint and AI readiness assessment

**Process**:
```
Fingerprinting Stage (Airflow Task)
    │
    ├─ Input: metrics.json from scoring stage
    │
    ├─ Step 1: Load Trust Scores
    │  ├─ Get avg_trust_score from metrics.json
    │  ├─ Get distribution (excellent/good/fair/poor)
    │  └─ Calculate trust_percentage (excellent + good) / total
    │
    ├─ Step 2: Calculate AI Readiness Metrics
    │  │
    │  ├─ Metric 1: Data Quality Score
    │  │  ├─ Source: Scoring metrics
    │  │  ├─ Calculation:
    │  │  │  data_quality = (
    │  │  │    avg_confidence * 0.33 +
    │  │  │    avg_coherence * 0.33 +
    │  │  │    (100 - avg_noise) * 0.34
    │  │  │  )
    │  │  └─ Weight: 25% of AI Ready score
    │  │
    │  ├─ Metric 2: Completeness Score
    │  │  ├─ Source: DQ violations, chunk coverage
    │  │  ├─ Calculation:
    │  │  │  completeness = (
    │  │  │    (1 - violation_ratio) * 0.7 +
    │  │  │    chunk_coverage * 0.3
    │  │  │  ) * 100
    │  │  └─ Weight: 20% of AI Ready score
    │  │
    │  ├─ Metric 3: Consistency Score
    │  │  ├─ Source: Quality distribution
    │  │  ├─ Calculation:
    │  │  │  consistency = (excellent_ratio * 100 +
    │  │  │                good_ratio * 80 +
    │  │  │                fair_ratio * 50 +
    │  │  │                poor_ratio * 0) / max(excellent+good+fair+poor, 1)
    │  │  └─ Weight: 20% of AI Ready score
    │  │
    │  ├─ Metric 4: Coverage Score
    │  │  ├─ Source: File upload coverage
    │  │  ├─ Calculation:
    │  │  │  coverage = (total_chunks / expected_chunks) * 100
    │  │  │  capped at 100
    │  │  └─ Weight: 15% of AI Ready score
    │  │
    │  └─ Metric 5: Compliance Score
    │     ├─ Source: Policy evaluation results
    │     ├─ Calculation:
    │     │  compliance = policy_passed ? 100 :
    │     │              (1 - violation_count/total_rules) * 100
    │     └─ Weight: 20% of AI Ready score
    │
    ├─ Step 3: Calculate AI READY SCORE
    │  │
    │  ├─ Formula:
    │  │  AI_READY_SCORE = (
    │  │    data_quality * 0.25 +
    │  │    completeness * 0.20 +
    │  │    consistency * 0.20 +
    │  │    coverage * 0.15 +
    │  │    compliance * 0.20
    │  │  )
    │  │
    │  ├─ Result: 0-100 score
    │  │
    │  └─ Interpretation:
    │     ├─ 90-100: EXCELLENT - Ready for AI/RAG
    │     ├─ 75-89:  GOOD - Ready with minor improvements
    │     ├─ 60-74:  FAIR - Some improvements needed
    │     ├─ 40-59:  POOR - Major improvements needed
    │     └─ 0-39:   NOT READY - Significant work required
    │
    ├─ Step 4: Create Fingerprint
    │  └─ fingerprint.json contains:
    │     {
    │       "AI_Trust_Score": 78.5,
    │       "AI_Ready_Score": 75.3,
    │       "Data_Quality": 72.0,
    │       "Completeness": 82.0,
    │       "Consistency": 68.5,
    │       "Coverage": 95.0,
    │       "Compliance": 88.0,
    │       "Confidence_Average": 84.5,
    │       "Coherence_Average": 70.8,
    │       "Noise_Average": 18.3,
    │       "Chunk_Quality_Distribution": {
    │         "excellent": 2500,
    │         "good": 1800,
    │         "fair": 600,
    │         "poor": 100
    │       },
    │       "Timestamp": "2026-03-31T10:30:00Z",
    │       "Recommendation": "Ready for deployment with monitoring"
    │     }
    │
    └─ Register artifact: fingerprint.json
       └─ File saved to S3
```

### 3.2 AI Ready Score Categories

**Scoring Breakdown**:

```
┌─────────────────────────────────────────────────────────────┐
│           AI READY SCORE COMPONENTS                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Data Quality (25%)                                         │
│  ├─ Confidence (text extraction confidence)                 │
│  ├─ Coherence (sentence flow quality)                       │
│  └─ Noise (unwanted characters/artifacts)                   │
│                                                             │
│  Completeness (20%)                                         │
│  ├─ Data field presence                                     │
│  ├─ DQ rule violations ratio                                │
│  └─ Document section coverage                               │
│                                                             │
│  Consistency (20%)                                          │
│  ├─ Quality distribution balance                            │
│  ├─ Variation in chunk scores                               │
│  └─ Outlier detection                                       │
│                                                             │
│  Coverage (15%)                                             │
│  ├─ Chunk extraction coverage                               │
│  ├─ File upload completeness                                │
│  └─ Section representation                                  │
│                                                             │
│  Compliance (20%)                                           │
│  ├─ Policy evaluation results                               │
│  ├─ Governance rule adherence                               │
│  └─ Security/privacy requirements                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## AI Ready Score Calculation

### Full Formula

```python
AI_READY_SCORE = (
    # Data Quality: How good are individual chunks?
    (
        (AVG_CONFIDENCE * 0.33) +
        (AVG_COHERENCE * 0.33) +
        ((100 - AVG_NOISE) * 0.34)
    ) * 0.25 +

    # Completeness: Do we have enough data?
    (
        ((1 - VIOLATION_RATIO) * 0.7) +
        (CHUNK_COVERAGE * 0.3)
    ) * 0.20 +

    # Consistency: Is quality uniform?
    (
        (EXCELLENT_RATIO * 100) +
        (GOOD_RATIO * 80) +
        (FAIR_RATIO * 50) +
        (POOR_RATIO * 0)
    ) / TOTAL_CHUNKS * 0.20 +

    # Coverage: Did we process everything?
    MIN(
        (TOTAL_CHUNKS / EXPECTED_CHUNKS) * 100,
        100
    ) * 0.15 +

    # Compliance: Do we meet policy requirements?
    (
        100 if POLICY_PASSED else
        ((1 - POLICY_VIOLATIONS / TOTAL_POLICIES) * 100)
    ) * 0.20
)

# Result: 0-100
```

### Example Calculation

```
Given a dataset with:
  - Total chunks: 5000
  - Avg confidence: 85
  - Avg coherence: 72
  - Avg noise: 18
  - Violations: 50 (1% violation ratio)
  - Excellent chunks: 2500
  - Good chunks: 1800
  - Fair chunks: 600
  - Poor chunks: 100
  - Policy: PASSED

Calculation:
  Data_Quality = ((85 * 0.33) + (72 * 0.33) + (82 * 0.34)) * 0.25
               = 79.6 * 0.25 = 19.9

  Completeness = (((1 - 0.01) * 0.7) + (1.0 * 0.3)) * 0.20
               = (0.693 + 0.3) * 0.20
               = 0.993 * 0.20 = 19.9

  Consistency = ((2500/5000*100 + 1800/5000*80 + 600/5000*50 + 0) / 5000) * 0.20
              = 79.6 * 0.20 = 15.9

  Coverage = MIN((5000/5000)*100, 100) * 0.15
           = 100 * 0.15 = 15.0

  Compliance = 100 * 0.20 = 20.0

  AI_READY_SCORE = 19.9 + 19.9 + 15.9 + 15.0 + 20.0
                 = 90.7
```

---

## Quality Metrics & Drill-Down

### 4.1 Quality Improvement Analysis

**Location**: `backend/src/primedata/api/quality_improvement.py`

**Endpoint**: `GET /api/v1/products/{id}/quality-improvement`

**Purpose**: Provide detailed quality metrics with drill-down capabilities

**Response Structure**:
```json
{
  "product_id": "6b62f3a3-ffbf-4606-a74a-6df7ec9117be",
  "version": 1,
  "quality_summary": {
    "overall_quality": 75.3,
    "total_chunks": 5000,
    "excellent_ratio": 0.50,
    "good_ratio": 0.36,
    "fair_ratio": 0.12,
    "poor_ratio": 0.02
  },
  "quality_distribution": {
    "excellent": {
      "count": 2500,
      "avg_score": 95.5,
      "avg_coherence": 85.0,
      "avg_noise": 8.0
    },
    "good": {
      "count": 1800,
      "avg_score": 80.2,
      "avg_coherence": 70.0,
      "avg_noise": 20.0
    },
    "fair": {
      "count": 600,
      "avg_score": 65.8,
      "avg_coherence": 55.0,
      "avg_noise": 35.0
    },
    "poor": {
      "count": 100,
      "avg_score": 45.0,
      "avg_coherence": 40.0,
      "avg_noise": 55.0
    }
  },
  "issues": {
    "low_coherence_chunks": 450,
    "high_noise_chunks": 300,
    "mid_sentence_chunks": 200,
    "extraction_issues": 50
  },
  "recommendations": [
    "Review 450 chunks with low coherence - consider sentence re-combining",
    "300 chunks have high noise - check for OCR artifacts or encoding issues",
    "200 chunks start/end mid-sentence - adjust chunking strategy",
    "Overall quality is GOOD (75.3) - ready for production with monitoring"
  ]
}
```

### 4.2 Chunk Quality Drill-Down

**Location**: `backend/src/primedata/api/chunk_quality.py`

**Endpoint**: `GET /api/v1/chunk-quality/products/{product_id}/versions/{version}/chunks`

**Purpose**: Retrieve individual chunks with quality scores

**Query Parameters**:
```
confidence_min=70      # Minimum confidence score
confidence_max=100     # Maximum confidence score
noise_max=30          # Maximum noise score
coherence_min=60      # Minimum coherence score
source_file=File1.pdf # Filter by source file
sort_by=confidence    # Sort by: confidence, coherence, noise, chunk_index
sort_order=desc       # Sort order: asc or desc
offset=0              # Pagination offset
limit=100             # Pagination limit
```

**Response Structure**:
```json
{
  "product_id": "6b62f3a3-ffbf-4606-a74a-6df7ec9117be",
  "version": 1,
  "chunks": [
    {
      "id": "chunk_123",
      "metadata": {
        "chunk_id": "file1_section2_chunk45",
        "chunk_text": "The quick brown fox jumps over...",
        "chunk_order": 45,
        "source_file": "File1.pdf",
        "section": "Chapter 2",
        "page_number": 42,
        "confidence_score": 87.5,
        "noise_score": 12.3,
        "coherence_score": 78.9
      },
      "quality_issues": []
    },
    {
      "id": "chunk_124",
      "metadata": {
        "chunk_id": "file1_section2_chunk46",
        "chunk_text": "...",
        "confidence_score": 65.0,
        "noise_score": 45.0,
        "coherence_score": 55.0
      },
      "quality_issues": [
        "low_confidence",
        "high_noise",
        "low_coherence"
      ]
    }
  ],
  "total_count": 5000,
  "returned_count": 100,
  "offset": 0,
  "limit": 100,
  "has_more": true,
  "quality_summary": {
    "total_checked": 5000,
    "total_retained": 4850,
    "filtered_out": 150,
    "avg_confidence": 84.5,
    "avg_noise": 18.3
  }
}
```

---

## Complete Example Workflow

### Step-by-Step Example

```
┌─────────────────────────────────────────────────────────────┐
│ USER UPLOADS 2 FILES                                        │
│ • Document1.pdf (45 pages, 15MB)                            │
│ • Document2.docx (20 pages, 3MB)                            │
└──────────────────────┬────────────────────────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────┐
    │ API CREATES RAWFILE RECORDS           │
    │ ├─ raw_files[0]:                      │
    │ │  ├─ filename: Document1.pdf         │
    │ │  ├─ storage_key: ws/.../doc1.pdf    │
    │ │  ├─ file_size: 15728640 bytes       │
    │ │  ├─ checksum: sha256:abc123...      │
    │ │  └─ status: ingested                │
    │ │                                     │
    │ └─ raw_files[1]:                      │
    │    ├─ filename: Document2.docx        │
    │    ├─ storage_key: ws/.../doc2.docx   │
    │    ├─ file_size: 3145728 bytes        │
    │    └─ checksum: sha256:def456...      │
    └──────────────────┬───────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────┐
    │ AIRFLOW PIPELINE TRIGGERED            │
    │ Creates PipelineRun record            │
    │ ├─ status: RUNNING                    │
    │ ├─ product_id: 6b62f3a3-...           │
    │ ├─ version: 1                         │
    │ └─ start_time: 2026-03-31T10:00:00Z   │
    └──────────────────┬───────────────────┘
                       │
         ┌─────────────┴──────────────┐
         │                            │
         ▼                            ▼
    ┌──────────────┐         ┌──────────────────┐
    │ PREPROCESS   │         │ Wait for other   │
    │              │         │ stages...        │
    │ Extract:     │         │                  │
    │ • 2850 chunks│         │ SCORING:         │
    │   from doc1  │         │ • Calc metrics   │
    │ • 980 chunks │         │ • Coherence      │
    │   from doc2  │         │ • Noise          │
    │ • TOTAL: 3830│         │ • Confidence     │
    │   chunks     │         │                  │
    │              │         │ VALIDATION:      │
    │ Save:        │         │ • DQ rules       │
    │ processed_   │         │ • Violations     │
    │ chunks_      │         │                  │
    │ *.jsonl      │         │ FINGERPRINT:     │
    └──────────────┘         │ • AI ready score │
         │                   │ • Trust score    │
         └──────────┬────────┘                  │
                    │                          │
                    ▼                          │
        ┌───────────────────────────┐         │
        │ ALL METRICS CALCULATED    │         │
        │                           │         │
        │ Chunk Statistics:         │         │
        │ • Avg confidence: 84.5    │         │
        │ • Avg coherence: 72.1    │         │
        │ • Avg noise: 18.3         │         │
        │ • Avg trust: 75.8         │         │
        │                           │         │
        │ Distribution:             │         │
        │ • Excellent: 1950 (50.9%) │         │
        │ • Good: 1384 (36.1%)      │         │
        │ • Fair: 426 (11.1%)       │         │
        │ • Poor: 70 (1.8%)         │         │
        │                           │         │
        │ DQ Violations:            │         │
        │ • Missing required fields: 12       │
        │ • Out-of-range values: 5  │         │
        │ • Total violations: 17    │         │
        │                           │         │
        │ Policy Status:            │         │
        │ • PASSED (no violations)  │         │
        └───────────────────────────┘         │
                    │                          │
                    ▼                          │
        ┌───────────────────────────┐         │
        │ FINGERPRINT GENERATED     │         │
        │                           │         │
        │ AI Ready Score:           │         │
        │ ┌─────────────────────┐   │         │
        │ │ Data Quality: 78.9  │   │         │
        │ │ Completeness: 85.5  │   │         │
        │ │ Consistency: 74.2   │   │         │
        │ │ Coverage: 98.0      │   │         │
        │ │ Compliance: 100.0   │   │         │
        │ └─────────────────────┘   │         │
        │                           │         │
        │ FINAL SCORE: 86.7         │         │
        │ STATUS: EXCELLENT         │         │
        │                           │         │
        │ Recommendation:           │         │
        │ "Ready for AI/RAG with    │         │
        │  excellent data quality"  │         │
        │                           │         │
        └───────────────────────────┘         │
                    │                          │
                    ▼                          │
        ┌──────────────────────────┐         │
        │ PRODUCTS TABLE UPDATED   │         │
        │                          │         │
        │ products[id]:            │         │
        │ ├─ current_version: 1    │         │
        │ ├─ trust_score: 75.8     │         │
        │ ├─ status: completed     │         │
        │ ├─ policy_status: PASSED │         │
        │ ├─ readiness_fingerprint │         │
        │ │  _path: s3://.../      │         │
        │ │  fingerprint.json      │         │
        │ └─ readiness_score: 86.7 │         │
        └──────────────────────────┘         │
                    │                          │
                    ▼                          │
        ┌──────────────────────────┐         │
        │ INDEXING STAGE           │         │
        │                          │         │
        │ • Embed 3830 chunks      │         │
        │ • Create OpenSearch      │         │
        │   collection             │         │
        │ • Index vectors + score  │         │
        │   metadata               │         │
        │                          │         │
        │ Status: COMPLETED        │         │
        └──────────────────────────┘         │
                    │                          │
                    ▼                          │
        ┌──────────────────────────┐         │
        │ PIPELINE COMPLETE        │         │
        │                          │         │
        │ PipelineRun Status:      │         │
        │ ├─ status: COMPLETED     │         │
        │ ├─ end_time: now()       │         │
        │ ├─ metrics: {...}        │         │
        │ └─ artifacts: {...}      │         │
        │                          │         │
        │ Available APIs:          │         │
        │ ├─ /chunks - Vector      │         │
        │ │  search                │         │
        │ ├─ /quality-improvement  │         │
        │ │  - Quality metrics     │         │
        │ ├─ /lineage - Flow trace │         │
        │ └─ /artifacts - Files    │         │
        └──────────────────────────┘         │
```

---

## Key Takeaways

### 1. **Extraction Pipeline**
- Files uploaded → Text extracted → Normalized → Chunked → Scored

### 2. **Quality Scoring**
- Each chunk gets 3 scores: Confidence, Coherence, Noise
- Aggregated into overall Trust score for the product
- Distribution tracked: excellent/good/fair/poor

### 3. **AI Ready Score**
- Combines 5 components (25% weighted average)
- Ranges from 0-100
- Indicates production readiness for AI/RAG applications

### 4. **Metrics Available**
- Individual chunk scores in OpenSearch
- Aggregated metrics in fingerprint
- Drill-down analysis via quality improvement API

### 5. **Compliance & Governance**
- Policy evaluation integrated
- DQ violations tracked
- Lineage maintained throughout pipeline

---

**For more details**: See `detailed_workflow.md` for architecture, API endpoints, and database schema.
