# NUANCES — заметки по деплою ai-agents

Краткий список для ops и агентов.

## Архитектура

| Тема | Как у нас |
|------|-----------|
| SPA | `frontend/` (stock Mantine + тема portracker). Traefik/HTTPRoute → `ai-agents-frontend`; nginx проксирует `/api`, `/v1`, `/auth`, `/health`, `/mcp` в backend. |
| Postgres | На **хосте** (не в Compose). DDL только `alembic upgrade head` (migrate oneshot / initContainer). |
| Auth | Люди — Keycloak OIDC BFF; машины — `SERVICE_API_KEYS` + DB-ключи со скоупами. |
| Runs | Persist в PG; live SSE и cancel — **in-process** (`RunManager` / `LiveHub`). `replicas: 1`. Horizontal scale без Redis fan-out не поддерживается. |
| GPU | Нет inference GPU в app-подах; LLM — внешний OpenAI-compatible endpoint. |

## FQDN

| Контур | Host |
|--------|------|
| Lab/work | `ai-agents-dev.example.com` |
| Prod | `ai-agents.example.com` |

Не копировать `-dev` в k8s манифесты.

## Secrets / SOPS

- Enc-файл `infra/k8s/ai-agents-secret.enc.yaml` создаёт ops: `cp …example… enc` → fill → `sops -e -i`.
- В git без реальных секретов enc может отсутствовать — KSOPS sync не поднимется, пока enc не закоммичен.
- `SESSION_SECRET_KEY`: вне lab/dev слабый/`dev-only-change-me` → fail startup.
- Custom tools / MCP connections: headers в БД есть, в API наружу — только `header_names`.

## Деплой: отклонения от канона

| Тема | Как у нас | Почему |
|------|-----------|--------|
| `APP_PROFILE` | не используется: профиль IdP задают явные `KEYCLOAK_ISSUER` / `KEYCLOAK_PUBLIC_URL` / `KEYCLOAK_SSL_VERIFY` (Compose `.env`, k8s ConfigMap) | один код на все контуры, без скрытых дефолтов по профилю |
| `DB_CREATE_SCHEMA_ON_STARTUP` | флага нет: в коде нет `create_all`/DDL, схема — только Alembic (migrate oneshot / initContainer) | нечего выключать |
| Argo Application | `infra/bootstrap/` в репо нет, Application живёт в центральном GitOps-репо | см. `infra/k8s/ENV_LAYERS.md` |
| SOPS enc | `ai-agents-secret.enc.yaml` создаёт ops (age-ключ не в CI) | KSOPS decrypt только на Argo sync |
| k8s ConfigMap | без `FRONTEND_URL`/`CORS_ORIGINS_EXTRA`: SPA и API на одном origin (nginx прокси) | CORS не нужен |
| k8s `LANGFUSE_HOST` | сервис Langfuse в ns `ai-agents` (не часть app-манифестов) | опциональная трассировка |
| nginx upstream | env `BACKEND_UPSTREAM`: Compose — `ai-agents-backend:8080`, k8s — `ai-agents-backend.ai-agents.svc.cluster.local:8080` | nginx `resolver` не использует search-домены из `resolv.conf`: короткое имя в k8s не резолвится |

## Security debt

- `KEYCLOAK_SSL_VERIFY=false` в prod ConfigMap — temporary, пока CA mount/httpx не стабилен. Цель: `true` + `KEYCLOAK_CA_BUNDLE`.
- Outbound HTTP: SSRF-guard (private/metadata); redirects у custom tools отключены. Для MCP
  приватные цели разрешаются только через `MCP_EGRESS_ALLOWED_HOSTS` (host/`*.suffix`/CIDR).

## UI

- Темы: light / dark / portracker (осознанное отклонение от «только stock»).
- Assist: видит зарегистрированную форму (`useAssistForm`) + каталог сервиса, не весь DOM.
- Service keys UI — без AI-autofill (секреты).

## CI

- Root: pytest (backend) + `tsc --noEmit` + build (frontend); любой git tag → `decide-images` → build/retag ×2 → `bump` (один `newTag`).
- Override выбора образов: `BUILD_IMAGES=all|backend,frontend`.
- Offline jobs — только `gitlab-ci/offline/*`, не `include` в root.
