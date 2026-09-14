# PrimeData Backend - Detailed Technical Workflow

## Table of Contents
1. [Application Architecture](#application-architecture)
2. [Request Flow & Processing](#request-flow--processing)
3. [Database Schema & Models](#database-schema--models)
4. [API Endpoints Categorized](#api-endpoints-categorized)
5. [Pipeline Orchestration](#pipeline-orchestration)
6. [Data Persistence](#data-persistence)
7. [Error Handling & Recovery](#error-handling--recovery)
8. [Performance Optimization](#performance-optimization)

---

## Application Architecture

### Layered Architecture

```
┌─────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER (Frontend)                          │
│  React + TypeScript + Tailwind CSS                      │
└────────────────────┬────────────────────────────────────┘
                     │ REST API (JSON over HTTPS)
┌────────────────────▼────────────────────────────────────┐
│  API GATEWAY LAYER (FastAPI)                            │
│  • Request validation (Pydantic models)                 │
│  • JWT authentication & authorization                   │
│  • CORS handling & security headers                     │
│  • Request/response logging                             │
│  • Rate limiting & throttling                           │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
┌───────▼──────┐ ┌──▼───────┐ ┌──▼──────────┐
│ APPLICATION  │ │ BUSINESS │ │ INTEGRATION │
│ SERVICES     │ │ LOGIC    │ │ SERVICES    │
│              │ │          │ │             │
│• Auth        │ │• Quality │ │• Pipeline   │
│• ACL         │ │  Metrics │ │• Storage    │
│• Audit       │ │• Lineage │ │• Vector DB  │
│• Versioning  │ │• Policies│ │• Analytics  │
└──────────────┘ └──────────┘ └─────────────┘
        │            │            │
        └────────────┼────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  DATA ACCESS LAYER (SQLAlchemy ORM)                     │
│  • Database session management                          │
│  • Query building & optimization                        │
│  • Transaction handling                                 │
│  • Lazy loading & eager loading                         │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┬──────────────┐
        │            │            │              │
┌───────▼──┐ ┌──────▼──────┐ ┌──▼──────┐ ┌────▼─────┐
│PostgreSQL│ │ OpenSearch  │ │ S3/GCS  │ │ Airflow  │
│Database  │ │ Vectors     │ │ Storage │ │ Scheduler│
└──────────┘ └─────────────┘ └─────────┘ └──────────┘
```

### Component Interactions

```
USER REQUEST
    ↓
┌─────────────────────────────┐
│ FastAPI Endpoint Handler    │
│ • Validate JWT token        │
│ • Parse request parameters  │
│ • Validate input (Pydantic) │
└────────┬────────────────────┘
         ↓
┌─────────────────────────────┐
│ Service Layer               │
│ • Check permissions (ACL)   │
│ • Fetch from DB/Cache       │
│ • Apply business logic      │
│ • Format response           │
└────────┬────────────────────┘
         ↓
┌─────────────────────────────┐
│ Data Layer                  │
│ • Query builder             │
│ • Execute SQL               │
│ • Manage connections        │
│ • Handle transactions       │
└────────┬────────────────────┘
         ↓
┌─────────────────────────────┐
│ Database/Storage            │
│ • PostgreSQL tables         │
│ • OpenSearch indices        │
│ • S3/GCS objects            │
└──────────────────────────────┘
```

---

## Request Flow & Processing

### Example: File Upload Request

```
POST /api/v1/datasources/{id}/upload-files

1. REQUEST ARRIVAL
   ├─ Headers: Authorization: Bearer <JWT>
   ├─ Body: multipart/form-data with files
   └─ Content-Type: multipart/form-data

2. AUTHENTICATION & VALIDATION
   ├─ Extract JWT from Authorization header
   ├─ Verify JWT signature
   ├─ Decode JWT → get user_id
   ├─ Validate datasource_id format (UUID)
   ├─ Validate files present in request
   └─ Check file size limits

3. AUTHORIZATION CHECK
   ├─ Query database for datasource
   ├─ Verify datasource exists
   ├─ Check datasource.type == FOLDER (only type allowed)
   ├─ Get product_id from datasource
   ├─ Query user permissions (ACL table)
   ├─ Verify user has WRITE permission on product
   └─ If not authorized → 403 Forbidden

4. DATA PREPROCESSING
   ├─ Get product current version
   ├─ Calculate storage bucket path:
   │  └─ s3://bucket/{S3_METADATA_PATH}ws/{workspace_id}/prod/{product_id}/v{version}/
   ├─ For each file:
   │  ├─ Read file content into memory
   │  ├─ Calculate SHA256 checksum
   │  ├─ Sanitize filename
   │  ├─ Determine content type
   │  └─ Store in variables for processing

5. STORAGE OPERATIONS
   ├─ For each file:
   │  ├─ Generate S3 storage key: prefix + safe_filename
   │  ├─ Upload file to S3/GCS
   │  │  └─ PUT request to storage service
   │  ├─ If upload fails → log error, continue with next file
   │  └─ If upload succeeds → proceed to database entry

6. DATABASE PERSISTENCE
   ├─ For each successfully uploaded file:
   │  ├─ Create RawFile object (SQLAlchemy model)
   │  ├─ Set attributes:
   │  │  ├─ id: UUID (auto-generated)
   │  │  ├─ workspace_id, product_id, version
   │  │  ├─ filename, file_stem
   │  │  ├─ storage_bucket, storage_key
   │  │  ├─ file_size (bytes)
   │  │  ├─ file_checksum (SHA256)
   │  │  ├─ status: INGESTED
   │  │  └─ created_at, updated_at
   │  ├─ db.add(raw_file)
   │  └─ db.commit()

7. AUDIT LOGGING
   ├─ Create UserAuditLog record
   ├─ Set action: "file_uploaded"
   ├─ Set resource_id: product_id
   ├─ Set old_value: null
   ├─ Set new_value: {files_uploaded: [...]}
   ├─ db.add(audit_log)
   └─ db.commit()

8. RESPONSE FORMATTING
   ├─ Collect results:
   │  ├─ uploaded_count: number of successful uploads
   │  ├─ error_count: number of failures
   │  ├─ uploaded_files: list of uploaded file info
   │  └─ errors: list of error messages
   ├─ Create response object (Pydantic model)
   └─ Serialize to JSON

9. RESPONSE TRANSMISSION
   ├─ Set status code: 200 OK
   ├─ Set content-type: application/json
   ├─ Serialize Pydantic model to JSON
   ├─ Include CORS headers
   └─ Send response to client
```

### Example: Query Search Request

```
GET /api/v1/products/{id}/chunks?q=search_term&limit=50

1. PARAMETERS PARSING
   ├─ Extract from path: product_id (UUID)
   ├─ Extract from query: q, limit, offset, sort_by
   ├─ Set defaults: limit=50, offset=0, sort_by="relevance"
   └─ Validate: all parameters match expected types

2. AUTHENTICATION
   ├─ Extract JWT from Authorization header
   ├─ Verify JWT
   └─ Decode to get user_id

3. AUTHORIZATION
   ├─ Query Product by ID
   ├─ Check user has READ permission
   ├─ If not authorized → 403 Forbidden

4. FETCH PRODUCT METADATA
   ├─ Query database:
   │  └─ SELECT * FROM products WHERE id = ?
   ├─ Get current_version
   ├─ Get embedding_config
   └─ Get promoted_version (if exists)

5. VECTOR SEARCH PREPARATION
   ├─ Get embedding model from embedding_config
   ├─ Encode search query to vector
   │  └─ Using configured embedding model (e.g., OpenAI text-embedding-3-small)
   ├─ Create search query parameters:
   │  ├─ Vector: encoded query
   │  ├─ Top-K: limit parameter
   │  ├─ Offset: offset parameter
   │  └─ Filters: product_id = X, version = Y

6. OPENSEARCH QUERY
   ├─ Construct OpenSearch request:
   │  ├─ Collection name: {workspace_id}_{product_id}_v{version}
   │  ├─ Query type: vector similarity
   │  ├─ Top-K results: limit
   │  └─ Filters (if any): DQ score > threshold, etc.
   ├─ Execute search:
   │  └─ Call vector_search_client.search()
   ├─ Parse results:
   │  ├─ Extract vector IDs
   │  ├─ Get similarity scores
   │  └─ Retrieve metadata

7. DATA ENRICHMENT
   ├─ For each result chunk:
   │  ├─ Extract metadata from OpenSearch:
   │  │  ├─ text (chunk content)
   │  │  ├─ source (filename)
   │  │  ├─ page_number
   │  │  ├─ chunk_index
   │  │  ├─ quality_scores
   │  │  └─ created_at
   │  ├─ Extract similarity score from OpenSearch
   │  ├─ If DQ violations exist:
   │  │  ├─ Query dq_violations table
   │  │  ├─ Filter by chunk_id
   │  │  └─ Add violation details to response
   │  └─ Add lineage info (if enabled):
   │     ├─ Query lineage table
   │     └─ Include upstream/downstream entities

8. RESPONSE CONSTRUCTION
   ├─ Create ChunksResponse object:
   │  ├─ total_count: total matches
   │  ├─ offset: current offset
   │  ├─ limit: requested limit
   │  ├─ chunks: array of chunk objects
   │  └─ metadata:
   │     ├─ search_time_ms
   │     ├─ collection_name
   │     └─ version
   ├─ Serialize to JSON
   └─ Send response (200 OK)
```

---

## Database Schema & Models

### Core Models

#### User
```
users {
  id: VARCHAR(255) [PK]
  email: VARCHAR(255) [UNIQUE, NOT NULL]
  name: VARCHAR(255) [NOT NULL]
  first_name: VARCHAR(255)
  last_name: VARCHAR(255)
  auth_provider: ENUM [NOT NULL, DEFAULT: 'none']
  password_hash: VARCHAR(255)
  email_verified: BOOLEAN [DEFAULT: false]
  timezone: VARCHAR(50) [DEFAULT: 'UTC']
  created_at: TIMESTAMP [DEFAULT: now()]
  updated_at: TIMESTAMP
}

Relationships:
  - One-to-Many: workspace_memberships (WorkspaceMember)
  - One-to-Many: owned_products (Product)
  - One-to-Many: acls (ACL)
  - One-to-Many: audit_logs (UserAuditLog)
```

#### Workspace
```
workspaces {
  id: UUID [PK, DEFAULT: uuid_generate_v4()]
  name: VARCHAR(255) [NOT NULL]
  settings: JSONB [DEFAULT: {}]
  created_at: TIMESTAMP [DEFAULT: now()]
  updated_at: TIMESTAMP
}

Relationships:
  - One-to-Many: members (WorkspaceMember)
  - One-to-Many: products (Product)
  - One-to-One: billing_profile (BillingProfile)
  - One-to-Many: data_quality_rules (DataQualityRule)
```

#### Product
```
products {
  id: UUID [PK, DEFAULT: uuid_generate_v4()]
  workspace_id: UUID [FK → workspaces.id, NOT NULL]
  owner_user_id: VARCHAR(255) [FK → users.id, NOT NULL]
  name: VARCHAR(255) [NOT NULL]
  status: ENUM [DEFAULT: 'draft']
  current_version: INTEGER [DEFAULT: 0]
  promoted_version: INTEGER
  playbook_id: VARCHAR(50)
  chunking_config: JSONB
  embedding_config: JSONB
  trust_score: FLOAT
  readiness_fingerprint: JSONB
  created_at: TIMESTAMP [DEFAULT: now()]
  updated_at: TIMESTAMP
}

Relationships:
  - Many-to-One: workspace (Workspace)
  - Many-to-One: owner (User)
  - One-to-Many: data_sources (DataSource)
  - One-to-Many: raw_files (RawFile)
  - One-to-Many: pipeline_runs (PipelineRun)
```

#### RawFile
```
raw_files {
  id: UUID [PK, DEFAULT: uuid_generate_v4()]
  workspace_id: UUID [FK → workspaces.id, NOT NULL]
  product_id: UUID [FK → products.id, NOT NULL]
  version: INTEGER [NOT NULL]
  data_source_id: UUID [FK → data_sources.id]
  filename: VARCHAR(500) [NOT NULL]
  file_stem: VARCHAR(500) [NOT NULL]
  storage_bucket: VARCHAR(255) [NOT NULL]
  storage_key: VARCHAR(1000) [NOT NULL]
  file_size: BIGINT [NOT NULL]
  content_type: VARCHAR(255)
  file_checksum: VARCHAR(255)
  status: ENUM [DEFAULT: 'ingested']
  error_message: TEXT
  created_at: TIMESTAMP [DEFAULT: now()]
  updated_at: TIMESTAMP
}

Constraints:
  - UNIQUE (workspace_id, product_id, version, file_stem)

Relationships:
  - Many-to-One: product (Product)
  - Many-to-One: data_source (DataSource)
```

#### PipelineRun
```
pipeline_runs {
  id: UUID [PK, DEFAULT: uuid_generate_v4()]
  workspace_id: UUID [FK → workspaces.id, NOT NULL]
  product_id: UUID [FK → products.id, NOT NULL]
  version: INTEGER [NOT NULL]
  run_id: VARCHAR(255) [UNIQUE]
  mode: VARCHAR(50) [NOT NULL]
  status: ENUM [DEFAULT: 'queued']
  triggered_by_user_id: VARCHAR(255)
  airflow_dag_run_id: VARCHAR(255)
  start_time: TIMESTAMP
  end_time: TIMESTAMP
  error_message: TEXT
  metrics: JSONB
  created_at: TIMESTAMP [DEFAULT: now()]
}

Relationships:
  - Many-to-One: product (Product)
  - One-to-Many: artifacts (PipelineArtifact)
```

#### PipelineArtifact
```
pipeline_artifacts {
  id: UUID [PK, DEFAULT: uuid_generate_v4()]
  pipeline_run_id: UUID [FK → pipeline_runs.id, NOT NULL]
  workspace_id: UUID [NOT NULL]
  product_id: UUID [NOT NULL]
  version: INTEGER [NOT NULL]
  stage_name: VARCHAR(255) [NOT NULL]
  artifact_type: ENUM [NOT NULL]
  artifact_name: VARCHAR(255) [NOT NULL]
  storage_bucket: VARCHAR(255) [NOT NULL]
  storage_key: VARCHAR(1000) [NOT NULL]
  file_size: BIGINT
  checksum: VARCHAR(255)
  storage_etag: VARCHAR(255)
  artifact_metadata: JSONB
  status: ENUM [DEFAULT: 'active']
  retention_policy: ENUM [DEFAULT: 'auto_delete']
  created_at: TIMESTAMP [DEFAULT: now()]
  updated_at: TIMESTAMP
}

Relationships:
  - Many-to-One: pipeline_run (PipelineRun)
```

#### DqViolation
```
dq_violations {
  id: UUID [PK, DEFAULT: uuid_generate_v4()]
  workspace_id: UUID [NOT NULL]
  product_id: UUID [NOT NULL]
  version: INTEGER [NOT NULL]
  chunk_id: VARCHAR(255)
  violation_type: VARCHAR(255) [NOT NULL]
  severity: ENUM
  rule_id: VARCHAR(255)
  details: JSONB
  detected_at: TIMESTAMP [DEFAULT: now()]
}
```

#### UserAuditLog
```
user_audit_logs {
  id: UUID [PK, DEFAULT: uuid_generate_v4()]
  workspace_id: UUID
  user_id: VARCHAR(255)
  action: VARCHAR(255) [NOT NULL]
  resource_type: VARCHAR(255)
  resource_id: VARCHAR(255)
  old_value: JSONB
  new_value: JSONB
  ip_address: VARCHAR(45)
  created_at: TIMESTAMP [DEFAULT: now()]
}
```

#### ACL (Access Control List)
```
acls {
  id: UUID [PK, DEFAULT: uuid_generate_v4()]
  workspace_id: UUID
  user_id: VARCHAR(255) [FK → users.id]
  resource_type: VARCHAR(255)
  resource_id: UUID
  permission: VARCHAR(255)
  granted_at: TIMESTAMP [DEFAULT: now()]
}

Relationships:
  - Many-to-One: user (User)
```

#### DataQualityRule (Enterprise)
```
data_quality_rules {
  id: UUID [PK]
  workspace_id: UUID [FK → workspaces.id]
  product_id: UUID [FK → products.id]
  name: VARCHAR(255) [NOT NULL]
  description: TEXT
  rule_type: VARCHAR(255) [NOT NULL]
  severity: ENUM
  configuration: JSONB
  enabled: BOOLEAN [DEFAULT: true]
  created_by: VARCHAR(255) [NOT NULL]
  updated_by: VARCHAR(255)
  created_at: TIMESTAMP
  updated_at: TIMESTAMP
}
```

---

## API Endpoints Categorized

### Authentication & Users
```
POST   /api/v1/auth/login                    Login with email/password
POST   /api/v1/auth/signup                   Create new user account
POST   /api/v1/auth/refresh                  Refresh JWT token
POST   /api/v1/auth/logout                   Logout & invalidate token
GET    /api/v1/users/me                      Get current user info
PUT    /api/v1/user/profile                  Update user profile
GET    /api/v1/auth/.well-known/jwks.json   Get JWKS for token verification
```

### Workspaces & Team
```
GET    /api/v1/workspaces                    List user's workspaces
POST   /api/v1/workspaces                    Create new workspace
GET    /api/v1/workspaces/{id}               Get workspace details
PUT    /api/v1/workspaces/{id}               Update workspace
GET    /api/v1/workspaces/{id}/members       List workspace members
POST   /api/v1/workspaces/{id}/members       Invite user to workspace
DELETE /api/v1/workspaces/{id}/members/{uid} Remove member from workspace
```

### Products
```
POST   /api/v1/products                      Create new product
GET    /api/v1/products                      List products in workspace
GET    /api/v1/products/{id}                 Get product details
PUT    /api/v1/products/{id}                 Update product configuration
DELETE /api/v1/products/{id}                 Delete product
GET    /api/v1/products/{id}/versions        List product versions
```

### Data Sources & Upload
```
POST   /api/v1/datasources                   Create data source
GET    /api/v1/datasources                   List data sources for product
GET    /api/v1/datasources/{id}              Get datasource details
POST   /api/v1/datasources/{id}/upload-files Upload files (multi-file batch)
POST   /api/v1/datasources/{id}/test-config  Test datasource configuration
DELETE /api/v1/datasources/{id}              Delete data source
```

### Pipeline & Orchestration
```
POST   /api/v1/pipeline/run                  Trigger pipeline execution
GET    /api/v1/pipeline/runs                 List pipeline runs
GET    /api/v1/pipeline/runs/{id}            Get pipeline run status
POST   /api/v1/pipeline/runs/{id}/stop       Stop running pipeline
GET    /api/v1/pipeline/artifacts            List pipeline artifacts
GET    /api/v1/pipeline/artifacts/{id}       Get artifact details
POST   /api/v1/pipeline/{id}/promote         Promote version to production
```

### Chunks & Search
```
GET    /api/v1/products/{id}/chunks          Vector search over chunks
GET    /api/v1/products/{id}/chunks/{cid}    Get specific chunk details
GET    /api/v1/chunk-quality/products/{id}/versions/{v}/chunks  Get chunks with quality scores
GET    /api/v1/products/{id}/quality-improvement  Get quality improvement metrics
```

### Data Quality
```
GET    /api/v1/products/{id}/rules           List DQ rules for product
PUT    /api/v1/products/{id}/rules           Update DQ rules
POST   /api/v1/products/{id}/rules/seed      Initialize default DQ rules
GET    /api/v1/products/{id}/violations      Get DQ violations
GET    /api/v1/products/{id}/report          Get DQ compliance report
```

### AI Readiness & Analytics
```
GET    /api/v1/ai-readiness/assess/{id}      Assess AI readiness
POST   /api/v1/ai-readiness/improve/{id}     Get improvement recommendations
GET    /api/v1/analytics/metrics             Get workspace analytics
GET    /api/v1/products/{id}/insights        Get product insights
```

### Governance & Compliance
```
GET    /api/v1/lineage/{id}                  Get data lineage
GET    /api/v1/lineage/{id}/upstream         Get upstream dependencies
GET    /api/v1/lineage/{id}/downstream       Get downstream dependencies
POST   /api/v1/acl                           Create access control rule
GET    /api/v1/acl                           List ACL rules
DELETE /api/v1/acl/{id}                      Delete ACL rule
```

### Audit & Logs
```
GET    /api/v1/audit/logs                    List audit logs
GET    /api/v1/audit/logs/user/{uid}         Get user activity timeline
GET    /api/v1/audit/logs/resource/{rid}     Get resource change history
GET    /api/v1/audit/export                  Export audit logs
GET    /api/v1/audit/stats                   Get audit statistics
```

### Billing
```
POST   /api/v1/billing/checkout-session      Create Stripe checkout session
GET    /api/v1/billing/portal                Get Stripe billing portal URL
GET    /api/v1/billing/limits                Get plan usage limits
POST   /api/v1/billing/webhook               Stripe webhook handler
```

### Health & Config
```
GET    /health                               Health check (combined services)
GET    /health/simple                        Simple liveness probe
POST   /api/v1/config/validate               Validate system configuration
GET    /api/v1/embeddings                    List available embedding models
GET    /api/v1/chunking-strategies           List chunking strategies
GET    /api/v1/playbooks                     List available playbooks
```

---

## Pipeline Orchestration

### Airflow DAG Structure

```
PrimeData DAG (Triggered for each product/version)
│
├─ Stage: Initialize Pipeline
│  ├─ Task: create_pipeline_run
│  │  └─ Creates PipelineRun record in DB
│  ├─ Task: validate_inputs
│  │  └─ Check product exists, version valid
│  └─ Task: setup_storage
│     └─ Initialize S3/GCS paths
│
├─ Stage: Data Ingestion
│  ├─ Task: fetch_raw_files
│  │  └─ Query RawFile records from DB
│  ├─ Task: validate_files
│  │  └─ Check files exist in S3, verify checksums
│  └─ Task: map_file_metadata
│     └─ Create file_stem → storage_key mapping
│
├─ Stage: Preprocessing
│  ├─ Task: preprocess_documents
│  │  ├─ Load documents from S3
│  │  ├─ Apply normalizers
│  │  ├─ Detect sections
│  │  ├─ Apply chunking strategy
│  │  └─ Output: processed_chunks_*.jsonl
│  └─ Task: register_preprocess_artifacts
│     └─ Create PipelineArtifact records
│
├─ Stage: Scoring
│  ├─ Task: calculate_quality_metrics
│  │  ├─ For each chunk: score coherence, noise, sentence boundaries
│  │  ├─ Aggregate scores per document
│  │  └─ Output: metrics.json
│  └─ Task: register_scoring_artifacts
│     └─ Create PipelineArtifact record
│
├─ Stage: Validation
│  ├─ Task: apply_dq_rules
│  │  ├─ Load DQ rules from DB
│  │  ├─ For each chunk: check compliance
│  │  ├─ Record violations in dq_violations table
│  │  └─ Output: validation_summary.csv
│  └─ Task: register_validation_artifacts
│     └─ Create PipelineArtifact record
│
├─ Stage: Analysis
│  ├─ Task: calculate_fingerprint
│  │  ├─ Calculate AI Trust Score
│  │  ├─ Generate readiness metrics
│  │  └─ Output: fingerprint.json
│  ├─ Task: generate_reports
│  │  ├─ Generate trust report PDF
│  │  └─ Output: trust_report.pdf
│  └─ Task: register_analysis_artifacts
│     └─ Create PipelineArtifact records
│
├─ Stage: Indexing
│  ├─ Task: prepare_embeddings
│  │  ├─ Prepare chunks for embedding
│  │  ├─ Set up embedding model
│  │  └─ Chunk large files if needed
│  ├─ Task: embed_chunks
│  │  ├─ For each chunk: generate vector embedding
│  │  ├─ Add metadata to vector
│  │  └─ Collect all vectors for batch insert
│  ├─ Task: create_opensearch_collection
│  │  ├─ Create collection with appropriate vector size
│  │  └─ Configure similarity metric
│  ├─ Task: index_vectors
│  │  ├─ Batch insert all vectors into OpenSearch
│  │  ├─ Verify index health
│  │  └─ Output: indexed vector count
│  └─ Task: register_indexing_artifacts
│     └─ Create PipelineArtifact record
│
└─ Stage: Finalize
   ├─ Task: update_product_state
   │  ├─ Update Product.current_version
   │  ├─ Update Product.trust_score
   │  ├─ Update Product.readiness_fingerprint
   │  └─ db.commit()
   ├─ Task: mark_pipeline_complete
   │  ├─ Update PipelineRun.status = SUCCEEDED
   │  ├─ Set end_time
   │  └─ db.commit()
   └─ Task: send_notifications
      ├─ Send Slack notification (if enabled)
      ├─ Send email to product owner
      └─ Log completion event
```

### Error Handling in Pipeline

```
At any stage failure:
│
├─ Catch exception in Airflow task
├─ Log error with full traceback
├─ Update PipelineRun.status = FAILED
├─ Set PipelineRun.error_message = error description
├─ Mark associated RawFile records as FAILED
├─ Send failure notification to product owner
├─ Store metrics/state for recovery
└─ Return task as FAILED (Airflow marks DAG as FAILED)

User can then:
├─ Review error message in UI
├─ Fix root cause (e.g., update DQ rules)
├─ Trigger new pipeline run
└─ System processes files again from beginning
```

---

## Data Persistence

### Database Transactions

```
UPLOAD TRANSACTION
BEGIN TRANSACTION
  ├─ FOR EACH FILE:
  │  ├─ Create RawFile object
  │  ├─ db.add(raw_file)
  │  └─ (NOT yet committed)
  ├─ Create UserAuditLog
  ├─ db.add(audit_log)
  └─ db.commit()  ← All-or-nothing
END TRANSACTION
```

### S3/GCS Data Organization

```
Bucket Structure:
s3://bucket/
  └─ {S3_METADATA_PATH}/
     └─ ws/{workspace_id}/
        └─ prod/{product_id}/
           ├─ v1/
           │  ├─ raw_documents/
           │  │  ├─ document1.pdf
           │  │  ├─ document2.docx
           │  │  └─ document3.xlsx
           │  ├─ processed_chunks_document1.jsonl
           │  ├─ processed_chunks_document2.jsonl
           │  ├─ processed_chunks_document3.jsonl
           │  ├─ metrics.json
           │  ├─ validation_summary.csv
           │  ├─ fingerprint.json
           │  ├─ trust_report.pdf
           │  └─ vector_metadata.json
           ├─ v2/
           │  └─ (similar structure)
           └─ exports/
              ├─ export_2024_01_15.zip
              └─ export_2024_01_20.zip
```

### OpenSearch Vector Index

```
Collection Name: {workspace_id}_{product_id}_v{version}

Vector Document Structure:
{
  "id": "chunk_001",
  "vector": [0.123, 0.456, ..., 0.789],  // 1536 dims for OpenAI
  "metadata": {
    "text": "chunk content",
    "source": "document1.pdf",
    "page_number": 1,
    "chunk_index": 1,
    "section": "Introduction",
    "quality_scores": {
      "coherence": 0.95,
      "noise": 0.05,
      "sentence_complete": true
    },
    "timestamps": {
      "processed_at": "2024-01-15T10:30:00Z",
      "indexed_at": "2024-01-15T10:35:00Z"
    }
  }
}
```

---

## Error Handling & Recovery

### Common Error Scenarios

```
SCENARIO 1: File Upload Fails Midway
├─ File 1: Uploaded ✓
├─ File 2: Upload error (network timeout)
├─ File 3: Uploaded ✓
└─ Response:
   {
     "success": false,
     "uploaded_count": 2,
     "error_count": 1,
     "errors": ["Failed to upload file2.pdf: timeout"]
   }

Recovery:
├─ User retries upload with just file2.pdf
├─ File2 uploaded successfully
└─ All 3 files now in system

SCENARIO 2: Insufficient Permissions
├─ User lacks WRITE permission on product
├─ Request rejected before file processing
└─ Response: 403 Forbidden

SCENARIO 3: Pipeline Preprocessing Fails
├─ File 1: Processed ✓
├─ File 2: Preprocessing error (unsupported encoding)
├─ File 3: Skipped (dependency on File 2)
└─ Pipeline status: FAILED

Recovery Options:
├─ Fix file format and retry
├─ OR skip problematic file and reprocess others
└─ System supports partial pipeline re-runs
```

### Retry Strategy

```
AUTOMATIC RETRIES
├─ S3/GCS connection errors: retry up to 3 times with exponential backoff
├─ Database connection errors: retry up to 5 times with 5s backoff
└─ Transient errors: retry with jitter to avoid thundering herd

MANUAL RETRIES
├─ User triggers pipeline run again
├─ System checks which stages succeeded
├─ User can choose to:
│  ├─ Reprocess entire pipeline (default)
│  ├─ Skip to next stage (manual intervention)
│  └─ Rerun specific stage only (expert mode)
└─ Audit log records retry with reason
```

---

## Performance Optimization

### Database Optimization

```
INDEXES CREATED
├─ users(email, auth_provider)           // Fast user lookups
├─ workspaces(created_at)                // Sort/filter by time
├─ products(workspace_id, status)        // Filter by workspace & status
├─ raw_files(product_id, version)        // Fast file queries
├─ pipeline_runs(product_id, status)     // Track runs per product
├─ pipeline_artifacts(pipeline_run_id)   // Get artifacts per run
├─ dq_violations(product_id, version)    // Fast violation queries
├─ user_audit_logs(user_id, resource_id) // Audit trail lookups
└─ acls(user_id, resource_id)            // Permission checks

QUERY OPTIMIZATION
├─ Use eager loading for relationships (selectin)
├─ Pagination: limit 100, offset-based
├─ Batch operations: insert 1000 records at once
└─ Connection pooling: max 20 connections
```

### Caching Strategy

```
CACHEABLE DATA (5-minute TTL)
├─ Product configuration (chunking, embedding)
├─ DQ rules for product
├─ User permissions (ACLs)
├─ Embedding model configs
└─ Playbook definitions

CACHE INVALIDATION
├─ On product update: invalidate product config cache
├─ On rule change: invalidate DQ rules cache
├─ On ACL change: invalidate permission cache
├─ Automatic: 5-minute expiry

CACHE BACKEND
├─ Redis (production)
├─ In-memory (development/testing)
└─ Key format: {resource_type}:{resource_id}:{version}
```

### Storage Optimization

```
FILE SIZE CONSIDERATIONS
├─ Raw files: unlimited size (stream to S3)
├─ Processed chunks: ~10-50MB per file (compressed JSONL)
├─ Metrics: ~1-5MB per product version
├─ Fingerprint: ~100-500KB (small JSON)
├─ Trust report: 1-10MB (PDF)
└─ Vectors in OpenSearch: 8 bytes × dim × count
   └─ Example: 1536 dims × 5000 chunks ≈ 60MB

COMPRESSION
├─ JSONL files: gzip compressed
├─ Metadata: JSONB in PostgreSQL (compressed)
└─ Exports: ZIP format with compression
```

---

## Summary

The detailed workflow shows:

1. **Request Processing**: Multi-layer validation, authentication, authorization
2. **Data Persistence**: Atomic transactions, proper foreign keys, audit trails
3. **Pipeline Execution**: Orchestrated through Airflow with error recovery
4. **Storage Strategy**: Hierarchical S3 structure with proper partitioning
5. **Optimization**: Indexes, caching, query optimization, batch operations
6. **Error Handling**: Graceful degradation, retry strategies, user-friendly errors

The system is designed for enterprise-grade reliability, scalability, and compliance requirements.

See **api_spec.json** for complete OpenAPI specification and **sql_queries.sql** for database operations.
