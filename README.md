# Rauzr Technologies Pvt Ltd

An AI workspace for **pharma CMC / GxP regulatory compliance** — inspired by
[FurtherAI](https://www.furtherai.com/)'s public-site pattern (landing page,
no forced login, "Book a demo" CTA, optional authenticated workspace), and
built around the founder's existing
[CMC Regulatory Compliance Pipeline](https://cmcregulatorycompliancepipeline-production.up.railway.app/)
concept: **ingest source PDFs → structured extraction → GxP rule audit.**

This is a complete, runnable MVP scaffold, not a finished product. Read
"Limitations & Future Work" at the bottom before treating any part of it as
production-ready.

---

## 0. Login persistence bug — root cause and fix

**Symptom:** a user registers, closes the app, the project restarts
(container redeploy, `docker compose down` + `up`, etc.), and their login
now fails with "Invalid email or password" even though the password is
correct.

**Root cause, confirmed by reading the code, not guessed:**
`backend/app/config.py` defaulted `DATABASE_URL` to a relative SQLite file
(`sqlite:///./veritant.db`) with **no persistent volume behind it**. A
container's filesystem is ephemeral — anything written inside it, including
that SQLite file, is wiped on every rebuild/redeploy/restart unless it lives
on a volume mounted from *outside* the container. So every restart handed
the app a brand-new, empty database. The login endpoint itself was correct
the whole time; it was correctly rejecting a login against a user row that
no longer existed. This was **not** a token/session/localStorage bug — the
frontend's JWT handling (`frontend/src/context/AuthContext.tsx`,
`frontend/src/api/client.ts`) re-validates the stored token against
`/api/auth/me` on load and was already sound.

