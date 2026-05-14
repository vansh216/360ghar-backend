# Memory Usage Reduction Plan: 500MB → 100MB

**Date:** 2026-05-14
**Status:** Approved for implementation
**Target:** Reduce idle RSS from ~300-400MB to ~100-120MB, peak from ~500-700MB to ~200-250MB

---

## Table of Contents

1. [Current Memory Budget](#1-current-memory-budget)
2. [Target Memory Budget](#2-target-memory-budget)
3. [Phase 1: Docker & Container Optimization](#phase-1-docker--container-optimization)
4. [Phase 2: File-Based Disk Cache](#phase-2-file-based-disk-cache)
5. [Phase 3: Database Connection Pools](#phase-3-database-connection-pools)
6. [Phase 4: SSE Event Bus](#phase-4-sse-event-bus)
7. [Phase 5: Image Processing](#phase-5-image-processing)
8. [Phase 6: Notification Thread Pool](#phase-6-notification-thread-pool)
9. [Phase 7: Lazy-Load Heavy Imports](#phase-7-lazy-load-heavy-imports)
10. [Phase 8: Dependency Cleanup](#phase-8-dependency-cleanup)
11. [Phase 9: Query-Level Fixes](#phase-9-query-level-fixes)
12. [Phase 10: Shared HTTP Clients](#phase-10-shared-http-clients)
13. [Files to Create](#files-to-create)
14. [Files to Modify](#files-to-modify)
15. [Implementation Order](#implementation-order)
16. [Validation](#validation)

---

## 1. Current Memory Budget

Measured via agent-based analysis of the full codebase.

| Component | Idle RSS | Peak RSS | File(s) |
|-----------|----------|----------|---------|
| Python runtime + libs | ~100 MB | ~100 MB | — |
| DB connection pools (14 max) | ~50-70 MB | ~70-140 MB | `app/core/config.py:107-113` |
| In-memory cache (1000 entries) | ~10-30 MB | ~30-50 MB | `app/core/cache/backends/memory.py` |
| SSE event bus (unbounded) | ~0 MB | ~0-128 MB | `app/core/sse.py` |
| Notification thread pool (8) | ~64 MB | ~64 MB | `app/services/notifications/helpers.py:21-24` |
| MCP servers (eager load) | ~20-30 MB | ~20-30 MB | `app/factory.py:27`, `app/infrastructure/mcp.py` |
| Pillow (eager import) | ~5-10 MB | ~5-10 MB | `app/services/image_processing.py:8-9` |
| pydantic-ai (scheduler load) | ~8-12 MB | ~8-12 MB | `app/services/blog_auto_publish.py:12-15` |
| Image upload (per-request spike) | — | ~300-400 MB | `app/services/image_processing.py:386,402` |
| HTTP clients (per-request) | — | ~20 MB | 13 locations |
| **TOTAL** | **~300-400 MB** | **~500-700 MB** | |

---

## 2. Target Memory Budget

| Component | Idle RSS | Peak RSS | Savings |
|-----------|----------|----------|---------|
| Python runtime + libs (lazy imports) | ~40 MB | ~40 MB | -60 MB |
| DB pools (6 max) | ~30 MB | ~30-60 MB | -40-80 MB |
| Cache (disk-based) | ~2 MB | ~2 MB | -28-48 MB |
| SSE queues (capped, maxsize=32) | ~0 MB | ~0-16 MB | -112 MB |
| Thread pool (3) | ~24 MB | ~24 MB | -40 MB |
| MCP (lazy) | ~0 MB | ~20-30 MB | -20-30 MB |
| Pillow (lazy) | ~0 MB | ~10 MB | -5-10 MB |
| pydantic-ai (lazy) | ~0 MB | ~12 MB | -8-12 MB |
| Image upload (no copies) | — | ~130 MB | -270 MB |
| HTTP clients (shared) | ~8 MB | ~8 MB | -12 MB |
| **TOTAL** | **~100-120 MB** | **~200-250 MB** | **~300-450 MB** |

---

## Phase 1: Docker & Container Optimization

### 1.1 Create `.dockerignore` (CRITICAL)

**File:** `.dockerignore` (NEW)

**Problem:** No `.dockerignore` exists. The entire working directory (1.1 GB) is sent as Docker build context. Secret files (`.env.dev`, `.env.test`, `.env.prod` with live API keys, database passwords) are embedded in the image.

**Action:**
```
.git
.venv
.env.dev
.env.test
.env.prod
.env.example
__pycache__
**/__pycache__
*.pyc
.pytest_cache
.mypy_cache
.ruff_cache
.coverage
htmlcov/
coverage.xml
.factory
.agents
.playwright-mcp
plans
tests
docs
scripts
supabase
chatgpt-widgets
*.png
*.jpg
*.jpeg
digest.txt
gitingest.txt
ghar360_backend.egg-info
.DS_Store
AGENTS.md
CLAUDE.md
README.md
LICENSE
.python-version
Procfile
app.yaml
wasmer.toml
railway.toml
docker-compose.yml
.github
```

### 1.2 Multi-stage Dockerfile (HIGH)

**File:** `Dockerfile`

**Problem:** `gcc`, `g++`, and `libpq-dev` (~150 MB) leak into the runtime image. `uv` binary (~40 MB) also remains at runtime.

**Action:** Replace with multi-stage build:

```dockerfile
# ---- Builder ----
FROM python:3.12-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---- Runtime ----
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv

COPY . .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 3600

CMD ["python", "run.py"]
```

**Savings:** ~190 MB image size (150 MB build tools + 40 MB uv binary)

### 1.3 Memory Limits in docker-compose (CRITICAL)

**File:** `docker-compose.yml`

**Problem:** No memory limits on any service. Services can grow unbounded.

**Action:**
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
  redis:
    command: redis-server --maxmemory 64mb --maxmemory-policy allkeys-lru
    deploy:
      resources:
        limits:
          memory: 128M
```

### 1.4 Remove bind mount in production config

**File:** `docker-compose.yml` line 35

**Problem:** `volumes: [".:/app"]` mounts entire host directory into container, overriding the image's `/app`. Leaks `.env` files, `.git/`, and local `.venv/`.

**Action:** Remove the bind mount for production builds. Keep it only in a `docker-compose.override.yml` for development.

---

## Phase 2: File-Based Disk Cache

### 2.1 Create Disk Cache Backend

**File:** `app/core/cache/backends/disk.py` (NEW)

**Problem:** The default `CACHE_BACKEND = "memory"` stores up to 1000 entries in-process. Each entry can be a full property search result (5-50 KB). Worst case: ~50 MB in process memory. Cleanup interval is 24 hours, so stale entries pile up.

**Action:** Create a new `DiskCacheBackend` that implements the `CacheBackend` protocol:

- Stores values as files on disk using `pickle` (or JSON for simple types)
- Directory: configurable via `CACHE_DISK_DIR` setting, default `/tmp/ghar360_cache`
- Keeps a lightweight `OrderedDict` metadata index in memory (key → file path, expiry timestamp only)
- LRU eviction when `max_size` is reached (deletes oldest file)
- TTL enforcement on read (check metadata, delete expired files)
- Pattern-based invalidation via metadata scan
- Background cleanup task to remove expired files periodically (every 300 seconds)
- Per-entry size limit: reject writes >1 MB
- Thread-safe via `asyncio.Lock`

**Interface contract (must implement):**
- `get(key) → Any | None`
- `set(key, value, ttl) → bool`
- `get_and_delete(key) → Any | None`
- `delete(key) → bool`
- `delete_pattern(pattern) → int`
- `exists(key) → bool`
- `clear() → bool`
- `connect() → None`
- `disconnect() → None`
- `is_available() → bool`

### 2.2 Register Disk Backend in Manager

**File:** `app/core/cache/manager.py`

**Action:**
- Add `DISK = "disk"` to `CacheBackendType` enum
- In `create_from_config()`, add disk backend instantiation path
- Use disk as the default when `CACHE_BACKEND = "disk"`
- Disk backend can still have in-memory as fallback for hot keys

### 2.3 Add Disk Cache Config Settings

**File:** `app/core/config.py`

**Action:** Add new settings:
```python
CACHE_BACKEND: str = "disk"           # Changed from "memory" to "disk"
CACHE_DISK_DIR: str = "/tmp/ghar360_cache"
CACHE_DISK_MAX_SIZE: int = 1000       # Max entries
CACHE_DISK_MAX_ENTRY_BYTES: int = 1_000_000  # 1 MB per entry max
```

### 2.4 Reduce Memory Backend Bloat (if still used as fallback)

**File:** `app/core/cache/backends/memory.py`

**Action:**
- Change default `cleanup_interval` from `86400` (24h) to `300` (5 min)
- Add per-entry size guard: reject values >1 MB in `set()`

---

## Phase 3: Database Connection Pools

### 3.1 Reduce Main Pool Size

**File:** `app/core/config.py:107-108`

**Problem:** Main pool has 5 base + 5 overflow = 10 max connections. Each PostgreSQL connection uses ~5-10 MB client-side. Total: ~50-100 MB.

**Action:**
```python
DB_POOL_SIZE: int = 2      # was 5
DB_MAX_OVERFLOW: int = 2   # was 5
```

New max: 4 connections → ~20-40 MB. **Savings: ~30-60 MB.**

### 3.2 Reduce Background Pool Size

**File:** `app/core/config.py:112-113`

**Action:**
```python
DB_BG_POOL_SIZE: int = 1      # was 2
DB_BG_MAX_OVERFLOW: int = 1   # was 2
```

New max: 2 connections. **Savings: ~10-20 MB.**

### 3.3 Reduce Redis Pool Connections

**File:** `app/core/cache/backends/redis.py`

**Problem:** Hardcoded `max_connections = 50` for a single-worker app.

**Action:** Reduce to 15. Add `CACHE_REDIS_MAX_CONNECTIONS` setting.

---

## Phase 4: SSE Event Bus

### 4.1 Reduce Queue Size

**File:** `app/core/sse.py:26`

**Problem:** `asyncio.Queue(maxsize=256)` per subscriber. With 1000 users: 256K event dicts in memory.

**Action:** Reduce `maxsize` from 256 to 32.

```python
queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
```

**Savings:** 87.5% reduction per queue. 1000 users × 32 × ~500 bytes = ~16 MB (vs ~128 MB).

### 4.2 Increase Reap Frequency

**File:** `app/core/sse.py:71`

**Problem:** Dead queues only reaped every 100 emits.

**Action:** Reap every 10 emits:
```python
if self._emit_count % 10 == 0:
```

### 4.3 Add Global Subscriber Cap

**File:** `app/core/sse.py`

**Action:** Add `MAX_GLOBAL_SUBSCRIBERS = 500` class constant. In `subscribe()`, count total queues and reject if over cap.

### 4.4 Add TTL-Based Queue Eviction

**File:** `app/core/sse.py`

**Action:** Track subscribe timestamps. In `_reap_dead_queues_async()`, also evict queues older than 30 minutes. This catches abandoned browser connections that never unsubscribe cleanly.

---

## Phase 5: Image Processing

### 5.1 Eliminate Full-Resolution Copies

**File:** `app/services/image_processing.py:386-417`

**Problem:** For an 8K panorama (~128 MB raw):
1. `img.convert("RGB")` — first copy (~96 MB)
2. `rgb_img.copy()` for thumbnail — second full-res copy (~96 MB)
3. `rgb_img.copy()` for WebP — third full-res copy (~96 MB)

Peak: ~416 MB per image.

**Action:** Process sequentially without `.copy()`. Use `img.thumbnail()` which modifies in-place. Process thumbnail first, then resize the original for WebP:

```python
with Image.open(io.BytesIO(image_bytes)) as img:
    rgb_img = img
    if img.mode in ("RGBA", "P"):
        rgb_img = img.convert("RGB")

    # Thumbnail (in-place modification is fine — we process sequentially)
    thumb_img = rgb_img.copy()  # Still need copy since thumbnail modifies in-place
    thumb_img.thumbnail((new_w, new_h), Image.Resampling.LANCZOS)
    thumb_buf = io.BytesIO()
    thumb_img.save(thumb_buf, format="WEBP", quality=WEBP_QUALITY, optimize=True)
    thumbnail = thumb_buf.getvalue()
    thumb_img.close()
    del thumb_img

    # Web-optimized: resize returns a new image, no need for copy
    w, h = rgb_img.size
    if w > max_dim or h > max_dim:
        web_img = rgb_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    else:
        web_img = rgb_img
    web_buf = io.BytesIO()
    web_img.save(web_buf, format="WEBP", quality=WEBP_QUALITY, optimize=True)
    web_optimized = web_buf.getvalue()
    if web_img is not rgb_img:
        web_img.close()
    del web_img
```

Actually, since `.thumbnail()` modifies in-place but `.resize()` returns a new image, the optimization is:
- Thumbnail: use `.copy()` + `.thumbnail()` (thumbnail is small, copy is needed)
- WebP: use `.resize()` directly on `rgb_img` (returns new image, no copy needed)

This saves one full-resolution copy (~96 MB).

### 5.2 Add Processing Semaphore

**File:** `app/services/storage/processing.py`

**Problem:** No limit on concurrent image uploads. Multiple concurrent 8K panoramas can spike to >1 GB.

**Action:** Add a module-level semaphore:
```python
_IMAGE_PROCESSING_SEMAPHORE = asyncio.Semaphore(2)
```

Wrap the processing function to acquire the semaphore before reading file content.

### 5.3 Release Base64 Strings in Tour AI

**File:** `app/services/tour_ai/scene_analysis.py:155-188`
**File:** `app/services/tour_ai/hotspot_suggestions.py:108,175`
**File:** `app/services/tour_ai/background.py:258-276`

**Problem:** Base64-encoded panorama images (~50-100 MB each) stay in scope across loop iterations.

**Action:** Add explicit `del image_base64` after creating the `VisionInput` object:
```python
image_base64, mime_type = await _download_image_as_base64(scene.image_url)
vision_input = VisionInput(image_base64=image_base64, mime_type=mime_type)
del image_base64
```

---

## Phase 6: Notification Thread Pool

### 6.1 Reduce Worker Count

**File:** `app/services/notifications/helpers.py:21-24`

**Problem:** 8 threads × 8 MB stack = 64 MB committed.

**Action:**
```python
_NOTIFICATION_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=3,  # was 8
    thread_name_prefix="notif-",
)
```

**Savings:** 40 MB (5 fewer threads × 8 MB).

---

## Phase 7: Lazy-Load Heavy Imports

### 7.1 Lazy-Load MCP Servers

**Files:** `app/factory.py:27`, `app/infrastructure/mcp.py`

**Problem:** `build_mcp_http_apps()` is called in the factory, eagerly loading FastMCP + MCP SDK + all tool modules (~20-30 MB).

**Action:** Move MCP app construction to lifespan startup, or wrap in a lazy proxy that builds on first request. The lifespan approach is cleaner:

```python
# In factory.py — don't call build_mcp_http_apps() eagerly
# Instead, store a reference that lifespan will initialize

# In lifespan.py — build MCP apps during startup
user_mcp_app, admin_mcp_app = build_mcp_http_apps()
app.state.user_mcp_app = user_mcp_app
app.state.admin_mcp_app = admin_mcp_app
```

Or for true lazy loading, use a Starlette middleware that intercepts `/mcp/*` routes and mounts the sub-app on first hit.

### 7.2 Lazy-Load Pillow

**Files:** `app/services/image_processing.py:8-9`, `app/services/storage/processing.py:12`

**Problem:** `from PIL import Image` loads native C extensions (~5-10 MB) at module import time.

**Action:** Move imports to function level:
```python
# Before (module-level):
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS

# After (function-level):
def process_scene_image(image_bytes: bytes, ...):
    from PIL import Image
    ...
```

### 7.3 Lazy-Load pydantic-ai in Blog Scheduler

**File:** `app/services/blog_auto_publish.py:12-15`

**Problem:** `pydantic-ai` imports (~8-12 MB including transitive deps) happen when the scheduler module is loaded.

**Action:** Move imports inside the `publish_draft()` function:
```python
async def publish_draft(...):
    from pydantic_ai import Agent, NativeOutput
    from pydantic_ai.messages import ModelResponse
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    ...
```

---

## Phase 8: Dependency Cleanup

### 8.1 Remove Unused `geojson` Package

**File:** `pyproject.toml:25`

**Problem:** `geojson>=3.2.0` is listed as a dependency but has **zero import statements** anywhere in `app/`. Dead weight.

**Action:** Remove from dependencies.

### 8.2 Replace `lxml` with stdlib `html.parser`

**File:** `pyproject.toml:46`

**Problem:** `lxml>=6.1.0` (~10-15 MB, C extensions) is not directly imported anywhere. It is only used as an acceleration backend for `beautifulsoup4`.

**Action:**
1. In data hub scraper files, change `BeautifulSoup(html, "lxml")` to `BeautifulSoup(html, "html.parser")`
2. Remove `lxml` from `pyproject.toml` dependencies

### 8.3 Audit `PyJWT`

**File:** `pyproject.toml:21`

**Problem:** `PyJWT>=2.9.0` has zero direct imports in `app/`. Likely only used transitively via `supabase`.

**Action:** Verify that `supabase` bundles its own JWT handling. If yes, remove from direct dependencies.

---

## Phase 9: Query-Level Fixes

### 9.1 Add `.limit()` to Unbounded Queries

**Files:** 141 instances across `app/services/`

**Problem:** Queries like `result.scalars().all()` without LIMIT can load entire tables into memory.

**Priority files (highest risk):**

| File | Line(s) | Query |
|------|---------|-------|
| `app/services/notification_dispatcher.py` | 253 | `find_user_ids_for_segment` loads ALL user IDs |
| `app/services/pm_reports.py` | 30 | All PM properties at once |
| `app/services/pm_dashboard.py` | 117, 157, 173, 189 | All charges/payments/maintenance/leases |
| `app/services/flatmates/moderation.py` | 488 | All listings for moderation |
| `app/services/core.py` | 73, 207, 338, 401 | bug_reports, pages, versions, faqs |
| `app/services/visit.py` | 171, 205, 221 | All visits for a user |
| `app/services/swipe.py` | 230, 233 | All swipes |

**Action:** Add safety `.limit(500)` caps to all listing queries. For reporting queries that need full data, use server-side aggregation or batched cursor iteration.

### 9.2 Use `load_only()` on Eager Loads

**Files:** `app/services/property/search.py:162-165` and 67 other locations

**Problem:** `selectinload` chains load full objects including heavy columns.

**Action:** Add `load_only()` to select only needed columns for list endpoints:
```python
query = select(Property).options(
    selectinload(Property.images).load_only(
        PropertyImage.id, PropertyImage.image_url, PropertyImage.is_main_image
    ),
)
```

### 9.3 Bound Scene Processing Tasks Dict

**File:** `app/services/tour/helpers.py:282`

**Problem:** `_scene_processing_tasks: dict = {}` is unbounded. Failed tasks may never be cleaned up.

**Action:** Add max size with oldest-entry eviction. Clean up on task completion (both success and failure paths).

### 9.4 Cap OAuth Token List Per User

**File:** `app/services/oauth_token_store.py:157-165`

**Problem:** Every OAuth token issuance appends to user's token list without pruning.

**Action:** Cap at 10 most recent tokens, prune tokens older than 24 hours:
```python
cutoff = time.time() - 86400
existing = [t for t in existing if t.get("created_at", 0) > cutoff]
existing = existing[-10:]
```

### 9.5 Track Background Task References

**File:** `app/services/tour_ai/background.py:209-222`

**Problem:** `asyncio.create_task()` without retaining reference. Tasks hold closure variables until GC'd.

**Action:**
```python
_background_tasks: set[asyncio.Task] = set()

task = asyncio.create_task(...)
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```

---

## Phase 10: Shared HTTP Clients

### 10.1 Shared FCM/SMS HTTP Client

**Files:** `app/services/notifications/fcm.py:126`, `app/services/sms.py:48`

**Problem:** Every push notification creates and destroys an `httpx.AsyncClient`. Connection churn under burst load.

**Action:** Create module-level singleton clients with proper lifecycle:
```python
_fcm_client: httpx.AsyncClient | None = None

def _get_fcm_client() -> httpx.AsyncClient:
    global _fcm_client
    if _fcm_client is None or _fcm_client.is_closed:
        _fcm_client = httpx.AsyncClient(timeout=30)
    return _fcm_client
```

### 10.2 Share AI Provider HTTP Client

**File:** `app/services/ai/base.py:93-105`

**Problem:** Each AI provider creates its own `httpx.AsyncClient` with 10 max connections. With 2 providers = 20 connections.

**Action:** Reduce per-provider limits:
```python
httpx.Limits(
    max_connections=5,          # was 10
    max_keepalive_connections=2, # was 5
    keepalive_expiry=60,
)
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `.dockerignore` | Exclude secrets, .git, .venv, tests, docs from Docker build |
| `app/core/cache/backends/disk.py` | File-based disk cache backend implementing `CacheBackend` protocol |
| `plans/memory-usage-reduction.md` | This plan document |

## Files to Modify

| File | Change | Phase |
|------|--------|-------|
| `Dockerfile` | Multi-stage build, env vars, remove uv from runtime | 1 |
| `docker-compose.yml` | Memory limits, Redis maxmemory, remove bind mount | 1 |
| `app/core/config.py` | Pool sizes, cache backend type, disk cache settings | 2, 3 |
| `app/core/cache/manager.py` | Add `DISK` backend type | 2 |
| `app/core/cache/backends/memory.py` | Cleanup interval 86400→300, size guard | 2 |
| `app/core/cache/backends/redis.py` | Max connections 50→15 | 3 |
| `app/core/sse.py` | Queue size 256→32, reap every 10, subscriber cap, TTL eviction | 4 |
| `app/services/image_processing.py` | Eliminate copies, lazy PIL import | 5, 7 |
| `app/services/storage/processing.py` | Processing semaphore, lazy PIL import | 5, 7 |
| `app/services/tour_ai/scene_analysis.py` | del base64 after use | 5 |
| `app/services/tour_ai/hotspot_suggestions.py` | del base64 after use | 5 |
| `app/services/tour_ai/background.py` | del base64, track task refs | 5, 9 |
| `app/services/notifications/helpers.py` | Thread pool 8→3 | 6 |
| `app/infrastructure/mcp.py` | Lazy MCP server creation | 7 |
| `app/factory.py` | Defer MCP builds to lifespan | 7 |
| `app/services/blog_auto_publish.py` | Lazy pydantic-ai imports | 7 |
| `pyproject.toml` | Remove geojson, lxml, audit PyJWT | 8 |
| `app/services/tour/helpers.py` | Bound tasks dict | 9 |
| `app/services/oauth_token_store.py` | Cap token list | 9 |
| `app/services/ai/base.py` | Reduce connection limits | 10 |
| `app/services/notifications/fcm.py` | Shared HTTP client | 10 |
| `app/services/sms.py` | Shared HTTP client | 10 |
| Multiple service files | Add `.limit()` to unbounded queries | 9 |

---

## Implementation Order

**Batch 1 (Quick wins, <1 hour each):**
1. `.dockerignore` — immediate image size reduction
2. `Dockerfile` multi-stage — removes ~190 MB from image
3. `docker-compose.yml` — memory limits + Redis config
4. `config.py` pool sizes — reduce from 14→6 connections
5. `sse.py` queue changes — 256→32, reap frequency
6. `notifications/helpers.py` — thread pool 8→3

**Batch 2 (New components, 2-4 hours):**
7. `disk.py` — file-based cache backend
8. `manager.py` — register disk backend
9. `config.py` — disk cache settings

**Batch 3 (Code refactoring, 2-4 hours):**
10. `image_processing.py` — eliminate copies
11. `storage/processing.py` — processing semaphore
12. Lazy imports (PIL, pydantic-ai, MCP)
13. `fcm.py` / `sms.py` — shared HTTP clients

**Batch 4 (Query fixes, 4-8 hours):**
14. Add `.limit()` to unbounded queries (141 instances)
15. Add `load_only()` to eager loads
16. Bound `_scene_processing_tasks` dict
17. Cap OAuth token lists
18. Track background task references

**Batch 5 (Dependency cleanup, <1 hour):**
19. Remove `geojson` from `pyproject.toml`
20. Replace `lxml` with `html.parser`
21. Audit `PyJWT`

---

## Validation

After each batch, validate with:

```bash
# Build and check image size
docker build -t ghar360-test .
docker images ghar360-test

# Run and check memory
docker-compose up -d
docker stats --no-stream

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check app/
```

### Memory Measurement Commands

```bash
# Container RSS
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Process RSS (inside container)
python -c "import psutil; print(f'RSS: {psutil.Process().memory_info().rss / 1024 / 1024:.1f} MB')"

# Python heap breakdown
python -c "
import tracemalloc
tracemalloc.start()
# ... import and start app ...
snapshot = tracemalloc.take_snapshot()
for stat in snapshot.statistics('lineno')[:20]:
    print(stat)
"
```

### Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Docker image size | ~800 MB | ~250 MB |
| Idle RSS (no traffic) | ~300-400 MB | ~100-120 MB |
| Peak RSS (under load) | ~500-700 MB | ~200-250 MB |
| Startup time | ~5-8s | ~3-5s |
| All tests passing | Yes | Yes |
| Ruff lint clean | Yes | Yes |
