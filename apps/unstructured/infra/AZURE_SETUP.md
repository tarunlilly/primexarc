# 🚀 Azure OpenAI Integration Setup Guide for PrimeData Airflow

## Overview

This guide walks through configuring Azure OpenAI embeddings for the PrimeData Airflow pipeline. The setup supports:

- ✅ Azure OpenAI embeddings (primary)
- ✅ FastEmbed fallback (local CPU-based)
- ✅ Production-grade error handling
- ✅ Performance monitoring
- ✅ Comprehensive logging

---

## Prerequisites

### Azure Requirements
- Azure OpenAI service deployment
- Embedding model deployed (e.g., text-embedding-3-large)
- API key and endpoint URL
- Appropriate IAM permissions

### Local Requirements
- Docker & Docker Compose
- 8GB+ RAM (for comfortable development)
- PostgreSQL, OpenSearch, MinIO running

---

## Configuration Steps

### Step 1: Create Azure OpenAI Deployment

#### 1a. Create Azure Account Resources
```bash
# Set variables
RESOURCE_GROUP="primedata-rg"
LOCATION="eastus"
OPENAI_NAME="primedata-openai"

# Create resource group
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

# Create Azure OpenAI service
az cognitiveservices account create \
  --name $OPENAI_NAME \
  --resource-group $RESOURCE_GROUP \
  --kind OpenAI \
  --sku s0 \
  --location $LOCATION
```

#### 1b. Deploy Embedding Model
```bash
# Deploy text-embedding-3-large
az cognitiveservices account deployment create \
  --resource-group $RESOURCE_GROUP \
  --name $OPENAI_NAME \
  --deployment-name text-embedding-3-large \
  --model name=text-embedding-3-large \
  --model-version "1" \
  --model-format OpenAI \
  --capacity 1
```

#### 1c. Get API Key and Endpoint
```bash
# Get API key
AZURE_OPENAI_API_KEY=$(az cognitiveservices account keys list \
  --resource-group $RESOURCE_GROUP \
  --name $OPENAI_NAME \
  --query "key1" -o tsv)

# Get endpoint
AZURE_OPENAI_ENDPOINT=$(az cognitiveservices account show \
  --resource-group $RESOURCE_GROUP \
  --name $OPENAI_NAME \
  --query "properties.endpoint" -o tsv)

echo "API Key: $AZURE_OPENAI_API_KEY"
echo "Endpoint: $AZURE_OPENAI_ENDPOINT"
```

---

### Step 2: Configure Environment Variables

#### 2a. Create `.env.local` file

Create `infra/.env.local`:

```bash
# ============================================
# Azure OpenAI Configuration
# ============================================
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_OPENAI_EMBEDDING_DIMENSIONS=3072

# ============================================
# Azure Storage (Optional)
# ============================================
AZURE_STORAGE_ACCOUNT_NAME=your-account-name
AZURE_STORAGE_ACCOUNT_KEY=your-account-key
AZURE_CONTAINER_NAME=primedata

# ============================================
# Core Infrastructure
# ============================================
POSTGRES_USER=aird
POSTGRES_PASSWORD=aird
POSTGRES_PORT=5432
POSTGRES_DB=aird
PRIMEDATA_APP_DB=primedata_backend

# ============================================
# OpenSearch
# ============================================
OPENSEARCH_URL=http://opensearch:9200
OPENSEARCH_USERNAME=admin
OPENSEARCH_ADMIN_PASSWORD=Admin@123

# ============================================
# MinIO
# ============================================
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_HOST_PORT=9002
MINIO_CONSOLE_HOST_PORT=9003

# ============================================
# Airflow
# ============================================
AIRFLOW_SECRET_KEY=your-secret-key-$(openssl rand -hex 16)
AIRFLOW_ADMIN_USER=admin
AIRFLOW_ADMIN_PASSWORD=admin123
AIRFLOW_WEBSERVER_PORT=8080
```

#### 2b. Verify Environment Variables
```bash
# Check if .env.local exists and has values
cat infra/.env.local | grep AZURE_OPENAI
```

