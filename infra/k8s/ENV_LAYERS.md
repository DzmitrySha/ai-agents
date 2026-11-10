# Слои env: Secret vs ConfigMap vs Settings

Приоритет runtime:

```text
env (ConfigMap / Secret)  >  default в Settings
```

В поде `envFrom`: сначала ConfigMap, потом Secret → **одноимённые ключи Secret побеждают**.
Не дублировать ключ в ConfigMap и Secret.

## Локальный паритет

| Слой | Compose (`docker/`) | Кластер |
|------|---------------------|---------|
| settings | `.env` ← `.env.example` / `.env.lab.example` | ConfigMap `ai-agents-config` |
| credentials | `.env.secrets` ← `.env.secrets.example` | SOPS `ai-agents-secret.enc.yaml` |
| defaults | — | `backend/app/settings.py` |
| данные | `./storage` → `/data` | PVC `ai-agents-data` → `/data` |

## A. Secret (SOPS) — только credentials

`ai-agents-secret.enc.yaml` / [`ai-agents-secret.example.yaml`](ai-agents-secret.example.yaml):

| Ключ | Назначение |
|------|------------|
| `SERVICE_API_KEYS` | bootstrap Bearer-ключи для `/v1/*` (полный доступ) |
| `DEFAULT_LLM_API_KEY` | ключ внешнего OpenAI-compatible LLM (опционально) |
| `KEYCLOAK_CLIENT_SECRET` | confidential client OIDC |
| `SESSION_SECRET_KEY` | подпись BFF cookie (длинный random; не `dev-only-change-me` в prod) |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | трассировка (пусто = off) |
| `DATABASE_URL` | PostgreSQL async URL (пароль внутри) |

Опционально позже: `DIRECTORY_ADMIN_CLIENT_SECRET`, `GITHUB_TOKEN`, `SKILLS_SH_TOKEN` — тоже только Secret.

**Не в Secret:** `DEFAULT_LLM_BASE_URL`, `DEFAULT_LLM_MODEL`, `MAX_STEPS`, `RUN_TIMEOUT_SECONDS`, `STORAGE_PATH`, `LOG_DIR`, флаги, FQDN.

Чеклист перед `sops`: «это credential?» — если нет → ConfigMap или default.

Первый запуск enc (ops, не в CI):

```bash
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
cp infra/k8s/ai-agents-secret.example.yaml infra/k8s/ai-agents-secret.enc.yaml
# заполнить CHANGE_ME, затем:
sops -e -i infra/k8s/ai-agents-secret.enc.yaml
```

Не `kubectl create secret generic ai-agents-secret` в штатном потоке.  
CI SOPS не трогает — decrypt только KSOPS на Argo sync.  
Argo Application может жить в центральном GitOps-репо (в этом репозитории манифеста Application нет).

## B. ConfigMap — отличия окружения

`ai-agents-config` в `backend.yaml`: `APP_NAME`, `ENVIRONMENT=production`, `BACKEND_PORT`,
`PUBLIC_URL` / IdP, `DEFAULT_LLM_*`, caps, `SUPERADMIN_EMAILS`, `USER_DAILY_RUN_LIMIT`,
`STORAGE_PATH=/data`, `LOG_DIR=/data/logs`, `KEYCLOAK_SSL_VERIFY` (temporary false — см. NUANCES).

Отклонения от шаблона (нет `APP_PROFILE`/`DB_CREATE_SCHEMA_ON_STARTUP`, Application вне репо) — [`docs/NUANCES.md`](../../docs/NUANCES.md) § «Деплой: отклонения от канона».

## C. Settings — дефолты в коде

`backend/app/settings.py` — portable defaults. Вне `dev`/`lab`/`test` слабый
`SESSION_SECRET_KEY` валит старт.

## D. PVC

`pvc.yaml` → `ai-agents-data` (local-path, RWO, 10Gi). Backend mount `/data`.  
Из‑за RWO: `replicas: 1`, `strategy: Recreate`. Live SSE / RunManager — **single-replica**
(in-process); горизонтальный scale без Redis fan-out не поддержан.
