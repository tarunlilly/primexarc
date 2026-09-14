# PrimeData Backend - Complete Workflow Overview

## Table of Contents
1. [System Architecture](#system-architecture)
2. [User Journey](#user-journey)
3. [Core Workflows](#core-workflows)
4. [Data Flow](#data-flow)
5. [Key Components](#key-components)
6. [Technology Stack](#technology-stack)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                            │
│                    (Frontend Application)                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/REST
┌──────────────────────────▼──────────────────────────────────────┐
│                      API GATEWAY                                │
│              (FastAPI Application - Python)                     │
├──────────────────────────────────────────────────────────────────┤
│ ├─ Authentication & Authorization (JWT tokens)                  │
│ ├─ CORS Handling & Security Headers                             │
│ ├─ Request/Response Validation (Pydantic)                       │
│ └─ API Routing & Rate Limiting                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
    ┌───────▼──────┐  ┌───▼──────┐  ┌───▼──────────┐
    │   PostgreSQL │  │ OpenSearch│  │  S3/GCS      │
    │   Database   │  │  Vectors  │  │  Storage     │
    └──────────────┘  └───────────┘  └──────────────┘
            │              │              │
            └──────────────┼──────────────┘
                           │
        ┌──────────────────▼─────────────────┐
        │  AIRFLOW ORCHESTRATION             │
        │  (DAG-based Pipeline Execution)    │
        ├───────────────────────────────────┤
        │ ├─ Data Ingestion Stages           │
        │ ├─ Data Processing (AIRD)          │
        │ ├─ Quality Validation              │
        │ ├─ Vector Indexing                 │
        │ ├─ Reporting & Analytics           │
        │ └─ Governance & Compliance         │
        └───────────────────────────────────┘
```

---

## User Journey

### Phase 1: Workspace & Product Setup
```
1. User Signup/Login
   └─> Authentication via JWT
   └─> Workspace Creation
   └─> Workspace Role Assignment

2. Product Configuration
   └─> Define Product
   └─> Set Use Case
   └─> Configure Playbook & Chunking
```

### Phase 2: Data Ingestion
```
3. Add Data Sources
   └─> Folder Connector (for local uploads)
   └─> Web Connector (URL-based)
   └─> Cloud Connector (S3/GCS)

4. Upload Files
   └─> Multi-file batch upload
   └─> File validation (checksum, size, type)
   └─> Storage to S3/GCS
   └─> RawFile metadata in database
```

### Phase 3: Pipeline Execution
```
5. Trigger Ingestion Pipeline
   └─> Initial ingest (discovery & validation)
   └─> OR Process new version

6. Pipeline Stages Executed
   └─> Preprocessing (normalization, chunking)
   └─> Scoring (quality metrics)
   └─> Validation (DQ rules)
   └─> Reporting (trust report generation)
   └─> Indexing (vector embeddings)
```

### Phase 4: Analysis & Insights
```
7. View Results
   └─> Quality metrics & drill-down
   └─> AI Readiness score
   └─> Trust report & fingerprint
   └─> Vector search capabilities

8. Apply Governance
   └─> Set data quality rules
   └─> Define access controls (ACL)
   └─> Track audit logs
   └─> Monitor data lineage
```

---

## Core Workflows

### Workflow 1: File Upload to Vector Search

```
USER UPLOAD
    │
    ├─> POST /api/v1/datasources/{id}/upload-files
    │   ├─ Validate datasource type (FOLDER only)
    │   ├─ Validate user access
    │   ├─ For each file:
    │   │  ├─ Read file content
    │   │  ├─ Calculate SHA256 checksum
    │   │  ├─ Upload to S3/GCS
    │   │  └─ Create RawFile record in DB
    │   └─ Return upload status
    │
AIRFLOW PIPELINE (Triggered manually or scheduled)
    │
    ├─> Ingestion Pipeline Run Created
    │   └─ PipelineRun record in database
    │
    ├─> Stage: Fetch Raw Files
    │   ├─ Query RawFile records from DB
    │   ├─ Validate files exist in S3
    │   └─ Map file stems to storage keys
    │
    ├─> Stage: Preprocessing
    │   ├─ Load document from S3
    │   ├─ Apply normalizers (remove headers, etc.)
    │   ├─ Detect sections & structure
    │   ├─ Apply chunking strategy (sentence/paragraph/char)
    │   ├─ Save processed_chunks_*.jsonl to S3
    │   └─ Register artifact
    │
    ├─> Stage: Scoring
    │   ├─ Calculate quality metrics for chunks
    │   ├─ Score coherence, noise, sentence endings
    │   ├─ Generate metrics.json
    │   └─ Register artifact
    │
    ├─> Stage: Validation
    │   ├─ Apply data quality rules
    │   ├─ Detect violations (missing fields, etc.)
    │   ├─ Generate validation_summary.csv
    │   └─ Register artifact
    │
    ├─> Stage: Fingerprinting
    │   ├─ Calculate trust score
    │   ├─ Generate AI readiness metrics
    │   ├─ Create fingerprint.json
    │   └─ Register artifact
    │
    ├─> Stage: Reporting
    │   ├─ Generate trust report PDF
    │   ├─ Include summary & recommendations
    │   └─ Register artifact
    │
    ├─> Stage: Indexing
    │   ├─ Embed all chunks using LLM
    │   ├─ Create OpenSearch collection
    │   ├─ Index vectors in OpenSearch
    │   └─ Register artifact with collection name
    │
    └─> PipelineRun Status: COMPLETED

ARTIFACTS AVAILABLE
    │
    ├─> API: GET /api/v1/pipeline/artifacts
    │   └─ Returns all stage artifacts with file sizes
    │
    ├─> API: GET /api/v1/products/{id}/chunks
    │   └─ Vector search over indexed chunks
    │
    └─> API: GET /api/v1/products/{id}/quality-improvement
        └─ Quality metrics with drill-down
```

### Workflow 2: Quality Control & Governance

```
SETUP QUALITY RULES
    │
    ├─> GET /api/v1/products/{id}/rules
    │   └─ List seed data quality rules
    │
    └─> POST /api/v1/products/{id}/rules/seed?overwrite=true
        ├─ Initialize default DQ rules
        ├─ Rules created with current_user as created_by
        └─ Store in database (data_quality_rules table)

VALIDATION DURING PIPELINE
    │
    ├─> Validation Stage
    │   ├─ Load validation rules from DB
    │   ├─ For each chunk:
    │   │  ├─ Check required fields presence
    │   │  ├─ Check field value ranges
    │   │  ├─ Check pattern matching
    │   │  ├─ Record violations if found
    │   │  └─ Update DQ metrics
    │   └─ Generate validation_summary.csv
    │
    └─> Store violations in dq_violations table

VIEW VIOLATIONS
    │
    └─> GET /api/v1/products/{id}/violations
        ├─ Retrieve DQ violations for product
        ├─ Filter by severity (error, warning)
        └─ Return detailed violation info

GOVERNANCE & COMPLIANCE
    │
    ├─> Set Access Control (ACL)
    │   └─ POST /api/v1/acl
    │       ├─ Define who can access product
    │       ├─ Set permissions (READ, WRITE, ADMIN)
    │       └─ Store in ACL table
    │
    ├─> Track Audit Logs
    │   └─> All operations logged to audit table
    │       ├─ User action (view, edit, delete)
    │       ├─ Resource changed
    │       ├─ Timestamp & IP address
    │       └─ Old & new values
    │
    └─> View Lineage
        └─> GET /api/v1/lineage/{product_id}
            ├─ Show data flow from sources to outputs
            ├─ Track transformations applied
            └─ Visualize dependencies
```

### Workflow 3: Analytics & Insights

```
AGGREGATE METRICS
    │
    ├─> GET /api/v1/analytics/metrics
    │   ├─ Get workspace-level metrics
    │   ├─ Query all products in workspace
    │   ├─ Aggregate:
    │   │  ├─ Total files processed
    │   │  ├─ Total chunks generated
    │   │  ├─ Average quality score
    │   │  ├─ Data size metrics
    │   │  └─ DQ violation counts
    │   └─ Return analytics response
    │
    └─> GET /api/v1/products/{id}/insights
        ├─ Product-specific insights
        ├─ Quality trends
        ├─ Performance metrics
        └─ Recommendations

AI READINESS ASSESSMENT
    │
    ├─> GET /api/v1/ai-readiness/assess/{product_id}
    │   ├─ Calculate readiness score
    │   ├─ Evaluate:
    │   │  ├─ Data quality
    │   │  ├─ Completeness
    │   │  ├─ Consistency
    │   │  ├─ Coverage
    │   │  └─ Compliance
    │   └─ Return readiness metrics
    │
    └─> POST /api/v1/ai-readiness/improve/{product_id}
        └─ Get AI-powered recommendations for improvements

QUALITY IMPROVEMENT
    │
    └─> GET /api/v1/products/{id}/quality-improvement
        ├─ Calculate quality scores for chunks
        ├─ Identify:
        │  ├─ Low quality chunks (coherence < threshold)
        │  ├─ High noise chunks (noise > threshold)
        │  └─ Mid-sentence chunks (incomplete sentences)
        ├─ Drill-down details
        └─ Actionable recommendations
```

---

## Data Flow

### From File Upload to Query

```
User's Computer
    │
    └─> File1.pdf, File2.docx, File3.xlsx
            │
            ├─ POST /api/v1/datasources/{id}/upload-files
            │
    ┌───────▼────────────────────────┐
    │      AWS S3 / Google Cloud      │
    │                                 │
    │  s3://bucket/ws/{ws}/prod/{p}/  │
    │  ├─ File1.pdf                   │
    │  ├─ File2.docx                  │
    │  └─ File3.xlsx                  │
    │                                 │
    └───────┬────────────────────────┘
            │
    ┌───────▼────────────────────────────────┐
    │      PostgreSQL Database                │
    │                                         │
    │  RawFile Table                          │
    │  ├─ id, filename, storage_key           │
    │  ├─ file_size, checksum, status         │
    │  ├─ product_id, version, workspace_id   │
    │  └─ 3 records for 3 files               │
    │                                         │
    └───────┬────────────────────────────────┘
            │
    ┌───────▼─────────────────────────────────────┐
    │    AIRFLOW Pipeline Orchestration           │
    │                                             │
    │  1. Preprocessing Stage                     │
    │     └─> processed_chunks_File1.jsonl        │
    │         processed_chunks_File2.jsonl        │
    │         processed_chunks_File3.jsonl        │
    │                                             │
    │  2. Scoring Stage                           │
    │     └─> metrics.json (all files combined)   │
    │                                             │
    │  3. Validation Stage                        │
    │     └─> validation_summary.csv              │
    │                                             │
    │  4. Reporting Stage                         │
    │     └─> trust_report.pdf                    │
    │                                             │
    │  5. Indexing Stage                          │
    │     └─> OpenSearch vectors                  │
    │                                             │
    └───────┬─────────────────────────────────────┘
            │
    ┌───────▼────────────────────┐
    │    OpenSearch Vectors      │
    │                            │
    │  Collection: "prod_v1"     │
    │  Points: 5000+ vectors     │
    │  Dimensions: 1536          │
    │  Metadata per chunk:       │
    │  ├─ text (chunk content)   │
    │  ├─ source (filename)      │
    │  ├─ page_number            │
    │  ├─ chunk_index            │
    │  ├─ scores (quality)       │
    │  └─ timestamps             │
    │                            │
    └───────┬────────────────────┘
            │
        QUERY TIME
            │
            ├─> GET /api/v1/products/{id}/chunks?q=search_term
            │   ├─ Vector encode query
            │   ├─ Search OpenSearch
            │   ├─ Retrieve matching chunks
            │   └─ Return results with scores
            │
            └─> GET /api/v1/products/{id}/quality-improvement
                ├─ Analyze all chunks
                ├─ Calculate quality metrics
                ├─ Return drill-down details
                └─ Provide improvement recommendations
```

---

## Key Components

### 1. API Layer (`backend/src/primedata/api/`)
- **datasources.py** - Data source management (upload, sync, test)
- **products.py** - Product CRUD and configuration
- **pipeline.py** - Pipeline orchestration and monitoring
- **chunks.py** - Chunk retrieval and search
- **chunk_quality.py** - Quality metrics for chunks
- **data_quality.py** - Data quality rules management
- **artifacts.py** - Artifact listing and preview
- **analytics.py** - Workspace and product analytics
- **ai_readiness.py** - AI readiness assessment
- **quality_improvement.py** - Quality drill-down and recommendations
- **lineage.py** - Data lineage tracking
- **governance.py** - Governance policies and controls
- **audit.py** - Audit log management
- **acl.py** - Access control lists
- **auth.py** - Authentication endpoints
- **team.py** - Team/user management
- **billing.py** - Billing and subscription management

### 2. Database Layer (`backend/src/primedata/db/`)
- **models.py** - Core SQLAlchemy ORM models
  - User, Workspace, Product
  - DataSource, RawFile, PipelineRun
  - PipelineArtifact, DqViolation
  - ACL, UserAuditLog, EvalRun
- **models_enterprise.py** - Enterprise features
  - DataQualityRule, DataQualityRuleAudit
  - CustomPlaybook, Governance models

### 3. Pipeline Layer (`backend/src/primedata/ingestion_pipeline/`)
- **dag_tasks.py** - Airflow DAG task definitions
- **aird_stages/** - AIRD pipeline stages
  - preprocess.py - Normalization & chunking
  - scoring.py - Quality metrics calculation
  - validation.py - Data quality validation
  - fingerprint.py - Fingerprinting & AI readiness
  - reporting.py - Report generation
  - indexing.py - Vector indexing

### 4. Storage Layer (`backend/src/primedata/storage/`)
- **storage_client.py** - S3/GCS abstraction
- **paths.py** - Path construction helpers
- **vector_search.py** - OpenSearch/Vector DB operations

### 5. Services (`backend/src/primedata/services/`)
- **quality_improvement_calculator.py** - Quality metrics calculation
- **dq_evaluator.py** - Data quality rule evaluation
- **vector_metadata.py** - Vector metadata handling

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React, TypeScript, Tailwind CSS | User interface |
| **Backend** | FastAPI, Python 3.10+ | REST API server |
| **Database** | PostgreSQL 14+ | Relational data storage |
| **Vector DB** | OpenSearch / Elasticsearch | Vector embeddings & search |
| **Storage** | AWS S3 / Google Cloud Storage | File storage |
| **Orchestration** | Apache Airflow | Pipeline execution & scheduling |
| **LLM/Embeddings** | OpenAI / HuggingFace | Text embeddings & analysis |
| **ORM** | SQLAlchemy | Database abstraction |
| **Validation** | Pydantic | Request/response validation |
| **Auth** | JWT tokens | Authentication |
| **Monitoring** | Prometheus, Grafana | Metrics & observability |

---

## Summary

PrimeData is a comprehensive data quality and AI readiness platform that:

1. **Ingests** multi-file uploads with checksum validation
2. **Processes** documents through AIRD stages (normalize, chunk, score)
3. **Validates** against configurable DQ rules
4. **Indexes** chunks as vectors for semantic search
5. **Reports** trust scores and AI readiness metrics
6. **Governs** data through ACLs, audit logs, and lineage tracking
7. **Analyzes** quality metrics with drill-down capabilities
8. **Recommends** improvements based on AI insights

The workflow supports enterprise-grade requirements including:
- Multi-workspace/multi-tenant architecture
- Role-based access control (RBAC)
- Audit logging for compliance
- Data lineage for traceability
- Scalable batch processing
- API-first design

See **detailed_workflow.md** for in-depth technical walkthrough.