---

### Step 3: Start Infrastructure

#### 3a. Build Docker Images
```bash
cd infra
docker-compose build
```

#### 3b. Start Services
```bash
# Start in background
docker-compose up -d

# Wait for services to initialize
sleep 30

# Check status
docker-compose ps
```

#### 3c. Verify Services
```bash
# Run health checks
bash scripts/health-checks/final-check.sh

# Expected output: All checks passing with OpenSearch (not Qdrant)
```

---

### Step 4: Test Azure Embeddings

#### 4a. Access Airflow UI
```
http://localhost:8080
Login: admin / admin123
```

#### 4b. Manually Test Embedding
```python
# In Airflow webserver shell or local Python
from infra.airflow.utils.azure_embeddings import AzureEmbeddingsClient

client = AzureEmbeddingsClient()
print(f"Status: {client.get_status()}")

# Test single text
embedding = client.embed_text("Hello, world!")
print(f"Embedding length: {len(embedding) if embedding else 'None'}")

# Test multiple texts
embeddings = client.embed_texts([
    "Text 1",
    "Text 2",
    "Text 3"
])
print(f"Embeddings count: {len(embeddings) if embeddings else 'None'}")
```

#### 4c. Check Logs
```bash
# View Airflow container logs
docker-compose logs -f airflow-webserver

# Look for Azure initialization messages:
# "✓ Azure OpenAI client initialized: text-embedding-3-large"
```

---

### Step 5: Create DAG with Azure Embeddings

#### 5a. Example DAG Using Azure Embeddings

Create `infra/airflow/dags/dag_test_azure_embeddings.py`:

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from infra.airflow.utils.azure_embeddings import embed_texts
from infra.airflow.utils.monitoring import track_task_execution

def task_embed_documents():
    """Example task using Azure embeddings."""
    documents = [
        "PrimeData transforms raw data into AI-ready insights",
        "Azure OpenAI provides powerful embedding models",
        "Airflow orchestrates complex data pipelines"
    ]

    embeddings = embed_texts(documents)
    if embeddings:
        return {
            "documents_count": len(documents),
            "embedding_dimensions": len(embeddings[0]),
            "success": True
        }
    return {"success": False}

dag = DAG(
    'test_azure_embeddings',
    default_args={'owner': 'primedata'},
    schedule_interval=None,
    start_date=days_ago(1),
    tags=['azure', 'embeddings', 'test'],
)

embed_task = PythonOperator(
    task_id='embed_documents',
    python_callable=task_embed_documents,
    dag=dag,
)
```

#### 5b. Deploy DAG
```bash
# Copy DAG to dags folder
cp infra/airflow/dags/dag_test_azure_embeddings.py \
   infra/airflow/dags/

# Airflow auto-detects DAG in 1-2 minutes
# Or manually trigger:
docker-compose exec airflow-webserver airflow dags list
```

---

## Configuration Reference

### Environment Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `AZURE_OPENAI_API_KEY` | Azure API key | `sk-...` | ✅ Yes |
| `AZURE_OPENAI_ENDPOINT` | Azure endpoint URL | `https://xxx.openai.azure.com/` | ✅ Yes |
| `AZURE_OPENAI_API_VERSION` | OpenAI API version | `2024-02-15-preview` | ❌ No |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | LLM deployment name | `gpt-4` | ❌ No |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding model deployment | `text-embedding-3-large` | ❌ No |
| `AZURE_OPENAI_EMBEDDING_DIMENSIONS` | Output embedding dimensions | `3072` | ❌ No |
| `AZURE_STORAGE_ACCOUNT_NAME` | Azure storage account | `myaccount` | ❌ Optional |
| `AZURE_STORAGE_ACCOUNT_KEY` | Azure storage key | `...` | ❌ Optional |

### Python Client Usage

