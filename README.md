# Hello World — Automated CI/CD Deployment to AWS EC2

This is a proof-of-concept demonstrating a production-style CI/CD deployment pipeline using a minimal
Flask "Hello World" service.

For the full architectural write-up — branching model, environment strategy, testing layers,
traffic handling, security and rollback strategies please check
**[DEPLOYMENT_STRATEGY.md](DEPLOYMENT_STRATEGY.md)**.

---

## Git Repository

```
https://github.com/priyadas06/ds2-hello-deploy
```

## Live Demo

```
http://13.49.121.54:8080
```

---

## Table of Contents

- [For Reviewers: How to Verify This Project](#for-reviewers-how-to-verify-this-project)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [AWS EC2 Setup](#aws-ec2-setup)
- [Secrets and Environment Variables](#secrets-and-environment-variables)
- [Running Locally](#running-locally)
- [CI/CD Pipeline](#cicd-pipeline)
- [Troubleshooting](#troubleshooting)
- [How the Hello World App Demonstrates the Deployment Strategy](#how-the-hello-world-app-demonstrates-the-deployment-strategy)
- [Known Limitations of the Demo](#known-limitations-of-the-demo)

---

## For Reviewers: How to Verify This Project

There are three different ways our app can be validated

### Option 1 — Direct access tp the live deployed system

No setup required. The app is deployed and running continuously:

```bash
curl http://13.49.121.54:8080
# → Hello World from team IT WORKS ON MY MACHINE!

curl http://13.49.121.54:8080/health
# → {"status": "ok"}
```

Or open `http://13.49.121.54:8080` in a browser.

### Option 2 — Trigger the CI/CD pipeline yourself (recommended)

This is the recommended path to see the full automation in action.

**Step 1: Clone the repository**

```bash
git clone https://github.com/priyadas06/ds2-hello-deploy
cd ds2-hello-deploy
```

**Step 2: Create a feature branch**

```bash
git checkout -b feature/reviewer-verification
```

**Step 3: Make a small but visible change**

Edit `app/app.py`, for example:

```python
return "Hello World is verified by <reviewer's_name>"
```

**Step 4: Push the branch and open a pull request**

```bash
git add .
git commit -m "Verify CI/CD pipeline"
git push origin feature/reviewer-verification
```

Go to the GitHub repo — you will see a prompt to open a pull request targeting `main`. Open it.

**Step 5: Observe CI behaviour on the pull request**

In the **Actions** tab, watch the pipeline run triggered by the PR:
- The `Build & Test` job runs automatically — image builds, container starts, both endpoints
  are curl-tested
- The `Deploy to EC2` job does **not** appear — it is explicitly blocked on PR events via an
  `if:` condition in the workflow file
- This is the PR-gated CI in action: unreviewed code never reaches the server

**Step 6: Merge the PR and observe CD**

Once `Build & Test` is green, merge the PR. The merge to `main` triggers a new pipeline run
where both jobs fire — `Build & Test` followed by `Deploy to EC2` — with no manual step.

**Step 7: Verify the live change**

```bash
curl http://13.49.121.54:8080
# → Hello World is verified by <reviewer's_name>
```

The response reflects your change, confirming the full pipeline executed end to end.

### Option 3 — Local execution only (no AWS account needed)

```bash
git clone https://github.com/priyadas06/ds2-hello-deploy
cd ds2-hello-deploy
docker compose up --build
```

In another terminal:

```bash
curl http://localhost:8080
curl http://localhost:8080/health
```

Stop with `docker compose down`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Application | Python 3.12, Flask 3.0.3 |
| Containerization | Docker, Docker Compose |
| CI/CD platform | GitHub Actions (managed hosted runners, `ubuntu-latest`) |
| Deployment target | AWS EC2 t2.micro (Ubuntu 24.04 LTS, free-tier eligible) |
| Deployment mechanism | SCP (file sync) + SSH (remote `docker compose` commands) |
| Secrets management | GitHub Actions encrypted repository secrets |

---

## Project Structure

```
ds2-hello-deploy/
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI/CD pipeline
├── app/
│   └── app.py                  # Flask application
├── .dockerignore               
├── compose.yml                 # Service definition
├── Dockerfile                  # Image build
├── requirements.txt            # Python dependencies
├── README.md
└── DEPLOYMENT_STRATEGY.md      # Our Deployment strategy write-up
```

---

## AWS EC2 Setup

1. Launch a `t2.micro` instance (Ubuntu 24.04 LTS, free-tier eligible).

2. Create a dedicated key pair for deployment only — not a personal SSH key. The private
   key becomes the `SERVER_SSH_KEY` secret. Never commit it to the repository.

3. Configure security group inbound rules:
   - **Port 22 (SSH)** — source `0.0.0.0/0`. Required because GitHub-hosted runners use
     dynamic IPs with no fixed range. Mitigated by key-only authentication.
   - **Port 8080 (application)** — source `0.0.0.0/0` so the app is publicly reachable.

4. Allocate an **Elastic IP** and associate it with the instance created above, so the deploy target
   address never changes between stop/start cycles.

5. Now SSH into the instance and Install Docker from Docker's official repository:

   ```bash
   sudo apt install -y ca-certificates curl gnupg
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   sudo chmod a+r /etc/apt/keyrings/docker.gpg
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
     https://download.docker.com/linux/ubuntu \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
     sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt update
   sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
   sudo usermod -aG docker ubuntu
   ```

   Log out and back in so the group membership takes effect, then verify:

   ```bash
   docker ps             # must work without sudo
   docker --version
   docker compose version
   ```

6. Then create the deploy target directory:

   ```bash
   mkdir -p ~/ds2-hello-deploy
   ```

---

## Secrets and Environment Variables

Secrets are stored in **GitHub → Settings → Secrets and variables → Actions** and never in source control or pipeline logs.

| Secret | Purpose |
|---|---|
| `SERVER_IP` | EC2 Elastic IP — the deploy job SSH/SCP target |
| `SERVER_USER` | SSH login user on the instance (`ubuntu`) |
| `SERVER_SSH_KEY` | Full contents of the `.pem` private key, including header and footer lines |

Application configuration uses environment variables rather than hardcoded values.
The app reads its listening port from the `PORT` environment variable, which is set
in `compose.yml`. This means the port can be changed at deploy time without touching
application code i.e. no hardcoded configuration in the container.

---

## Running the project locally first

### With raw Docker (tests the image in isolation)

```bash
# Build the image
docker build -t ds2-hello .

# Run the container
docker run -d -p 8080:8080 --name test-container ds2-hello

# Test both endpoints
curl http://localhost:8080
curl http://localhost:8080/health

# Inspect logs
docker logs test-container

# Tear down
docker stop test-container && docker rm test-container
```

### With Docker Compose

```bash
docker compose up --build -d

curl http://localhost:8080
curl http://localhost:8080/health

docker compose logs

docker compose down
```

Both methods must pass cleanly before trusting the CI pipeline, if it fails locally it
will also fail in CI for the same reason.

---

## CI/CD Pipeline

Defined in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml).

The pipeline has two separate triggers with two separate responsibilities — they must never
be collapsed into one:

**Trigger 1 — Pull Request opened against `main`:**
Runs `Build & Test` only. The `Deploy to EC2` job is explicitly blocked on PR events via
`if: github.event_name == 'push' && github.ref == 'refs/heads/main'`. Unreviewed,
unmerged code never reaches the server.

**Trigger 2 — Push to `main` (only reachable via an approved, merged PR):**
Runs `Build & Test` followed by `Deploy to EC2`.

### `Build & Test` job (runs on both triggers)

1. Checkout code
2. Set up Docker Buildx
3. Build the Docker image from the `Dockerfile`
4. Start the container and smoke test both endpoints:
   ```bash
   curl -f http://localhost:8080        
   curl -f http://localhost:8080/health # pipeline fails here if the app is not serving
   ```
5. Stop and remove the test container

### `Deploy to EC2` job (merge to `main` only — blocked on pull requests)

1. Checkout code
2. Copy repository contents to EC2 via `appleboy/scp-action`
3. SSH into the instance via `appleboy/ssh-action` and run:
   ```bash
   cd ~/ds2-hello-deploy
   docker compose down || true
   docker compose up -d --build
   sleep 2
   curl -f http://localhost:8080        || exit 1
   curl -f http://localhost:8080/health || exit 1
   ```
4. The post-deploy `curl` checks verify the app is actually serving before the pipeline
   reports success. If either check fails the job exits non-zero, the pipeline fails, and
   the deployment is flagged.
---

## Troubleshooting

| Symptom | Where to look |
|---|---|
| `Build & Test` fails at image build step | Check Actions log, usually a `Dockerfile` syntax error or missing dependency in `requirements.txt` |
| `curl -f` fails during smoke test in CI | App didn't start in time or crashed, add `docker logs test-container` before the curl step to diagnose |
| `scp-action` step fails | Port 22 is blocked in the security group, or `SERVER_SSH_KEY` pasted incorrectly (must include `-----BEGIN-----` / `-----END-----` lines, no extra whitespace) |
| `ssh-action` step fails | Same SSH key/port issues, also confirm `SERVER_USER` is `ubuntu` and `SERVER_IP` is the Elastic IP, not the instance's private IP |
| Deploy job shows green but app is not reachable from outside | Security group missing the port 8080 inbound rule, or port mismatch between `compose.yml` and `app.py` |
| Post-deploy `curl` fails (app not serving after deploy) | SSH in and check `docker compose logs` and `docker ps` for container state and startup errors |
| Inspect the live container directly | `ssh ubuntu@13.49.121.54 "docker compose -f ~/ds2-hello-deploy/compose.yml ps"` |

**General monitoring during a live deploy:**

```bash
# GitHub Actions tab — real-time logs for both jobs (in browser)

# On the EC2 instance
docker compose logs -f
docker ps

# From outside
curl -v http://13.49.121.54:8080
```

---

## How the Hello World App Demonstrates the Deployment Strategy

This Hello World application is the smallest possible payload that allows each element of our
strategy to be demonstrated with a real, live, verifiable system.

| Strategy element | What to observe to verify it |
|---|---|
| Protected `main`, PR-gated CI | Open a PR — watch `Build & Test` run in Actions; confirm `Deploy to EC2` job does not appear; confirm the PR cannot be merged until CI is green |
| CI blocks broken code | Introduce a deliberate syntax error on a branch; open a PR; confirm CI fails and the merge button stays disabled |
| CD triggers only on merge | Merge the PR; watch both jobs fire automatically in Actions with no manual step |
| Dual-trigger pipeline | Inspect `deploy.yml`, the `on:` block shows both `pull_request` and `push` triggers, the `if:` condition on the deploy job is visible in the file |
| SSH deploy to real infrastructure | See `docker ps` on EC2 before and after a merge, the container ID change proving it was stopped and recreated |
| Post-deploy verification | Check the `Deploy to EC2` job log, the final `curl -f` steps pass after a successful deploy and would fail the job if the app was not serving |
| Health check endpoint | `curl http://13.49.121.54:8080/health` returns `{"status": "ok"}` |
| Secrets management | See that `SERVER_IP`, `SERVER_USER`, `SERVER_SSH_KEY` listed in GitHub Secrets with values hidden, the `.pem` file is absent from the repository and from all commit history.

---

## Known Limitations of our Demo app

| Limitation | Production standard |
|---|---|
| Image rebuilt on the server (`--build`) rather than pulled from a registry | Build once in CI, push a SHA-tagged image to a container registry (Docker Hub), pull that exact tag at deploy time, this guarantees the tested artifact is identical to what runs in production |
| Single environment, no staging | Staging environment receiving every merge automatically, manual approval gate before production deploy |
| No TLS — app served on plain HTTP | Reverse proxy (nginx) with automatic Encrypt certificate, port 8080 removed from public security group |
| SSH port 22 open to all IPs | Restrict to known CI runner IP ranges, or route server access through a bastion host or VPN |
| Recreate deployment (brief downtime per deploy) | Blue-green deployment behind a load balancer for zero-downtime deploys |
| No image vulnerability scanning | Image scan can be added as a CI stage between build and test, pipeline fails on CRITICAL/HIGH findings |
| No centralised logging or monitoring | Log aggregation (AWS CloudWatch) and metrics (Datadog) with proper alerting and dashboards |
| Manual rollback only | Automated rollback triggered by post-deploy health check failure, previous SHA-tagged image re-deployed immediately |
| Single EC2 instance, no redundancy | Multiple instances behind an AWS ALB across availability zones |