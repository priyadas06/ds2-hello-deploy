# Deployment Strategy

This document describes our deployment strategy that covers — branching model,
environment design, CI/CD pipeline structure, testing strategy, containerization, artifact
management, traffic handling, security, and rollback.

---

## Table of Contents

- [Philosophy](#philosophy)
- [Branching Strategy](#branching-strategy)
- [Environment Strategy](#environment-strategy)
- [CI/CD Pipeline Design](#cicd-pipeline-design)
- [Testing Strategy](#testing-strategy)
- [Containerization Strategy](#containerization-strategy)
- [Artifact Management](#artifact-management)
- [Deployment Strategies](#deployment-strategies)
- [Security Strategy](#security-strategy)
- [Traffic Handling](#traffic-handling)
- [Secrets Management](#secrets-management)
- [Observability and Health Checks](#observability-and-health-checks)
- [Rollback Strategy](#rollback-strategy)
- [Role of Docker and Docker Compose](#role-of-docker-and-docker-compose)
- [How the Hello World App Demonstrates This Strategy](#how-the-hello-world-app-demonstrates-this-strategy)
- [Known Limitations of the Demo](#known-limitations-of-the-demo)

---

## Philosophy

The goal of this deployment strategy is to make shipping software to production:

- **Safe** — broken code cannot reach users without being caught by automation first
- **Fast** — the time between a developer finishing a change and it being live is measured in
  minutes, not days or tickets
- **Repeatable** — every deployment follows the exact same process regardless of who triggers it
- **Auditable** — every change to production is traceable to a specific commit, a specific author,
  and a specific pipeline run
- **Recoverable** — when something goes wrong (and it will), the team can get back to a known-good
  state quickly and with confidence

These five properties drive every specific decision in our strategy.

---

## Branching Strategy

### Trunk-Based Development

We recommend using the **trunk-based development**. `main` is the single source of truth — the "trunk"
— and it is always in a deployable state. All work happens on short-lived feature branches that are
merged back into `main` frequently, ideally within one to two days of being opened.

```
main  ──────────────────────────────────────────────────────► (always deployable)
          ▲             ▲                ▲
          │             │                │
feature/a ──►     feature/b ──►    feature/c ──►
(merged)          (merged)           (merged)
```

### Why Not Git Flow

Git Flow (with `develop`, `release`, and `hotfix` branches) was the dominant pattern in the 2010s.
It is now considered outdated for most teams for two reasons: it delays integration, which means
bugs hide in long-lived branches until merge time, and it adds significant branch-management
overhead with no meaningful benefit for teams that have good CI. Trunk-based development solves
both problems by integrating continuously.

### Branch Protection Rules

`main` is protected at the platform level (GitHub branch protection rules), not by developer
discipline. The following rules are enforced:

- **No direct pushes to `main`** — every change must go through a pull request, including changes
  by repository administrators
- **Required status checks** — the CI pipeline (build and test) must pass before a pull request
  can be merged
- **Required review** — at least one approving review from a team member other than the author is
  required before merge (in a solo project this is relaxed to zero approvals, but the rule exists
  and is documented as a known deviation from the standard)
- **No force pushes** — the commit history of `main` is immutable; history cannot be rewritten

### Pull Request Workflow

The full lifecycle of a change:

1. Developer creates a branch from the latest `main`:
   `git checkout -b feature/description-of-change`
2. Work is committed to the feature branch. Commits are small and focused.
3. When the change is ready, the developer opens a **pull request** targeting `main`.
4. Opening the PR triggers the **CI pipeline** — build and test run automatically.
5. A reviewer reads the code, checks the CI result, and approves or requests changes.
6. Once approved and CI is green, the PR is merged into `main`.
7. The merge to `main` triggers the **CD pipeline** — the change is automatically deployed.
8. The feature branch is deleted after merge.

The critical rule: **CI runs on the pull request. CD runs on the merge.** These are two separate
events with two separate responsibilities, and they must never be collapsed into one.

---

## Environment Strategy

The real system runs the same application across multiple environments, each serving a
different purpose:

### Development (local)

- Runs on the developer's own machine
- Uses Docker Compose to replicate the production environment locally
- Never connected to production data or infrastructure
- The developer is responsible for keeping it working; it is not monitored

### Staging

- A full replica of the production environment running on real infrastructure
- Receives every change automatically after it passes CI (continuous deployment to staging)
- Used for integration testing, manual QA, and verifying that the application works on real
  infrastructure before it reaches users
- Has its own isolated database, secrets, and configuration — never shares anything with production
- A manual approval gate sits between staging and production: a human must explicitly approve the
  promotion before the production deployment runs

### Production

- The live environment that serves real users
- Receives changes only after they have passed CI, been deployed to staging, and been manually
  approved
- Has stricter monitoring, alerting, and on-call coverage than staging
- Deployments are logged and auditable

### Environment Separation in Practice

Each environment has:
- Its own infrastructure (separate EC2 instances, separate AWS accounts in larger organizations)
- Its own set of secrets and credentials, scoped to that environment
- Its own deployment pipeline stage, triggered separately
- Its own domain or IP address

No secret, credential, or configuration value is shared between environments.

---

## CI/CD Pipeline Design

### The Two Responsibilities

The pipeline has two distinct, non-overlapping responsibilities:

**Continuous Integration (CI)** — validate that the code is correct before it reaches `main`.
Runs on every pull request. Its job is to say "this change is safe to merge" or "this change is
not safe to merge." It never deploys anything.

**Continuous Deployment (CD)** — automatically ship every change that has been validated and
merged. Runs only on push to `main` (which can only happen via a reviewed, CI-passing pull
request). Its job is to take the validated change and make it live.

### Pipeline Stages

```
Pull Request opened
│
├── [CI] Build
│     Build the Docker image from the Dockerfile.
│     If the image fails to build, the pipeline fails here.
│     No code proceeds past a build failure.
│
├── [CI] Test
│     Start the container from the built image.
│     Run automated tests against the running container.
│     Assert the application responds correctly on all expected endpoints.
│     Tear down the container.
│     If any test fails, the pipeline fails here.
│
Pull Request approved + CI green → Merge to main
│
├── [CD] Build & Push
│     Rebuild the Docker image (now targeting the merged commit on main).
│     Tag the image with the Git commit SHA for full traceability.
│     Push the tagged image to the container registry.
│
├── [CD] Deploy to Staging
│     Pull the tagged image on the staging server.
│     Run docker compose up -d --force-recreate.
│     Run a post-deploy health check against the staging URL.
│     Pipeline fails if the health check does not return success.
│
├── [Manual Gate] Approval required for production
│     A human reviews the staging deployment.
│     Approves or rejects the production deployment.
│
└── [CD] Deploy to Production
      Pull the same tagged image on the production server.
      Run docker compose up -d --force-recreate.
      Run a post-deploy health check against the production URL.
      Pipeline fails if the health check does not return success.
      On failure, automatic rollback to the previous image tag.
```

### Trigger Conditions

| Event | CI runs | CD runs |
|---|---|---|
| Push to a feature branch | No | No |
| Pull request opened/updated | Yes (build + test) | No |
| Push to `main` (via merge) | Yes (build + test) | Yes (deploy) |
| Manual trigger | Optional | Optional (with approval) |

### Runners and Executors

Pipelines run on **managed hosted runners** (GitHub Actions). These are provisioned fresh for every pipeline run and torn down immediately after so that:

- No state leaks between runs — the environment is identical every time
- No maintenance burden for the team — the runner infrastructure is managed by the platform
- Credentials are never cached on persistent machines

---

## Testing Strategy

Testing is not a single step that lives in CI — it is a layered system spread across the entire
pipeline. Each layer catches a different class of problem, runs at a different point, and uses
different tooling. The layers are deliberately ordered from fastest and cheapest to slowest and
most expensive, so the pipeline fails as early and as cheaply as possible when something is wrong.

### The Test Pyramid

```
                     ▲
					/ \
                   /E2E\            Fewest tests — simulate real user flows
                  /─────\           Slow, expensive, run against real environments
                 / Integ \          Test how components interact
                /─────────\         Medium speed, may need external services
               /   Unit    \        Most tests — test individual functions
              /─────────────\       Fast, no external dependencies, run everywhere
```

The pyramid shape means many fast unit tests form the base, fewer integration tests in
the middle, and a small number of E2E tests at the top. Inverting the pyramid (many E2E, few unit
tests) produces a slow, brittle, expensive test suite.

### Layer 1 — Unit Tests

**What:** Test individual functions and classes in complete isolation. No database, no network, no
filesystem — external dependencies are replaced with mocks/stubs.

**When they run:** On every push to any branch, and in CI on every pull request. They are the
first thing that runs because they are the fastest — a full unit test suite for a typical service
runs in under 30 seconds.

**Coverage:** Aim for 80%+ line coverage as a minimum gate. Coverage below this threshold fails
the pipeline.

### Layer 2 — Integration Tests

**What:** Test how components work together — the application talking to a real database, the
application calling a real external API, multiple services interacting. Unlike unit tests, nothing
is mocked; real dependencies are running.

**When they run:** In CI on pull requests, after unit tests pass. They are slower than unit tests
because they involve real I/O and network calls.

**Tool:** `pytest` with `docker compose` to spin up dependencies.

### Layer 3 — Smoke Tests

**What:** The minimum viable check that the deployed application is alive and serving traffic.
Test things like : Did the container start, bind the port, and
respond to HTTP? If smoke tests fail, nothing else matters.

**When they run:** In CI immediately after the container is started from the built image, and
again after every deployment to staging and production as a post-deploy verification step.

### Layer 4 — End-to-End (E2E) Tests

**What:** Simulate a real user interacting with the fully deployed application through a real
browser or HTTP client. Test complete user flows from start to finish across the entire stack.

**When they run:** Against the staging environment after every successful deployment to staging —
never directly in CI against a local container, because they require the full environment to be
running. Never against production directly.

### Layer 5 — Performance and Load Tests

**What:** Verify the application behaves correctly under the expected volume of concurrent users
and requests. Catch memory leaks, slow queries, and resource exhaustion before they affect real
users.

**When they run:** Not on every commit — on a schedule (nightly or weekly) against the staging
environment, and before major releases. Running load tests on every PR would be too slow and costly.

**Define acceptance thresholds before running** — e.g. p95 response time under 200ms, error rate
under 0.1% at 100 concurrent users. A load test without defined thresholds is an observation,
not a test.

### Layer 6 — Security Testing

**What:** Automated scanning for known vulnerabilities in the code and in the running application.
Two distinct approaches serve different purposes:

**SAST — Static Application Security Testing:** scans source code and dependencies without running
the application. Catches known vulnerable dependency versions, dangerous code patterns, and secrets
accidentally committed to source.

**Tools:** `Bandit` (Python source), `Trivy` (Docker image and dependency manifest scanning)

**DAST — Dynamic Application Security Testing:** scans the running application by sending crafted
inputs and observing responses. Catches runtime vulnerabilities like SQL injection, XSS, missing
security headers, and open redirects that static analysis cannot detect.

**Tools:** `OWASP ZAP` (free, widely used in industry)

DAST always runs against staging after deployment — never in CI against a local container, and
never directly against production.

### Where Each Testing Layer Sits in the Full Pipeline

```
Feature branch (local development)
  └── Developer runs unit tests locally before pushing

Pull Request opened → CI runs
  ├── Unit tests          fast, fails immediately if logic is broken
  ├── Integration tests   medium, fails if components don't work together
  ├── Smoke test          fast, fails if the container doesn't start or respond
  └── SAST / image scan   fails if known vulnerabilities are present

Merge to main → Deploy to Staging → CD runs
  ├── Smoke test          post-deploy, fails if staging app isn't serving
  ├── E2E tests           run against the live staging environment
  └── DAST scan           run against the live staging environment

Nightly scheduled run
  └── Load tests          run against staging, never production

Manual approval → Deploy to Production → CD runs
  └── Smoke test          post-deploy, triggers automatic rollback on failure
```

---

## Containerization Strategy

### Why Docker

Docker solves the fundamental "works on my machine" problem by packaging the application with its
exact runtime, system libraries, and dependencies into a single portable image. The same image
runs identically on a developer's laptop, inside a CI runner, and on a production server. This
is what makes the pipeline reproducible — the artifact is defined precisely, not assembled
differently in each environment.

### Image Design Principles

**Use the smallest viable base image.** A smaller image has less attack surface (fewer packages
that could contain vulnerabilities), downloads faster, and starts faster.

**Separate dependency installation from application code.** Copy the dependency manifest
(`requirements.txt`, `package.json`) and install dependencies before copying the application
source. Docker caches layers — if dependencies haven't changed, the installation layer is reused
on every rebuild, making builds significantly faster.

**Run as a non-root user.** A container that runs as root gives any attacker who escapes the
container root access to the host. Creating and switching to a dedicated application user before
the `CMD` instruction closes this attack vector.

**Pin dependency versions.** Every dependency must be pinned to an exact version.

**Use `.dockerignore`.** The build context sent to the Docker daemon should contain only what the
application needs to run. Version control directories (`.git`), CI configuration (`.github`),
local environment files (`.env`), editor configuration, and documentation add unnecessary size
and risk to the image.

**Add a `HEALTHCHECK`.** The `HEALTHCHECK` instruction tells Docker how to test whether the
container is actually working, not just running. A container can be in a `running` state while the
application inside it is deadlocked, out of memory, or serving errors. `HEALTHCHECK` exposes this
distinction — `docker ps` will show `healthy` or `unhealthy`, not just `Up`.

---

## Artifact Management

### Build Once, Deploy the Same Artifact Everywhere

A fundamental principle of a sound deployment pipeline: **the artifact built by CI is the exact
artifact deployed to production.** Building the image again at deploy time, even from the same
source code, is not sufficient — it opens the possibility of environment differences, package
registry changes between the two builds, or subtle non-determinism in the build process producing
a different result.

The correct pattern:

1. CI builds the image once
2. CI pushes the image to a container registry, tagged with the Git commit SHA
3. The deploy stage pulls that exact tag — it does not rebuild
4. Every environment (staging, production) runs the identical bytes

### Image Tagging

Images are tagged with two identifiers simultaneously:

- **Commit SHA tag** — immutable, points to a specific commit forever, used
  for rollbacks and audit
- **`latest` tag** — mutable, always points to the most recent build, used for convenience

The commit SHA tag is what the deployment pipeline uses. The `latest` tag is a convenience for
local development only and is never referenced in production Compose files or deployment
manifests.

### Container Registry

The container registry is the storage layer for built images. For GitHub-hosted projects, GitHub
Container Registry is the natural choice — it is free, scoped to the repository, and
accessible using the automatically-provided `GITHUB_TOKEN` without any additional credential
management.

---

## Deployment Strategies

For deployment strategy despite infrastructure complexity we suggest the Blue-Green deployment.

### Blue-Green

Two identical environments exist simultaneously — "blue" (current production) and "green" (new
version). Traffic is switched from blue to green at the load balancer level after the green
environment passes health checks.

- **Downtime:** none — the switch is instantaneous at the load balancer
- **Rollback:** switch traffic back to blue — instantaneous
- **Trade off:** requires double the infrastructure running simultaneously

---

## Security Strategy

### Principle of Least Privilege

Every component in the system has exactly the permissions it needs to do its job, and no more.

- The CI pipeline workflow declares `permissions: contents: read` — it cannot write to the
  repository, cannot manage secrets, cannot create releases
- The deploy SSH key is a dedicated key created only for this deployment — it is not a personal
  SSH key, it is not reused across projects
- The EC2 instance runs only the services it needs — no unnecessary packages, no open ports beyond
  what the application requires

### Network Security

- Port 22 (SSH) is required to be open for the CI/CD pipeline to connect. On GitHub-hosted
  runners this means allowing all IPs, since runner IPs are dynamic. This is a known, documented
  trade-off mitigated by key-only authentication.
- Application ports are open only for the ports the application serves (8080 in this demo).
- In production, the application should not be directly exposed on a raw port — it should sit
  behind a reverse proxy (nginx or Caddy) that handles TLS termination, rate limiting, and
  request filtering.

### TLS / HTTPS

All production traffic must be encrypted in transit. A reverse proxy (nginx or Caddy) terminates
TLS using a certificate from Let's Encrypt (free, automatic renewal). The application container
itself speaks plain HTTP to the proxy on the local network interface — never to the public
internet unencrypted.

### Image Security

- Base images are pinned to specific versions, not `latest`
- Dependencies are pinned to exact versions
- The container runs as a non-root user
- In a mature pipeline, image scanning is added as a CI stage between build
  and test to catch known vulnerabilities in base image layers and dependencies before they reach
  production

---

## Traffic Handling

Traffic handling is the full path a request travels from a user's browser to the application
container and back. In a production system this path is never a direct browser-to-container
connection — it passes through a series of infrastructure layers, each with a specific
responsibility. Understanding and designing this path is a core part of the deployment strategy.

### The Full Request Path (Production)

```
User's browser
      │  HTTPS (443)
      ▼
  DNS (Route 53 / Cloudflare)
  Resolves domain name → Load Balancer IP
      │
      ▼
  Load Balancer (AWS ALB)
  Distributes traffic across healthy instances
  Terminates TLS (HTTPS → HTTP internally)
      │  HTTP (80 internally)
      ▼
  Reverse Proxy (nginx / Caddy) — on each EC2 instance
  Handles request routing, rate limiting, security headers
      │  HTTP (8080 internally)
      ▼
  Application Container (Flask / Express)
  Business logic — produces the response
      │
      ▼
  Response travels back up the same path
```

### Layer 1 — DNS

**What it does:** Translates a human-readable domain name (`app.example.com`) into an IP address.
Users never interact with raw IP addresses in production.

### Layer 2 — Load Balancer

**What it does:** Distributes incoming requests across multiple instances of the application,
ensuring no single instance is overwhelmed. Continuously health-checks each instance and removes
unhealthy ones from the pool automatically, without human intervention. Enables zero-downtime
deployments by draining traffic from one instance before it is taken offline.

**How the ALB health check works with the deployment:**

During deployment, the ALB continuously polls `/health` on each instance. When a new
container is starting up, its health check initially returns unhealthy (503) — the ALB keeps the
instance out of the pool. Once the application is ready and `/health` returns 200 consistently,
the ALB adds it back. Traffic is never routed to an instance that is not ready.

**Cost note:** AWS ALB costs approximately $16–20/month minimum.For low-traffic service, a single EC2 instance with a reverse proxy is the cost-appropriate
alternative.

### Layer 3 — Reverse Proxy

**What it does:** Sits on the EC2 instance between the internet (or load balancer) and the
application container. Handles TLS termination, request routing, security headers, rate limiting,
gzip compression, and static file serving. The application container speaks plain HTTP to the
proxy on the local network — it never handles TLS or raw internet traffic directly.

**Tools:** nginx (standard, maximum control)

### Layer 4 — TLS / HTTPS

**What it does:** Encrypts all traffic between the user's browser and the server. Without TLS,
all data including any credentials or session tokens — travels in plain text and can be intercepted.
TLS is not optional for any production service.

### Layer 5 — CDN (Content Delivery Network)

**What it does:** Caches static assets (images, CSS, JavaScript) at edge locations geographically
close to users, reducing latency and offloading traffic from the origin server.

**Tools:** AWS CloudFront (with ALB/EC2), Cloudflare (simpler, free tier)

---

## Secrets Management

Secrets are credentials, tokens, keys, and any other value that grants access to a system. They
are the most sensitive artefacts in a software system and require specific handling:

### Rules Without Exception

- **Never commit a secret to source control.** Not in a `.env` file, not in a comment, not in a
  commit that is "immediately reverted." Once a secret is in git history, it must be considered
  compromised and rotated.
- **Never log a secret.** Pipeline logs, application logs, and error messages must never contain
  secret values. GitHub Actions automatically redacts registered secrets from logs, but this is a
  safety net, not a substitute for care.
- **Never share secrets between environments.** Staging and production have separate credentials.
  Compromising staging credentials does not compromise production.
- **Rotate secrets periodically.** SSH keys and tokens should be replaced on a regular schedule
  and immediately if there is any suspicion of compromise.

### Where Secrets Live

Secrets are stored in the CI/CD platform's encrypted secret store (GitHub Actions repository
secrets). They are injected into pipeline runs as environment variables at runtime and are never
written to disk on the runner.

On the deployment target, secrets the application needs at runtime are passed via environment
variables defined in Docker Compose, sourced from a `.env` file that exists on the server but
never in the repository.

---

## Observability and Health Checks

### Health Check Endpoint

Every service exposes a `/health` endpoint that returns a 200 response when the application is
ready to serve traffic. This endpoint is used by:

- Docker's `HEALTHCHECK` instruction — `docker ps` reports `healthy` or `unhealthy`
- The CD pipeline's post-deploy verification step — the pipeline curls `/health` after deployment
  and fails if it does not return 200
- Load balancers and orchestrators (in a multi-instance setup) — to determine which instances
  should receive traffic

The `/health` endpoint must respond quickly and must not perform heavy work. It should check
that the application process is alive and can accept connections, not that every downstream
dependency is healthy (that is a separate, more expensive check called a "readiness probe").

### Logging

Application logs are written to stdout and stderr — never to files on disk. This is a Docker and
twelve-factor application convention: the container runtime collects stdout and makes it available
via `docker logs`. In a mature system, a log aggregation service like AWS CloudWatch collects logs from all instances and makes them searchable.

### Monitoring and Alerting

In a production system:
- **Metrics** (request rate, error rate, latency, container CPU/memory) are collected by a metrics
  system (Prometheus, Datadog, CloudWatch)
- **Alerts** are configured to notify the on-call engineer when error rates exceed a threshold or
  when health checks fail
- **Dashboards** give the team visibility into the system's behaviour over time

---

## Rollback Strategy

Every deployment must have a defined rollback path before it is executed.

### Image-Tag-Based Rollback

Because every image is tagged with the Git commit SHA at build time, rolling back is
straightforward: re-deploy the previous known-good image tag. The pipeline does not need to
rebuild anything — the image already exists in the registry.

Rollback procedure:
1. Identify the last known-good commit SHA from the pipeline run history or `git log`
2. On the server, update the image tag in `compose.yml` to the previous SHA (or pass it as an
   environment variable)
3. Run `docker compose pull && docker compose up -d --force-recreate`
4. Verify the health check passes
5. Investigate the bad deployment on a branch; fix and re-deploy through the normal pipeline

### Automated Rollback

In a mature pipeline, the post-deploy health check failure triggers an automatic rollback:
if `curl /health` does not return 200 within a timeout, the pipeline immediately re-deploys the
previous image tag and fails the pipeline run, notifying the team. The bad version never stays
live for more than the health check timeout.

---

## Role of Docker and Docker Compose

**Docker** is the unit of deployment. It packages the application with its exact runtime,
dependencies, and configuration into a portable, reproducible image. The same image runs
identically in every environment. Docker eliminates environment drift — the "works on my machine"
class of problems — by making the environment part of the artifact.

**Docker Compose** is the service definition layer. It defines how one or more containers should
run together: which image, which ports, which environment variables, which volumes, which networks,
and what restart policy. For a single-service application it may seem like overhead, but it is the
correct tool because:

- The service configuration is a checked-in, version-controlled file, not a memorised command
- The same Compose file is what developers run locally and what the pipeline executes on the
  server — there is no separate "prod run command" to maintain
- When the service grows (add a database, add a reverse proxy), Compose scales to it naturally
  without changing the deployment mechanism

---