```python
from infra.airflow.utils.azure_embeddings import AzureEmbeddingsClient

# Initialize client (auto-detects environment vars)
client = AzureEmbeddingsClient()

# Check status
status = client.get_status()
print(f"Azure available: {status['azure_available']}")
print(f"Fallback available: {status['fallback_available']}")

# Embed single text
embedding = client.embed_text("Your text here")
print(f"Embedding shape: {len(embedding)}")  # 3072 or 1536

# Embed multiple texts
embeddings = client.embed_texts([
    "Text 1",
    "Text 2"
])
print(f"Embeddings count: {len(embeddings)}")

# Use fallback (if Azure unavailable)
embedding = client.embed_text("Text", use_azure=False)
```

---

## Error Handling

### Azure Errors Handled

| Error | Handling |
|-------|----------|
| Invalid credentials | Logs warning, falls back to FastEmbed |
| Rate limit (429) | Automatic retry with exponential backoff |
| Timeout (408) | Automatic retry with exponential backoff |
| Server error (5xx) | Automatic retry with exponential backoff |
| Invalid deployment | Non-retryable, raises exception |

### Testing Error Scenarios

```python
# Test fallback by disabling Azure
import os
os.environ["AZURE_OPENAI_API_KEY"] = ""

from infra.airflow.utils.azure_embeddings import embed_text
embedding = embed_text("This will use FastEmbed fallback")
```

---

## Monitoring and Debugging

### Check Azure Connection
```bash
# Test Azure endpoint connectivity
curl -H "api-key: $AZURE_OPENAI_API_KEY" \
  "$AZURE_OPENAI_ENDPOINT/openai/deployments/$AZURE_OPENAI_EMBEDDING_DEPLOYMENT/embeddings?api-version=2024-02-15-preview" \
  -d '{"input": ["test"]}'
```

### View Logs
```bash
# All containers
docker-compose logs -f

# Specific container
docker-compose logs -f airflow-scheduler

# Search for Azure messages
docker-compose logs airflow-webserver | grep -i azure
```

### Performance Metrics
```python
from infra.airflow.utils.monitoring import get_metrics_collector

collector = get_metrics_collector()
summary = collector.get_summary()
print(f"Success rate: {summary['success_rate']:.1f}%")
print(f"Error rate: {summary['error_rate']:.1f}%")
```

---

## Troubleshooting

### Issue: "Azure credentials not configured"
**Solution:**
```bash
# Verify env vars are set
docker-compose exec airflow-webserver env | grep AZURE_OPENAI

# Check .env.local exists
ls -la infra/.env.local

# Ensure docker-compose uses .env.local
grep "env_file" infra/docker-compose.yml
```

### Issue: "Azure OpenAI client initialization failed"
**Solution:**
```bash
# Check Azure service is deployed
az cognitiveservices account show \
  --resource-group $RESOURCE_GROUP \
  --name $OPENAI_NAME

# Verify API key is valid
curl -H "api-key: $AZURE_OPENAI_API_KEY" \
  "$AZURE_OPENAI_ENDPOINT/openai/models?api-version=2024-02-15-preview"
```

### Issue: "Connection timeout to Azure endpoint"
**Solution:**
- Check network connectivity to Azure
- Verify endpoint URL is correct (including trailing slash)
- Check firewall rules allow outbound HTTPS
- Try manually calling endpoint: `curl $AZURE_OPENAI_ENDPOINT`

### Issue: Fallback to FastEmbed but slow
**Solution:**
- FastEmbed uses CPU only, slower on weak hardware
- Consider using Azure embeddings for production
- Or run FastEmbed on GPU: Install `onnxruntime[gpu]`

---

## Next Steps

1. ✅ Configure Azure OpenAI credentials
2. ✅ Start infrastructure
3. ✅ Test embeddings
4. ✅ Deploy production DAGs
5. ✅ Monitor performance
6. ✅ Set up alerting

See `AZURE_DAG_EXAMPLES.md` for production DAG templates.

---

## Support

For issues or questions:
1. Check logs: `docker-compose logs airflow-webserver`
2. Review status: `azure.get_status()`
3. Consult [Azure OpenAI docs](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
4. Check [Airflow docs](https://airflow.apache.org/)
