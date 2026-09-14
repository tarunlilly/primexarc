# CATS Deployment Reference

> NEVER run `git` commands against the K8s manifest repo. Read and edit YAML files, then present changes to the user for manual merge. See hard rule in `CLAUDE.md`.

## K8s manifest repo path

```
/Users/L027310/Library/CloudStorage/OneDrive-EliLillyandCompany/Documents/github/LRL_light_k8s_infra_apps/projects/dev/ibu-ai-ready-data-dev/
```

This is the CATS-managed GitOps repo. ArgoCD watches it and applies changes to the `ibu-ai-ready-data-dev` namespace automatically when commits land.

## Files and their purpose

| File | What it controls |
|---|---|
| `deploy.yaml` | Main app Deployment — image tag, container env vars from secrets, resource limits/requests, liveness/readiness probes |
| `secret.yaml` | ExternalSecret syncing Azure AD credentials (`CLIENT_ID`, `TENANT_ID`) from AWS Secrets Manager |
| `pgadmin.yaml` | ExternalSecret for pgAdmin login + pgAdmin Deployment, Service, and Ingress |
| `aws-cli-deployment.yaml` | Long-running aws-cli pod with CSST service account — used to manage AWS Secrets Manager via CLI (see section below) |
| `rds-postgres.yaml` | Crossplane `RDSInstance` — provisions the Postgres RDS; writes connection secret automatically. **Do not edit without deep Crossplane knowledge — wrong changes can trigger destructive DB operations.** |
| `ingress.yaml` | Main app Ingress — host `ibu-ard.bu.lilly.com`, routes to ClusterIP service on port 80 |
| `namespace.yaml` | Namespace `ibu-ai-ready-data-dev` with Argo RBAC (read/admin AD group refs) |
| `service.yaml` | ClusterIP Service — port 80 → pod 8000 |

## Image tagging and Flux automation

ECR registry: `283234040926.dkr.ecr.us-east-2.amazonaws.com/ibu-ai-ready-data`

The Flux image automation annotation on `deploy.yaml:8`:
```
app.lilly.com/flux.simple.ibu-ai-ready-data-policy: "283234040926;ibu-ai-ready-data;glob:*.*.*"
```
This tells Flux to watch ECR for tags matching `*.*.*` (3-segment semver like `0.4.3`) and automatically commit a change to `deploy.yaml`'s `image:` line when a newer matching tag is found.

CI (`ci.yml`) tags released images with:
- `type=sha` (every push to main — dev traceability)
- `type=semver,pattern={{version}}` (only when a `v*.*.*` git tag is pushed — e.g. `v0.4.4` → ECR tag `0.4.4`)

No mutable `major.minor` tags are pushed. Every version in ECR is unique and traceable.

**Typical release flow:**
1. Merge changes to `main` in the project repo.
2. Create and push a git tag: `git tag v0.4.4 && git push origin v0.4.4`
3. CI builds and pushes `0.4.4` to ECR.
4. Flux detects `0.4.4` matches `glob:*.*.*` and auto-updates `deploy.yaml:35`.
5. ArgoCD picks up the manifest change and rolls out the new pod.

## ExternalSecrets pattern

All cluster secrets are delivered via AWS Secrets Manager + the External Secrets operator. Never hand-roll `Secret` resources.

**ExternalSecret YAML template:**
```yaml
apiVersion: kubernetes-client.io/v1
kind: ExternalSecret
metadata:
  name: <k8s-secret-name>
  namespace: ibu-ai-ready-data-dev
spec:
  backendType: secretsManager
  data:
    - key: ibu-arc-dev/ibu-ai-ready-data/<path>
      name: <k8s-key-name>
      property: <aws-secret-key>
```

**Referencing in a Deployment:**
```yaml
env:
  - name: MY_ENV_VAR
    valueFrom:
      secretKeyRef:
        name: <k8s-secret-name>
        key: <k8s-key-name>
```

**Existing K8s secrets and their AWS source:**

| K8s Secret name | AWS Secrets Manager path | Keys |
|---|---|---|
| `ibu-ai-ready-data-postgres-secrets` | Managed by Crossplane (auto) | endpoint, port, username, password |
| `pgadmin-secret` | `ibu-arc-dev/ibu-ai-ready-data/pgadmin` | pgadmin-email, pgadmin-password |
| `ibu-ai-ready-data-azure-ad` | `ibu-arc-dev/ibu-ai-ready-data/azure-ad` | client-id, tenant-id |

## How to add a new secret to the cluster (CSST CLI method)

Use the `aws-cli` pod (in `aws-cli-deployment.yaml`) instead of the AWS console — no direct AWS account access needed.

**1 — Exec into the aws-cli pod:**
ArgoCD UI → namespace `ibu-ai-ready-data-dev` → `aws-cli` deployment → pod → Terminal tab.

**2 — Discover / verify existing secrets:**
```sh
aws secretsmanager list-secrets --filters Key=name,Values=ibu-arc-dev/ibu-ai-ready-data
```

**3 — Create a new secret:**
```sh
aws secretsmanager create-secret \
  --name ibu-arc-dev/ibu-ai-ready-data/<purpose> \
  --secret-string '{"<key1>":"<value1>","<key2>":"<value2>"}'
```

Example for Azure AD credentials:
```sh
aws secretsmanager create-secret \
  --name ibu-arc-dev/ibu-ai-ready-data/azure-ad \
  --secret-string '{"client-id":"<CLIENT_ID>","tenant-id":"<TENANT_ID>"}'
```

**4 — Update an existing secret:**
```sh
aws secretsmanager update-secret \
  --secret-id ibu-arc-dev/ibu-ai-ready-data/<purpose> \
  --secret-string '{"<key1>":"<new-value>"}'
```

**5 — Verify:**
```sh
aws secretsmanager get-secret-value \
  --secret-id ibu-arc-dev/ibu-ai-ready-data/<purpose>
```

**6 — Clear shell history after handling real values:**
```sh
history -c
```

**7 — Wire it up:** create/update the ExternalSecret YAML (template above) and add `secretKeyRef` env entries to `deploy.yaml`. Propose the diff; user commits and pushes in the K8s repo.

**Note on image pull:** `aws-cli-deployment.yaml` uses `amazon/aws-cli:latest` (DockerHub). If the cluster blocks DockerHub, change to `elilillyco-lilly-docker.jfrog.io/amazon/aws-cli:latest`.

## CATS documentation (auth-walled — paste content here or in the agent prompt)

All URLs below require Lilly SSO. WebFetch cannot access them; the user must paste content if needed.

- **Home**: https://cats.lilly.com/guide
- **External Secrets**: https://cats.lilly.com/guide/ExternalSecrets
- **Cluster Self-Service Toolkit**: https://cats.lilly.com/guide/ClusterSelfServiceToolkit
- **Argo**: https://cats.lilly.com/guide/Argo

## Hard rules

- **Never run `git` in the K8s manifest repo.** Propose YAML diffs; user commits.
- Never paste secret values into YAML.
- Never edit `rds-postgres.yaml` casually — Crossplane RDS changes can be destructive.
- Local development (`app/.env` in the project repo) is separate from cluster secrets; they coexist cleanly via Pydantic's `process env > .env file` precedence.
