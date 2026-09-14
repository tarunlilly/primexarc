# PrimeData Backend Documentation

Complete technical documentation for the PrimeData backend application covering architecture, workflows, APIs, and database operations.

## Documentation Files

### 1. **workflow.md** - Complete Workflow Overview
**Purpose**: High-level overview of the entire PrimeData system

**Contents**:
- System architecture diagram
- User journey through the application
- Core workflows (file upload → vector search, quality control, analytics)
- Data flow diagrams
- Key components breakdown
- Technology stack

**When to read**: Start here for a comprehensive understanding of how PrimeData works end-to-end.

**Use cases**:
- Onboarding new team members
- Understanding system architecture
- Planning new features
- Integration planning

---

### 2. **detailed_workflow.md** - In-Depth Technical Walkthrough
**Purpose**: Detailed technical guide for developers

**Contents**:
- Layered architecture explanation
- Request flow examples (upload, search)
- Database schema & model relationships
- API endpoints categorized by feature
- Airflow DAG pipeline orchestration
- Data persistence strategy
- Error handling & recovery mechanisms
- Performance optimization tips

**When to read**: When you need detailed technical understanding of specific components.

**Use cases**:
- API development
- Database optimization
- Pipeline troubleshooting
- Performance tuning
- Error debugging

**Key sections**:
- Request Flow & Processing: Step-by-step example of file upload and search
- Database Schema: Complete model definitions with relationships
- Pipeline Orchestration: Airflow DAG structure and execution flow
- Performance Optimization: Indexing, caching, and query optimization

---

### 3. **sql_queries.sql** - SQL Operations Reference
**Purpose**: SQL equivalent of all SQLAlchemy ORM operations

**Contents**:
- Table creation (DDL) for all 15+ models
- Common SELECT queries
- INSERT queries with examples
- UPDATE queries for state changes
- DELETE queries (with cascade info)
- Aggregation queries
- Analytical queries
- Performance tuning queries
- Maintenance queries
- Backup & recovery queries

**When to use**: For database debugging, optimization, or when working with raw SQL.

**Use cases**:
- Direct database queries for debugging
- Performance analysis and optimization
- Data exports and backups
- Database maintenance
- Understanding ORM to SQL mapping

**Key sections**:
- **Table Creation**: DDL with constraints and indexes
- **Common Queries**: CRUD operations organized by table
- **Analytics**: Workspace usage, product quality, timeline analysis
- **Maintenance**: VACUUM, ANALYZE, index management
- **Troubleshooting**: Finding slow queries, unused indexes

---

### 4. **api_spec.json** - OpenAPI 3.0 Specification
**Purpose**: Complete API specification for all endpoints

**Contents**:
- OpenAPI 3.0.0 format specification
- 50+ API endpoints documented
- Request/response schemas
- Authentication scheme (JWT Bearer)
- Error responses
- Parameter definitions

**When to use**: For API integration, client generation, or endpoint reference.

**Use cases**:
- Building API clients
- Generating SDK code
- API integration testing
- Swagger UI documentation
- REST client configuration

**Endpoint categories**:
- Authentication & Users
- Workspaces & Team Management
- Products & Configuration
- Data Sources & Upload
- Pipeline & Orchestration
- Chunks & Search
- Data Quality & Compliance
- AI Readiness
- Analytics & Insights
- Governance & Audit
- Billing
- Health & System

**Example usage**:
```bash
# Import into Swagger/Postman
curl -X GET "http://localhost:8000/docs"

# Generate client code
openapi-generator-cli generate -i api_spec.json -g python-client

# Validate against spec
swagger-cli validate api_spec.json
```

---

## Quick Navigation

### By Role

**Product Managers**
1. Start with `workflow.md` - System Architecture section
2. Read workflow examples for each feature
3. Check `detailed_workflow.md` - User Journey section

**Frontend Developers**
1. Review `api_spec.json` for endpoint documentation
2. Check `workflow.md` - Data Flow section
3. Reference `detailed_workflow.md` - Request Flow examples

**Backend Developers**
1. Read `detailed_workflow.md` - complete guide
2. Reference `sql_queries.sql` for database operations
3. Use `api_spec.json` for endpoint contract

**DevOps/Database Admins**
1. Review `detailed_workflow.md` - Data Persistence section
2. Use `sql_queries.sql` - Performance & Maintenance sections
3. Check `workflow.md` - Technology Stack

**QA/Testers**
1. Review `workflow.md` - Core Workflows section
2. Check `api_spec.json` for endpoint testing
3. Reference error scenarios in `detailed_workflow.md`

### By Task

**Onboarding to the project**
→ `workflow.md` (complete overview)

**Implementing a new API endpoint**
→ `api_spec.json` (schema), `detailed_workflow.md` (request flow)

**Debugging a database issue**
→ `sql_queries.sql` (troubleshooting section), `detailed_workflow.md` (data persistence)

**Optimizing pipeline performance**
→ `detailed_workflow.md` (pipeline orchestration), `sql_queries.sql` (performance tuning)

**Understanding data flow**
→ `workflow.md` (data flow diagram), `detailed_workflow.md` (complete flow)

**Testing APIs**
→ `api_spec.json` (all endpoints), `workflow.md` (example workflows)

**Integrating with PrimeData**
→ `api_spec.json` (complete spec), `workflow.md` (architecture)

---