**Fix implemented:**
1. `backend/app/config.py` — added `require_persistent_database()`: if
   `DATABASE_URL` is SQLite and not pointed at the mounted `DATA_DIR`, the
   app **refuses to boot** when `ENV=production` **or when running on
   Railway at all** (see section 0.1 below — this second condition was
   added after the first fix still wasn't catching every real deployment).
2. `backend/Dockerfile` — creates `/app/data` and declares it a `VOLUME`, so
   a SQLite file placed there survives container restarts if a real volume
   is mounted at that path.
3. `docker-compose.yml` — local dev already used Postgres with a named
  volume (`veritant_pg_data`) for the backend, which is *why* users
   survived restarts locally — the bug only bit non-Compose deployments
   (bare containers, or Railway without the Postgres plugin attached). This
   is now called out explicitly in the compose file's comments.
4. `backend/.env.example` — documents both supported fixes.

The legacy SQLite/Postgres storage identifiers are intentionally retained
after the Rauzr Technologies rebrand. Renaming a database file or Compose
volume without a migration would make existing passwords appear invalid by
starting the app against a new empty database.

**Recommended fix for any real deployment:** attach a managed Postgres
database (Railway's Postgres plugin does this in one click) and set
`DATABASE_URL` to it — this is what `docker-compose.yml` already does for
local dev, and what the README's Railway deploy steps (section 4) require.
SQLite-on-a-volume is documented as a fallback, not the recommended path,
because a single mounted file doesn't handle concurrent writes or backups
as gracefully as managed Postgres.

---

## 0.1 Second pass — why the persistence fix above still didn't work on Railway, and two more real bugs found

A later round reported: "signup and login work locally but not on the
Railway deployment," and separately, "animations aren't showing, some
spots just look white." Both were tracked down by reading the actual code
and testing the fixes, not by guessing.

**Bug 1 — the production-only guard never fired on Railway.**
`require_persistent_database()` only raised when `ENV=production` was set.
Railway does **not** set that variable for you — it's a plain env var the
user has to add on the dashboard, and it's easy to deploy a backend service
without ever touching it. Result: `ENV` silently defaulted to
`"development"`, the guard's condition was `False`, and the backend booted
"successfully" against the same ephemeral SQLite file the section above
already diagnosed — so every Railway restart/redeploy was *still* wiping
every registered user, exactly reproducing "signup works, login later
fails," just on a platform-specific trigger the first fix didn't cover.

*Fix:* `Settings.is_railway` now checks for Railway's own injected env vars
(`RAILWAY_ENVIRONMENT_NAME` / `RAILWAY_ENVIRONMENT` / `RAILWAY_PROJECT_ID`)
directly — these are present on **every** Railway deployment regardless of
what the user configures. `require_persistent_database()` now raises on
`is_production OR is_railway`. Verified by simulating both env-var
combinations locally (see git history / commit for this fix): ephemeral
SQLite + `RAILWAY_ENVIRONMENT_NAME` set now raises immediately with a clear
message in the deploy logs; Postgres + the same Railway var set boots
clean. **This means a Railway backend without Postgres attached will now
fail to deploy loudly instead of running broken silently — attach the
Postgres plugin (or a volume-backed SQLite path) before redeploying this
version.** `app/main.py` also now logs the resolved `env`, `railway`,
`database`, and `cors_origins` values once at startup so a future
misconfiguration shows up directly in Railway's logs instead of requiring
a code read to diagnose.

**Bug 2 — the landing page's animated content had two unrelated problems.**
1. `useGsapReveal` (used on the Product, Company, and Resources pages)
   gates its fade-in on a GSAP ScrollTrigger with `once: true`. ScrollTrigger
   calculates each trigger's pixel position from the DOM layout *at the
   moment it's created*. This app loads two custom Google Fonts
   asynchronously; if a trigger is created before they finish loading (very
   likely — the fonts request is async and nothing blocked on it), the
   fallback-font layout is used, trigger positions are computed against a
   layout that's about to change, and once the swap-in causes a reflow, a
   `once: true` trigger can be left permanently unfired — its element
   stays at its `opacity: 0` starting state forever. That's the literal
   "white where an animation should be": real content, real background
   color, just invisible.
   *Fix:* the hook now calls `ScrollTrigger.refresh()` once fonts finish
   loading (`document.fonts.ready`) and again on `window.load`, so cached
   trigger positions are recalculated against the final layout. As defense
   in depth against *any* other cause of a missed trigger, a one-shot
   safety-net timer now force-completes the reveal a couple of seconds
   after mount if it hasn't played yet — nothing on the page can be stuck
   invisible indefinitely regardless of root cause.
2. `CaseStudyCarousel` rendered four workflow "product screenshots" from
   `/media/product/*.png`. All five files in that folder were confirmed to
   be **byte-identical** (`identify`/`file` showed matching size and
   dimensions) — a single old capture of the pre-rename `/workspace` page,
   still carrying the "Veritant" wordmark, reused for every tab, cropped to
   mostly show pale empty page background against a dark carousel panel.
   Clicking between the four tabs changed nothing visually, and what was
   visible read as a mostly-blank pale rectangle — again, "just white."
   *Fix:* replaced the screenshot dependency entirely with
   `frontend/src/components/WorkflowPreview.tsx`, four distinct hand-built
   inline SVG panels (one real, differentiated mockup per workflow: intake,
   batch release, CoA/KSM matching, nitrosamine screening). This has no
   external asset to go stale, capture, or re-brand again, and it was
   visually confirmed correct by rendering each one directly rather than
   assumed. The stale PNGs and the credits entries describing them were
   deleted.

Both fixes were verified, not just written: `pytest` (7/7 passing),
`npm run build` (clean), and a live local run of both services together —
registering and logging in over HTTP, and loading every route
(`/`, `/product`, `/company`, `/resources`, `/security`, `/workspace`,
`/login`, `/register`) through the Vite dev proxy — all before this file
was packaged.

---

## 1. Architecture and tech stack decisions

### Frontend
| Decision | Choice | Why |
|---|---|---|
| Framework | React 18 + Vite + TypeScript | Fast dev server, small production bundle, strong typing catches API-contract drift at build time. |
| Routing | `react-router-dom` v6 | Standard, small, no server requirement (SPA). |
| State | React Context (`AuthContext`) + local component state | The app's state is small (one optional session, a couple of forms) — Redux/Zustand would be overhead, not value, at this scope. Revisit if the workspace grows multi-step wizards or real-time state. |
| Styling | Tailwind CSS | Fast iteration, consistent design tokens (see `tailwind.config.js`), no CSS-in-JS runtime cost. |
| Accessibility | Semantic HTML, visible focus rings (never suppressed), `prefers-reduced-motion` respected, labeled form fields, `role="alert"` on errors | Baseline accessibility floor rather than an afterthought. |
| Animation | Hand-rolled SVG/CSS/`IntersectionObserver` for the original landing-page elements (hero diagram, marquee, stat counters — see section 7); **GSAP** (`gsap` + `ScrollTrigger`) for the Resources/Company pages and route-change transitions added this round | The original elements didn't need a library — a single loop or one-shot count-up is simpler in plain CSS/RAF. GSAP earns its place for the newer, more numerous scroll-triggered reveals (`useGsapReveal` hook) and the cross-page transition (`PageTransition.tsx`), where `ScrollTrigger` and stagger sequencing would be reinvented by hand otherwise. Every GSAP animation checks `matchMedia("(prefers-reduced-motion: reduce)")` first and sets the final state with no motion if it matches — same contract as the hand-rolled pieces. |
| Typefaces | Source Serif 4 (display) + IBM Plex Sans (body) + IBM Plex Mono (data labels) | Chosen for a regulatory/documentation feel distinct from generic SaaS defaults, not the common cream+terracotta or Inter-everywhere look. |

### Backend
| Decision | Choice | Why |
|---|---|---|
| Framework | FastAPI (Python) | Async-capable, automatic OpenAPI docs at `/api/docs`, first-class Pydantic validation — matches the founder pipeline's existing Python/FastAPI stack. |
| Database | PostgreSQL in production (Railway plugin), SQLite fallback locally | Zero-setup local dev; Postgres is what Railway provisions natively and is portable to any other cloud's managed Postgres. |
| ORM | SQLAlchemy 2.x | Explicit, portable, no vendor lock-in; `DATABASE_URL` is the only thing that changes between environments. |
| Auth | JWT bearer tokens, **optional everywhere except the saved workspace history** | Matches the brief: landing, demo booking, and even a full pipeline run work with zero login. Login only unlocks "see my past runs." |
| Password hashing | `bcrypt` (direct library call) | passlib's bcrypt backend detection is currently broken against bcrypt ≥4.1 (a known, unresolved upstream issue) — calling bcrypt directly is more reliable for a fresh project today. |
| API shape | REST, versionless (`/api/...`) | Simple surface area; see API contracts below. |
| Security | CORS allowlist, security headers, per-IP rate limiting, upload type/size validation, honeypot field on the public booking form, generic auth error messages (no user enumeration) | See full checklist in section 6. |

### Deployment and observability
| Decision | Choice | Why |
|---|---|---|
| Platform | Railway, two services (backend, frontend) from one repo | Matches the founder pipeline's existing deployment target; each service has its own Dockerfile and `railway.json`. |
| Containerization | Docker for both services | Cloud-portable by construction — the same images run on Render, Fly.io, ECS, Cloud Run, etc. with no code changes, only env var and platform-config changes. |
| CI/CD | Railway's git-push auto-deploy (documented); a GitHub Actions test workflow is included so `pytest` runs on every PR before merge | Keeps the scaffold deployable without requiring a CI platform decision, while still gating merges on tests. |
| Environment parity | Single `Settings` object (`app/config.py`) reads everything from env vars; `.env.example` documents every variable for local/staging/prod | 12-factor config — no hardcoded environment-specific values in code. |
| Logging | Structured request logs (method, path, status, duration, request ID) via Python's `logging`, `X-Request-ID` response header | Enough to trace a single request through logs without a full observability stack. |
| Monitoring | `/api/health` (liveness) and `/api/health/ready` (DB connectivity) endpoints, wired into Railway's healthcheck | Minimum viable monitoring; see Future Work for what a production deployment should add. |

### Data flow / secure end-to-end handling
1. Browser → Backend: HTTPS only in any deployed environment (Railway terminates TLS).
2. Auth: password hashed with bcrypt before it ever touches the database; JWTs are short-lived (24h default, configurable) and never contain the password or PII beyond the user ID.
3. File upload → parse: PDFs are validated by content-type and size **before** being handed to the parser; parsing happens in-process and the raw bytes are never persisted to disk or DB — only the derived structured fields and report are stored.
4. Uploaded content is never used to train a model and is not shared with any third party in this scaffold (no third-party AI API calls are wired in at all — the "extraction" is local regex/rule-based; see Limitations).
5. Every mutating request and every pipeline run is rate-limited per IP and logged with a request ID for traceability.

---

## 2. MVP scope and phased roadmap

### Visual upgrade, round 1

The landing page now uses a full-bleed media hero, an honest illustrative audience-mark marquee,
a capability marquee sourced from the product's workflow/rule vocabulary, and a tabbed workspace
case-study panel. The security page exposes implemented controls as visual badges, and the product
rule table uses the shared reduced-motion-aware GSAP reveal hook.

Media credits are tracked in `frontend/public/media/CREDITS.md`. The hero footage and product
captures remain launch placeholders until licensed stock media is downloaded and screenshots are
captured from the deployed workspace. No customer logos, press mentions, testimonials, SOC 2
claims, or ISO 27001 claims were added.

### Must-have (implemented in this scaffold)
- Public landing page, no forced login
- "Book a demo" flow (public, honeypot-protected, persisted to DB)
- Optional login/register (JWT), never required to use the product
- Public, no-auth "run the pipeline on a bundled sample" demo
- Authenticated file upload → pipeline run → scored compliance report
- Signed-in users see their own run and booking history
- **Public Resources hub** (`/resources`, `/resources/:slug`) — real, original
  editorial content (not placeholder text) backed by a full CRUD API;
  reads are public, writes (`POST`/`PATCH`/`DELETE`) are admin-only
- **Company page** (`/company`) — mission, principles, and current-state
  summary, GSAP-staggered on scroll
- **Login-persistence bug fixed** — see section 0 above
- **GSAP-driven animations** on the new pages, plus a route-change fade
  transition (`PageTransition.tsx`) applied globally, all `prefers-reduced-motion`-aware

### Nice-to-have (partially implemented / next up)
- Interactive UI: done at MVP level (file upload, live result table, run history, resource browsing/filtering)
- Animations: MVP set implemented (see above); a richer GSAP timeline for the hero pipeline diagram and page-to-page shared-element transitions are Phase 2
- Responsive UI: implemented (mobile nav, responsive grid) but not cross-browser QA'd
- Deeper accessibility audit (screen-reader pass, color contrast audit on the new pages) — not done
- Analytics hooks (page views, resource read events, CTA clicks) — not implemented; see Future Work

### Future-proofing
- Modular services: `app/services/pipeline.py` is isolated from the API layer specifically so the extraction/audit logic can be swapped (e.g., for an LLM-based extractor) without touching routers or models.
- Cloud-agnostic design: Docker + env-var config + standard Postgres means Railway is a choice, not a dependency. Section 4 documents the AWS/GCP/Render migration path.
- Rule engine is data-driven (`rules.yaml`), not hardcoded — a compliance team can extend it without a code change.
- Resources content is data-driven (`scripts/seed_resources.py` + the `resources` table via the admin API), not hardcoded into the frontend — new articles ship without a frontend redeploy.

---

## 3. System design and data model

### Entities (ERD concept)

```
User (1) ──< (many) DemoBooking      [user_id nullable — bookings work without login]
User (1) ──< (many) PipelineRun      [user_id nullable — sample/guest runs work without login]
Resource                             [standalone — editorial content, no user FK]
```

**User**
`id (uuid pk), email (unique), full_name, company (nullable), hashed_password, is_active, is_admin, created_at`

**DemoBooking**
`id (uuid pk), user_id (fk, nullable), full_name, work_email, company, role (nullable), team_size (nullable), preferred_datetime (nullable), message (nullable), status (enum: pending/confirmed/cancelled/completed), source_ip, created_at`

**PipelineRun**
`id (uuid pk), user_id (fk, nullable), dossier_filename, qa_package_filename, status (enum: queued/running/succeeded/failed), used_bundled_sample (bool), compliance_score (int, nullable), verdict (string, nullable), report_json (text, nullable), error_message (text, nullable), created_at, completed_at (nullable)`

**Resource**
`id (uuid pk), slug (unique), title, summary, body_markdown, category (enum: guide/regulatory_update/whitepaper/changelog), read_minutes, author_name, author_role, published (bool), published_at, updated_at`

Nullable `user_id` on `DemoBooking`/`PipelineRun` is the deliberate mechanism
behind "optional login": every write path works whether or not a JWT is
present. `Resource` has no `user_id` at all — it's editorial content, not
user-generated, so authorship is a plain string field, not a relationship.

### API contract sketches

All responses are JSON. All errors follow `{ "detail": string, "code": string }`.
Full interactive contract (request/response schemas) is auto-generated at
`/api/docs` (Swagger UI) when `DEBUG=true`.

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| GET | `/api/health` | none | — | Liveness probe |
| GET | `/api/health/ready` | none | — | Liveness + DB connectivity |
| POST | `/api/auth/register` | none | `{email, full_name, company?, password}` | 201 + token; 409 if email taken |
| POST | `/api/auth/login` | none | `{email, password}` | 401 on any failure (no user enumeration) |
| GET | `/api/auth/me` | required | — | 401 if no/invalid token |
| POST | `/api/demo-bookings` | optional | `{full_name, work_email, company, role?, team_size?, preferred_datetime?, message?, website?}` | `website` is a honeypot — a filled value returns 201 with a `null` body and persists nothing |
| GET | `/api/demo-bookings/mine` | optional | — | `[]` if not signed in |
| GET | `/api/demo-bookings` | admin only | — | 403 if not admin |
| POST | `/api/pipeline/run-sample` | optional | — | Runs the bundled sample package, no upload needed |
| POST | `/api/pipeline/run` | optional | `multipart/form-data: dossier, qa_package` | 415 if not PDF, 413 if >15MB, 400 if empty |
| GET | `/api/pipeline/runs/{id}` | none* | — | *scaffold-level: returns any run by ID; see Limitations |
| GET | `/api/pipeline/runs` | optional | — | `[]` if not signed in, else caller's own runs |
| GET | `/api/resources` | none | — | Published resources, newest first; `?category=guide\|regulatory_update\|whitepaper\|changelog` filters |
| GET | `/api/resources/{slug}` | none | — | 404 if missing or unpublished |
| POST | `/api/resources` | admin only | `{slug, title, summary, body_markdown, category, read_minutes, author_name, author_role, published}` | 409 if slug taken, 403 if not admin |
| PATCH | `/api/resources/{slug}` | admin only | any subset of the above fields | 404 if missing, 403 if not admin |
| DELETE | `/api/resources/{slug}` | admin only | — | 204 on success, 404 if missing |

### Edge cases handled
- Duplicate registration email → `409 Conflict`, not a 500
- Bad login credentials → `401`, identical message whether the email exists or not
- Non-PDF upload → `415 Unsupported Media Type` before any parsing is attempted
- Oversized upload → `413`, checked before parsing, not after a timeout
- Empty file upload → `400`
- Bot form submission (honeypot filled) → looks like success to the caller, nothing persisted
- Un-parseable / scanned-image PDF → pipeline returns a `failed` status with a user-actionable message (not a 500) — the extracted-field values are simply `null`, and every rule that depends on a missing field fails closed with "could not be extracted," never silently passes
- Rate limit exceeded → `429 Too Many Requests`
- Unhandled server error → `500` with a generic message; full stack trace goes to server logs only, never the client
- Resource slug collision on create → `409 Conflict`
- Unknown `category` filter/value on a resource → `422` with a clear message, not a silent empty result
- App boots with `ENV=production` on an unmounted SQLite `DATABASE_URL` → refuses to start (see section 0) instead of silently risking data loss on the next restart

---

## Routing plan, page wireframes, and key components

### Routes
| Path | Page | Auth | Data source |
|---|---|---|---|
| `/` | Landing | none | static + `PipelineAnimation`/`StatCounter` |
| `/product` | Product | none | static (`rules.yaml`-derived table) |
| `/resources` | Resources (hub) | none | `GET /api/resources` |
| `/resources/:slug` | Resource detail | none | `GET /api/resources/{slug}` |
| `/company` | Company | none | static |
| `/security` | Security | none | static |
| `/book-demo` | Book Demo | optional | `POST /api/demo-bookings` |
| `/login`, `/register` | Auth | none | `/api/auth/*` |
| `/workspace` | Workspace | optional | `/api/pipeline/*` |
| `*` | 404 | none | static |

### Wireframe — Resources hub (`/resources`)
```
┌─────────────────────────────────────────────┐
│ Navbar (Product · Resources · Company · Security) │
├─────────────────────────────────────────────┤
│ Eyebrow: "Resources"                         │
│ H1: Guides, regulatory updates, whitepapers  │
│ Category filter pills: All / Guides / ...    │
├─────────────────┬─────────────────────────────┤
│ Card: category badge, title, summary, │ Card │  ← 2-col grid, GSAP
│ read time, author                     │      │     stagger-reveal
├─────────────────┴─────────────────────────────┤
│ Footer                                        │
└─────────────────────────────────────────────┘
```

### Wireframe — Resource detail (`/resources/:slug`)
```
┌─────────────────────────────────────────────┐
│ Navbar                                        │
├─────────────────────────────────────────────┤
│ ← Back to Resources                           │
│ [category badge] [read time] [date]           │
│ H1: Title                                     │
│ Summary · Author · Role                       │
├─────────────────────────────────────────────┤
│ Article body (Markdown → headings/lists/bold) │  ← GSAP fade+rise on load
├─────────────────────────────────────────────┤
│ Footer                                        │
└─────────────────────────────────────────────┘
```

### Wireframe — Company (`/company`)
```
┌─────────────────────────────────────────────┐
│ Navbar                                        │
├─────────────────────────────────────────────┤
│ Dark hero: eyebrow "Company", H1 mission line │
├─────────────────────────────────────────────┤
│ H2: What we believe                           │
│ 2×2 principle cards (GSAP stagger-reveal)     │
├─────────────────────────────────────────────┤
│ H2: Where the build stands today              │
│ 3-col numbered milestone list (GSAP reveal)   │
├─────────────────────────────────────────────┤
│ Dark CTA band: See the product / Try sample   │
├─────────────────────────────────────────────┤
│ Footer                                        │
└─────────────────────────────────────────────┘
```

### Wireframe — Product (`/product`, existing page, unchanged this round)
```
┌─────────────────────────────────────────────┐
│ Navbar                                        │
├─────────────────────────────────────────────┤
│ Eyebrow "Product", H1, intro paragraph        │
├─────────────────────────────────────────────┤
│ Rule table: ID / Description / Severity       │
│ (data-driven from rules.yaml via the pipeline │
│  service, not hardcoded JSX)                  │
├─────────────────────────────────────────────┤
│ Footer                                        │
└─────────────────────────────────────────────┘
```

### Key components and responsibilities
| Component | Responsibility |
|---|---|
| `PageTransition.tsx` | Wraps `<main>`'s children; on every route change, fades/rises the new page in via GSAP (skipped entirely under reduced motion) |
| `useGsapReveal.ts` | Reusable hook: fades+slides an element (or staggered children matching a selector) in once, the first time it scrolls into view; reduced-motion sets the final state with no animation |
| `Markdown.tsx` | Small, dependency-free renderer for admin-authored resource content — headings, bullet/numbered lists, bold, paragraphs |
| `Resources.tsx` | Fetches and filters published resources by category; renders the GSAP-staggered card grid |
| `ResourceDetail.tsx` | Fetches one resource by slug; handles loading/404/error states distinctly |
| `Company.tsx` | Static mission/principles/milestones content with two independently-staggered reveal groups |
| `PipelineAnimation.tsx`, `StatCounter.tsx`, `TrustMarquee.tsx` | Pre-existing hand-rolled landing-page animations (see section 7) — unchanged this round |
| `Navbar.tsx` / `Footer.tsx` | Updated this round to add Resources/Company links |

---



```
rauzr/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, middleware, error handlers
│   │   ├── config.py            # env-driven Settings
│   │   ├── database.py          # SQLAlchemy engine/session
│   │   ├── models.py            # User, DemoBooking, PipelineRun
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── core/
│   │   │   ├── security.py      # bcrypt hashing, JWT create/decode
│   │   │   ├── deps.py          # optional/required/admin auth dependencies
│   │   │   └── rate_limit.py    # per-IP sliding window middleware
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── demo.py
│   │   │   ├── pipeline.py
│   │   │   ├── resources.py     # public reads, admin-only CRUD writes
│   │   │   └── health.py
│   │   └── services/
│   │       ├── pipeline.py      # ingest -> extract -> audit
│   │       └── rules.yaml       # data-driven GxP-style rule set
│   ├── scripts/
│   │   ├── create_admin.py      # promote/create an admin user
│   │   └── seed_resources.py    # idempotent; runs automatically on boot
│   ├── tests/test_api.py        # pytest smoke tests
│   ├── requirements.txt
│   ├── Dockerfile                # now creates + VOLUMEs /app/data (persistence fix)
│   ├── railway.json
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/                # Landing, Product, Resources, ResourceDetail, Company, Security, BookDemo, Login, Register, Workspace, NotFound
│   │   ├── components/           # Navbar, Footer, PageTransition, Markdown, PipelineAnimation, TrustMarquee, StatCounter
│   │   ├── hooks/                # useCountUp.ts, useGsapReveal.ts
│   │   ├── context/AuthContext.tsx
│   │   ├── api/{client,types}.ts
│   │   └── App.tsx / main.tsx
│   ├── package.json / vite.config.ts / tailwind.config.js   # package.json now includes `gsap`
│   ├── Dockerfile
│   ├── railway.json
│   └── .env.example
├── docker-compose.yml            # local dev: postgres (persistent volume) + backend + frontend
├── .gitignore
└── README.md                     # this file
```

### Running locally

**Option A — Docker Compose (closest to production topology):**
```bash
docker compose up --build
# Frontend: http://localhost:4173
# Backend:  http://localhost:8000/api/docs
```

**Option B — native, fastest iteration loop:**
```bash
# Terminal 1 — backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install   # installs gsap along with existing deps -- required after this round's changes
npm run dev
# open http://localhost:5173 -- Vite proxies /api to :8000 automatically
```

The Resources hub seeds itself automatically and idempotently on backend
startup (`scripts/seed_resources.py`, called from `main.py`) — no manual
step needed to see real content at `/resources`.

### Deploying to Railway
> This sequence is also the fix for the login-persistence bug (section 0) —
> step 3, attaching Postgres, is what makes registered users survive a
> redeploy. Skipping it and leaving the backend on its SQLite default will
> now make the app **refuse to boot** once `ENV=production` is set (step 4),
> rather than silently losing data again.

1. Push this repo to GitHub.
2. In Railway: **New Project → Deploy from GitHub repo**.
3. Add a **Postgres** plugin to the project — Railway injects `DATABASE_URL` automatically.
4. Create **two services** from the same repo, each with its root directory set:
   - `backend` service → root directory `/backend`, Railway auto-detects the Dockerfile. Set env vars from `backend/.env.example` (generate a real `JWT_SECRET_KEY`; set `ENV=production`, `DEBUG=false`, `CORS_ORIGINS` to your frontend's Railway URL).
  - `frontend` service → root directory `/frontend`. Set **build** variable `VITE_API_BASE_URL` to the backend service's public Rauzr Technologies URL — this must be a *build*-time variable since Vite inlines it.
5. Deploy both. Update `CORS_ORIGINS` on the backend once you know the frontend's final URL, and redeploy the backend.
6. (Optional) Run `railway run python -m scripts.create_admin you@company.com "Your Name" "StrongPassword123"` against the backend service to create an admin who can view all demo bookings at `GET /api/demo-bookings`.

#### Railway service-root requirement

This repository is a monorepo. For the full application, configure Railway
with two services as described above:

- Backend service root directory: `/backend` and Dockerfile: `Dockerfile`.
- Frontend service root directory: `/frontend` and Dockerfile: `Dockerfile`.
- Frontend variable: `VITE_API_BASE_URL=https://<backend-public-domain>`.
- Backend variable: `FRONTEND_URL=https://<frontend-public-domain>`.
- Backend variables: `ENV=production`, `DEBUG=false`, a unique `JWT_SECRET_KEY`, and the Railway Postgres `DATABASE_URL`.

The frontend Docker image writes `VITE_API_BASE_URL` into a small runtime
configuration file at container startup, so setting it as a Railway service
variable works even when it is not supplied as a Docker build argument. This
prevents sign-up and login requests from accidentally going to the static
frontend host instead of the FastAPI service. `FRONTEND_URL` is added to the
backend CORS allowlist so browser auth requests are accepted.

If a single frontend service is created from the repository root, the root
`Dockerfile` and `railway.json` provide an explicit static frontend build so
Railway uses Docker instead of failing Railpack autodetection. That mode does
not run the FastAPI backend; use the two-service configuration for login,
resources, demo bookings, and pipeline execution.

### Migrating to another cloud
Nothing here is Railway-specific except the two `railway.json` files (safe
to delete elsewhere) and the reliance on Railway's auto-injected
`DATABASE_URL`. To move to AWS/GCP/Render/Fly:
1. Build and push both Dockerfiles to your registry of choice.
2. Provision a managed Postgres instance; set `DATABASE_URL` on the backend service.
3. Set the same env vars documented in each `.env.example`.
4. Point the frontend's `VITE_API_BASE_URL` build var at the new backend URL and rebuild.
No application code changes are required — this is the entire point of keeping config in env vars and using standard Postgres/Docker.

---

## 5. Example starter code

All of it — this is a complete, runnable scaffold, not snippets. See the
file tree above. Highlights:
- `backend/app/services/pipeline.py` — the ingest/extract/audit logic
- `backend/app/routers/pipeline.py` — public sample-run + authenticated upload endpoints
- `frontend/src/pages/Workspace.tsx` — the interactive demo UI (both flows)
- `frontend/src/pages/BookDemo.tsx` — public lead-capture form with honeypot

---

## 6. Quick-start guide and verification steps

### Verify data flows securely
1. Start the stack (Docker Compose or native, above).
2. `curl -i http://localhost:8000/api/health` → confirm `200` and no stack trace in any error path (try `curl -i http://localhost:8000/api/pipeline/runs/does-not-exist` → should return the generic `{"detail": "...", "code": "HTTP_404"}` shape, never a traceback).
3. Register a user, confirm the password isn't visible anywhere in `docker compose logs backend`.
4. Upload a non-PDF file to `/api/pipeline/run` → confirm `415`, not a 500 or a hang.

### Perform a demo booking
1. Visit the frontend, click **Book a demo** in the nav.
2. Fill the form (no login) and submit.
3. Confirm the success screen renders.
4. Verify persistence: `curl -X POST http://localhost:8000/api/auth/register -H 'Content-Type: application/json' -d '{"email":"admin@rauzr.local","full_name":"Admin","password":"StrongPassword123"}'`, then promote that user with `python -m scripts.create_admin admin@rauzr.local Admin StrongPassword123`, log in, and `curl http://localhost:8000/api/demo-bookings -H "Authorization: Bearer <token>"` to see the booking.

### Verify the Resources hub and the persistence fix
1. `curl http://localhost:8000/api/resources` → confirm 4 seeded articles come back with real body content, not placeholder text.
2. `curl http://localhost:8000/api/resources/reading-a-cmc-dossier-in-30-minutes` → confirm the full article.
3. Register a user (or reuse the admin from above), then restart the stack (`docker compose down && docker compose up`, or `Ctrl-C` + re-run `uvicorn` natively) and log back in with the same credentials — this is the exact scenario that used to fail. With Postgres (Compose's default) it already worked; the fix matters for a bare-container or SQLite-without-a-volume deployment.
4. Try `curl -X POST http://localhost:8000/api/resources -d '{...}'` without a token → confirm `401`; with a non-admin token → confirm `403`.

### Basic security checklist
- [x] Passwords hashed with bcrypt, never logged or returned by the API
- [x] JWTs expire (24h default) and are validated on every protected request
- [x] CORS restricted to an explicit origin allowlist, not `*`
- [x] Security headers set (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)
- [x] File upload type/size validated before processing
- [x] Rate limiting on mutating and pipeline endpoints
- [x] Honeypot on the public booking form
- [x] Generic, non-enumerating auth error messages
- [x] Consistent error response shape, no stack traces leaked to clients
- [ ] Not yet done: CSRF isn't a concern for this token-in-header SPA pattern, but if you add cookie-based sessions later, add CSRF protection
- [ ] Not yet done: dependency vulnerability scanning in CI (see Future Work)
- [ ] Not yet done: secrets management beyond platform env vars (e.g. a dedicated secrets manager) for larger teams

---

## 7. Visual polish pass (landing page + Workspace, this round)

This round brought the landing page and Workspace states up from a flat scaffold
toward the level of intentionality in the FurtherAI reference, without adding
any new dependencies — everything below is hand-rolled with SVG, CSS
`@keyframes`, and `IntersectionObserver`. `package.json` is unchanged.

**Hero — animated pipeline diagram** (`src/components/PipelineAnimation.tsx`).
Replaces the static JSON preview box with a three-node SVG diagram
(Ingest → Extract → Audit). A dot travels the connecting line, nodes light up
in sequence on a ~6.4s loop, and a small mono readout below updates per stage,
settling on `verdict → PASS · 100%`. This is the one bold animated element on
the page — every other addition below is intentionally quieter. It fully
respects `prefers-reduced-motion`: the component checks
`matchMedia("(prefers-reduced-motion: reduce)")` on mount and again on change,
and freezes on the completed "PASS" state with the SVG `<animate>` circle and
CSS transitions removed rather than sped up.

**"Trusted by" marquee** (`src/components/TrustMarquee.tsx`). A slow
(28s) auto-scrolling strip of text wordmarks — placeholder company names, not
real logos, since there are no real customers yet. The list is duplicated
once and translated by exactly `-50%` for a seamless loop; the duplicate copy
is `aria-hidden` so screen readers only announce the wordmarks once. Pauses
on `:hover` and `:focus-within` via `group-hover:[animation-play-state:paused]`.
Under reduced motion, the global CSS rule freezes it at rest instead of letting
it flash through the truncated keyframe.

**Stat counters** (`src/hooks/useCountUp.ts` + `src/components/StatCounter.tsx`).
A small reusable hook that uses `IntersectionObserver` (fires once, `threshold: 0.4`)
and `requestAnimationFrame` with an ease-out cubic curve to count up when the
stats row scrolls into view — not on every re-render, and not on mount if the
row is already off-screen. Under reduced motion it snaps straight to the
target value. Added three stats to the hero (accuracy, speed multiple, rules
evaluated) that didn't exist in the previous version of the landing page.

**Workflow cards.** The four "Built for regulatory and quality teams" rows
became bordered cards with `hover:-translate-y-1 hover:border-teal hover:shadow-md`
— a lift and border-color change on interaction only, flat by default.

**Workspace loading & empty states** (`src/pages/Workspace.tsx`). Previously
the result panel just didn't render until a run finished, with only the
button label ("Running…") indicating anything was happening. Now:
- While `running`, a skeleton block (pulsing header lines + four pulsing rows
  mimicking the findings table) renders in the result panel's place, marked
  `aria-live="polite" aria-busy="true"` with an `sr-only` status line.
- When there's no run yet and nothing is running, a dashed-border empty state
  explains what to do next, instead of the panel simply not existing.

**Purge verification (item 6).** `Workspace.tsx` builds two CSS class strings
from lookup objects at runtime — `severityColor[f.severity]` and
`verdictColor[run.verdict]`. Ran `npm run build` and grepped the actual
`dist/assets/*.css` output (not dev mode) for every literal class string used
as a value in both objects, plus every new class this pass introduced
(`animate-marquee`, `animate-pulse-soft`, `hover:-translate-y-1`,
`hover:border-teal`, etc.) to confirm Tailwind's static analyzer picked them
up. **Found and fixed a real pre-existing bug in the process:**
`severityColor.major` was `"text-amber-dark"`, but `tailwind.config.js` only
defined `amber.DEFAULT` and `amber.light` — there was no `amber.dark`, so that
class was never generated and "major"-severity findings rendered with **no
color at all** in the results table. Fixed by adding `amber.dark: "#7A5209"`
to the config, mirroring the existing `teal` DEFAULT/light/dark pattern.

**Responsive + accessibility pass (item 7).** Reviewed every touched
component's Tailwind breakpoints (`sm:`/`md:`/`lg:`) for 375px, 768px, and
1440px behavior, and computed exact WCAG contrast ratios (relative luminance
formula) for the navy (`ink`, `#0F1B2B`) hero section's text colors against
its background. Two real failures turned up and were fixed:
- `text-teal-light` (`#2E8C7D`) on `ink` was **4.26:1** — just under the
  4.5:1 AA threshold for normal text — used for the hero eyebrow label and
  the pipeline verdict readout. Brightened `teal.light` to `#3AA391`
  (**5.63:1**) in `tailwind.config.js`; it's only ever used as text on this
  dark background, so the change is safe everywhere it appears.
- `text-paper/40` (**3.55:1**) in the new pipeline animation's caption text
  failed the same threshold. Bumped to `text-paper/60` (**6.37:1**).
- Verified `text-paper/50` (used for the "No account required" caption,
  pre-existing) is **4.81:1** — passes.
- Focus order: nav → hero primary/secondary CTAs → stats (non-interactive) →
  marquee (non-interactive, wordmarks are not links) → workflow cards
  (non-interactive) → trust section → footer. No `tabIndex` overrides were
  introduced; the marquee's duplicated wordmarks are `aria-hidden` so they
  don't appear in the accessibility tree twice.

**Honest caveat on this pass:** the sandbox this was built in has a network
allowlist that blocks the Playwright/Chromium download, so the responsive
and contrast checks above were done by code review and by computing WCAG
contrast ratios directly from the hex/opacity values in use — not by
capturing live screenshots at each breakpoint. The math is exact (standard
relative-luminance formula), but do a final look in real browser devtools at
375/768/1440px before shipping, and consider adding Playwright visual
regression tests as one of the future-work items below.

---

## What's done vs. pending, limitations, and future work

### Done and verified
- Backend: all routers, models, auth, rate limiting, error handling from
  the prior round — **7/7 pytest tests passing** as of the last verified run.
- Frontend: all original pages, routing, auth context, API client — **built
  cleanly with `tsc -b && vite build`** as of the last verified run.
- Docker Compose local stack, Dockerfiles for both services, Railway config for both services.
- Landing page visual pass (hero diagram, marquee, stat counters, workflow cards) — see section 7.

### Done this round, verified by code review and `py_compile` (not by execution — see caveat below)
- **Rebrand:** Rauzr Technologies Pvt Ltd is now the project identity across frontend metadata, backend app identity, Docker identifiers, and documentation.
- **Login-persistence bug:** root-caused and fixed (section 0). `backend/app/config.py`, `main.py`, and `Dockerfile` changes compile and import correctly (`python -m py_compile` passed on every touched file); the production-boot guard's logic was traced by hand against both the "SQLite outside DATA_DIR" and "Postgres" cases.
- **Resources hub:** new `Resource` model, Pydantic schemas, admin-gated CRUD router, idempotent seed script with four original, substantive articles (not lorem ipsum) — all `py_compile`-clean.
- **Company page:** static content page, no backend dependency.
- **GSAP integration:** `useGsapReveal` hook, `PageTransition` wrapper, applied to `Resources.tsx`, `ResourceDetail.tsx`, `Company.tsx`, and globally via `App.tsx`. Added `gsap` to `frontend/package.json`.

### Honest caveat on this round
The sandbox this was built in has **no network access**, so I could not run
`pip install` / `pytest` for the backend changes or `npm install` / `npm run
build` for the frontend changes (including pulling down the new `gsap`
dependency) inside this session. Everything above was verified as far as
possible without execution: Python files were syntax- and import-checked
with `py_compile`; TypeScript/TSX files were written against the exact
existing patterns in the codebase (`useCountUp.ts`'s reduced-motion
convention, `client.ts`'s `ApiError`/`api.get` shape, `schemas.py`'s
Pydantic v2 style) and cross-checked by re-reading the files they call into,
but **not compiled by `tsc` or run in a browser**. Before deploying:
```bash
cd backend && pip install -r requirements.txt && pytest        # confirm 7/7 + any new tests
cd frontend && npm install && npm run build                    # confirms gsap resolves and tsc is clean
```
Treat this the same as the existing "responsive/contrast checks done by
code review, not live browser" caveat further down — the reasoning is
sound and the patterns are consistent with the rest of the codebase, but
execution is the final gate before shipping.

### Known limitations (read before treating this as production-ready)
1. **Extraction is regex-based, not real NLP/LLM extraction.** `services/pipeline.py` uses simple patterns to pull yield %, nitrosamine ppm, deviations, etc. out of PDF text. This works for the bundled sample and reasonably well-structured text-based PDFs, but will under-extract from real-world scanned dossiers, unusual layouts, or non-English documents. This is the single most important thing to replace before any real regulatory use — swap in a layout-aware parser or an LLM extraction step with schema validation.
2. **Rule set is illustrative, not validated.** The six rules in `rules.yaml` are a plausible-looking GxP-style example, not a reviewed compliance rule library. Do not use the verdicts this scaffold produces for any real filing decision.
3. **`create_all()` schema management, no migrations.** Fine for an MVP; once real data exists, add Alembic before making schema changes, or you risk data loss.
4. **In-process rate limiting.** Correct for one Railway replica; incorrect the moment you scale to multiple instances (each has independent counters). Move to Redis-backed limiting before scaling out.
5. **No email delivery wired up.** Demo bookings are persisted and viewable via the admin endpoint, but no confirmation email is sent (SMTP settings exist in config but are inert). Wire up a transactional email provider before relying on this for real leads.
6. **`GET /api/pipeline/runs/{id}` has no ownership check** — it returns any run by ID to any caller, since run IDs are UUIDs and this endpoint exists mainly to let a just-completed run be re-fetched. Add an ownership/admin check before this is exposed beyond a demo.
7. **No automated frontend tests.** Backend has pytest coverage; the frontend has none. Add Vitest + React Testing Library for the forms and Workspace flow next.
8. **No CI pipeline included in this delivery**, though the repo structure supports adding one trivially (a GitHub Actions workflow running `pytest` and `npm run build` on PR is a natural next step).
9. **Uploaded PDF bytes are held only in memory during a request**, never written to disk or object storage — fine for a demo, but means there's no way to re-run an audit against the original file later. If that's needed, add S3/GCS-compatible storage and store a reference, not the bytes, in the DB.
10. **Accessibility and cross-browser QA are partial.** Structural accessibility (labels, focus states, reduced-motion) is in place, and the hero section's text/background contrast has now been computed and fixed (see section 7). What's still missing: a real screen-reader pass (VoiceOver/NVDA), and a live cross-browser/cross-device check — the responsive review this round was done by code inspection of Tailwind breakpoints, not by rendering the app in an actual browser at each width, because the sandbox used to build this couldn't download a headless browser.
11. **No visual regression coverage.** The animated hero, marquee, and count-up components have no automated test confirming they render or animate correctly — a manual QA step or a Playwright visual test suite is the natural next addition.
12. **No admin UI for the Resources CRUD.** Writing/editing/retracting a resource is API-only (`curl`/Swagger at `/api/docs`) — there's no in-app admin dashboard yet. Fine for a small, trusted admin team; add a minimal admin page before non-technical editors need to publish.
13. **`Markdown.tsx` is intentionally minimal** — headings, lists, bold, and paragraphs only. No links, images, code blocks, or tables. Sufficient for the four seeded articles; swap in a real markdown library (e.g. `react-markdown`) if articles need richer formatting.
14. **No automated tests for the Resources feature** (backend or frontend) — the existing `test_api.py` pattern (register → login → assert) is the template to follow for `/api/resources` CRUD and the honeypot-style edge cases (duplicate slug, unknown category, non-admin write attempt).
15. **This round's changes were not executed in this sandbox** (no network access) — see the caveat above. Run the install + test commands there before deploying.

### Recommended next steps, roughly in priority order
1. Replace regex extraction with a real document-understanding pipeline (layout-aware parsing or LLM extraction + schema validation), and expand `rules.yaml` with a reviewed rule set.
2. Add Alembic migrations before the schema changes again.
3. Add ownership checks to `GET /api/pipeline/runs/{id}`, and pagination to the history/admin list endpoints.
4. Move rate limiting to Redis for multi-instance scaling.
5. Wire up transactional email for demo-booking confirmations.
6. Add a GitHub Actions CI workflow (`pytest` + `npm run build` on every PR).
7. Add Vitest coverage for the frontend forms and Workspace flow.
8. Add object storage for uploaded source PDFs if audit re-runs or human review of the original document are required.
9. Full accessibility pass with a real screen reader, plus a live cross-browser/cross-device QA session (real devtools at 375/768/1440px, not just breakpoint code review).
10. Add Playwright (or similar) visual regression tests for the animated hero, marquee, and count-up components.
11. Run `npm install && npm run build` and `pytest` for this round's changes in an environment with network access (see caveat above) before deploying.
12. Build a minimal admin page for Resources CRUD (list + create/edit/publish toggle form), replacing raw `curl`/Swagger usage.
13. Add analytics hooks (page views, resource read events, CTA clicks) — Phase 2 per the brief; a lightweight approach is a `POST /api/events` endpoint plus a `usePageView()` hook mirroring `useGsapReveal`'s structure, or wiring in a privacy-respecting third-party analytics script behind a `VITE_ANALYTICS_ID` env var.
14. Swap `Markdown.tsx` for a full markdown library once articles need links/images/code blocks.
15. Add pytest coverage for `/api/resources` (public list/get, admin create/patch/delete, 401/403/404/409/422 paths) following the existing `test_register_and_login_flow` pattern.