## Key Concepts

### Data Models

**Core Models** (15+ total):
- User, Workspace, WorkspaceMember
- Product, DataSource, RawFile
- PipelineRun, PipelineArtifact
- DqViolation, ACL, UserAuditLog
- BillingProfile, CustomPlaybook
- DataQualityRule (Enterprise)

See `detailed_workflow.md` Database Schema section for full details.

### API Structure

**Base URL**: `/api/v1/`

**Authentication**: JWT Bearer token

**Categories**:
- Authentication & Users
- Workspaces
- Products
- Data Sources & Upload
- Pipeline Orchestration
- Chunks & Search
- Data Quality
- AI Readiness
- Analytics
- Governance
- Audit

See `api_spec.json` for complete specification.

### Pipeline Stages

1. **Initialization** - Create pipeline run, validate inputs
2. **Ingestion** - Fetch raw files from database/storage
3. **Preprocessing** - Normalize, chunk, section documents
4. **Scoring** - Calculate quality metrics for chunks
5. **Validation** - Apply DQ rules, detect violations
6. **Analysis** - Generate fingerprint, trust score, reports
7. **Indexing** - Embed chunks, create vector collection
8. **Finalization** - Update product state, send notifications

See `detailed_workflow.md` Pipeline Orchestration section.

---

## Architecture Overview

```
┌─────────────────────────┐
│  FastAPI Application    │
│  (REST API Layer)       │
└────────────┬────────────┘
             │
    ┌────────┼────────┐
    │        │        │
┌───▼──┐ ┌──▼────┐ ┌─▼──────┐
│PostgreSQL│ OpenSearch │ S3/GCS  │
│(Relational) │ (Vectors)  │ (Files)  │
└──────┘ └───────┘ └─────────┘
    │        │        │
    └────────┼────────┘
             │
   ┌─────────▼─────────┐
   │ Airflow Pipeline  │
   │ (Orchestration)   │
   └───────────────────┘
```

---

## Common Workflows

### Workflow 1: Upload & Process
```
1. User uploads files via POST /datasources/{id}/upload-files
2. Files stored in S3, RawFile records created in DB
3. User triggers pipeline via POST /pipeline/run
4. Pipeline processes through 7 stages
5. Results available via GET /pipeline/artifacts
```

### Workflow 2: Search & Analyze
```
1. Pipeline completes indexing
2. User searches chunks via GET /products/{id}/chunks?q=...
3. Results returned from OpenSearch with quality scores
4. Quality metrics available via GET /products/{id}/quality-improvement
```

### Workflow 3: Quality Control
```
1. System initializes DQ rules via POST /products/{id}/rules/seed
2. Validation stage applies rules during pipeline
3. Violations detected and stored
4. User reviews violations via GET /products/{id}/violations
```

---

## Database Relationships

```
users
  ├─→ workspace_members → workspaces
  ├─→ products (owner)
  ├─→ acls
  └─→ audit_logs

workspaces
  ├─→ workspace_members
  ├─→ products
  ├─→ billing_profiles
  └─→ data_quality_rules

products
  ├─→ data_sources
  ├─→ raw_files
  ├─→ pipeline_runs
  └─→ dq_violations

pipeline_runs
  └─→ pipeline_artifacts
```

---

## Performance Considerations

### Database
- Indexes on: email, workspace_id, product_id, status
- Query pagination: limit 100, offset-based
- Batch operations: 1000 records at once
- Connection pooling: max 20 connections

### Storage
- S3 hierarchical structure: `ws/{ws_id}/prod/{prod_id}/v{version}/`
- File compression: JSONL gzip, JSONB compressed
- Presigned URLs: 1-hour expiry

### Vector Search
- Collection naming: `{ws_id}_{prod_id}_v{version}`
- Indexing: batch insert with 1000 vector chunks
- Search: vector similarity with top-K retrieval

---

## Troubleshooting

### Issue: Slow queries
**Solution**: Check `sql_queries.sql` - Performance Tuning section
- Run `ANALYZE` to update statistics
- Check for missing indexes on foreign keys
- Verify query plans with `EXPLAIN`

### Issue: Pipeline failures
**Solution**: Check `detailed_workflow.md` - Error Handling section
- Review error message in PipelineRun record
- Check RawFile status and storage paths
- Verify DQ rules configuration

### Issue: Empty search results
**Solution**: Check data flow in `workflow.md` - Data Flow section
- Verify indexing stage completed
- Check OpenSearch collection exists
- Verify embedding configuration

---

## Additional Resources

**Code Examples**: See specific sections in `detailed_workflow.md`

**API Testing**: Use `api_spec.json` with Postman, Swagger UI, or curl

**Database Debugging**: Run queries from `sql_queries.sql` against PostgreSQL

**Pipeline Debugging**: Review Airflow logs and task outputs

---

## Document Versions

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-03-31 | Initial release with complete workflows, schemas, and APIs |

---

## Getting Help

**For architectural questions**: Review `workflow.md` and `detailed_workflow.md`

**For API questions**: Check `api_spec.json` and request/response examples

**For database questions**: Use `sql_queries.sql` and schema definitions

**For pipeline issues**: Review Airflow DAG structure and error handling

---

**Last Updated**: 2024-03-31

**Maintained By**: PrimeData Backend Team

**Contributing**: Submit documentation updates via pull request with examples and rationale.
