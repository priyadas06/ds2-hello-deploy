# DS2 Hello World — Automated CI/CD Deployment to AWS EC2

A proof-of-concept demonstrating a production-style CI/CD deployment pipeline — containerization,
automated build/test, and SSH-based continuous deployment — using a minimal Flask "Hello World"
service as the demonstration payload. The application itself is intentionally trivial; the focus of
this project is the deployment strategy and automation around it.

For a detailed write-up of the branching model, CI/CD concepts, the role of Docker/Compose, and
security trade-offs, see **[DEPLOYMENT_STRATEGY.md](DEPLOYMENT_STRATEGY.md)**.

## Git Repository

```
<GIT_REPO_URL>
```

## Live Demo

```
http://<EC2_ELASTIC_IP>:8080
```

## For Reviewers: How to Run and Verify This Project

There are three ways to verify this project, from quickest to most hands-on.

### Option 1 — Just visit the live URL

The app is deployed and running continuously. No setup needed:

```bash
curl http://<EC2_ELASTIC_IP>:8080
# → "Hello World from DS2!"

curl http://<EC2_ELASTIC_IP>:8080/health
# → {"status": "ok"}
```

Or open `http://<EC2_ELASTIC_IP>:8080` in a browser.

### Option 2 — Trigger the CI/CD pipeline yourself

This is the recommended way to actually see the automation work, not just its end result.

1. Clone the repo:
   ```bash
   git clone <GIT_REPO_URL>
   cd <REPO_NAME>
   ```
2. Make a trivial, visible change — e.g. edit the string returned in `app/app.py`:
   ```python
   return "Hello World from DS2! (verified by reviewer)"
   ```
3. Commit and push to `main`:
   ```bash
   git add .
   git commit -m "Verify pipeline"
   git push origin main
   ```
   (If branch protection is enabled on the repo, open a pull request instead and merge it — see
   [DEPLOYMENT_STRATEGY.md](DEPLOYMENT_STRATEGY.md).)
4. Open the **Actions** tab on GitHub and watch the `build` job run (build the image, start the
   container, `curl` it) followed by the `deploy` job (SCP the code to EC2, SSH in, recreate the
   container via Docker Compose).
5. Once both jobs are green, re-run the `curl` from Option 1 — the response will reflect your
   change, confirming the full pipeline executed end to end.

### Option 3 — Run it locally, no AWS account needed

If you just want to confirm the application and Docker setup work, without touching the live
infrastructure at all:

```bash
git clone <GIT_REPO_URL>
cd <REPO_NAME>
docker compose up --build
```
Then in another terminal:
```bash
curl http://localhost:8080
curl http://localhost:8080/health
```
Stop it with `docker compose down`.

## Table of Contents

- [For Reviewers: How to Run and Verify This Project](#for-reviewers-how-to-run-and-verify-this-project)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [AWS EC2 Setup](#aws-ec2-setup)
- [Secrets and Environment Variables](#secrets-and-environment-variables)
- [Running Locally](#running-locally)
- [CI/CD Pipeline](#cicd-pipeline)
- [Troubleshooting](#troubleshooting)
- [Bonus Features](#bonus-features)

## Tech Stack

| Layer | Choice |
|---|---|
| Application | Python 3.12, Flask |
| Containerization | Docker, Docker Compose |
| CI/CD platform | GitHub Actions (managed/hosted runners) |
| Deployment target | AWS EC2 (Ubuntu, free-tier eligible) |
| Deployment mechanism | SCP (file sync) + SSH (remote `docker compose` commands) |
| Secrets management | GitHub Actions encrypted repository secrets |

## Project Structure

```
.
ds2-hello-deploy/
├── .github/
│   └── workflows/
│       └── deploy.yml
├── app/
│   └── app.py
├── .dockerignore
├── compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
└── DEPLOYMENT_STRATEGY.md
```

## AWS EC2 Setup

1. Launch a `t2.micro`/`t3.micro` instance (Ubuntu 22.04/24.04, free-tier eligible).
2. Create a dedicated key pair for deployment (not a personal key) — the private key becomes the
   `SERVER_SSH_KEY` secret.
3. Security group inbound rules:
   - **22 (SSH)** — open to `0.0.0.0/0`, since GitHub-hosted runners don't have a fixed IP
     (see [Security Considerations](DEPLOYMENT_STRATEGY.md#security-considerations-and-trade-offs)
     in the strategy doc)
   - **8080 (app)** — open to `0.0.0.0/0`, so the app is publicly reachable
4. Allocate an **Elastic IP** and associate it with the instance, so the deploy target address
   never changes between stop/start cycles.
5. Install Docker and the Compose plugin:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y docker.io docker-compose-plugin
   sudo usermod -aG docker ubuntu
   ```
6. Create the deploy target directory:
   ```bash
   mkdir -p ~/ds2-hello-deploy
   ```

## Secrets and Environment Variables

Stored only in **GitHub → Settings → Secrets and variables → Actions**, never in source:

| Secret | Purpose |
|---|---|
| `SERVER_IP` | EC2 Elastic IP, used by the deploy job to connect |
| `SERVER_USER` | SSH user on the instance (`ubuntu`) |
| `SERVER_SSH_KEY` | Private key matching the public key authorized on the instance |

Application configuration uses environment variables rather than hardcoded values — the app reads
its listening port from `PORT` (set in `compose.yml`), defaulting to `8080` only if unset.

## Running Locally

```bash
# Build and run the raw Docker image
docker build -t ds2-hello .
docker run -d -p 8080:8080 --name test-container ds2-hello
curl http://localhost:8080
curl http://localhost:8080/health
docker logs test-container
docker stop test-container && docker rm test-container

# Or via Docker Compose (matches what the deploy stage actually runs)
docker compose up --build -d
curl http://localhost:8080
docker compose logs
docker compose down
```

## CI/CD Pipeline

Defined in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml), triggered on push to
`main`:

**`build` job**
1. Checkout code
2. Set up Docker Buildx
3. Build the Docker image
4. Run the container and `curl` it to validate the expected response (test stage)
5. Tear down the test container

**`deploy` job** (runs only if `build` succeeds)
1. Checkout code
2. `scp` the repository contents to the EC2 instance
3. SSH into the instance and run:
   ```bash
   cd ~/ds2-hello-deploy
   docker compose down || true
   docker compose up -d --build
   ```

This recreates the running container with the latest code automatically, with no manual step
between merge and live deployment.

## Troubleshooting

| Symptom | Where to look |
|---|---|
| `build` job fails | Actions log for that step — usually a Dockerfile or dependency issue |
| `curl -f` fails during the test stage | Container may not have started in time, or the app crashed — check `docker logs` in the workflow run |
| `scp`/`ssh` step fails | Security group blocking port 22, or `SERVER_SSH_KEY` pasted incorrectly (must include the `BEGIN`/`END` lines) |
| Deploy job succeeds but the app isn't reachable | Security group missing the 8080 inbound rule, or a port mismatch between `compose.yml` and the app |
| Need to inspect the live container | `ssh ubuntu@<EC2_IP> "docker compose -f ~/ds2-hello-deploy/compose.yml ps"` and `docker compose logs` |

General monitoring during a deploy:
- GitHub **Actions** tab — real-time pipeline logs for both jobs
- On the server: `docker compose logs -f` and `docker ps`
- From outside: `curl -v http://<EC2_IP>:8080`

## Bonus Features

- [x] Health check endpoint (`/health`) in the application
- [ ] Docker `HEALTHCHECK` directive wired to `/health`
- [x] Configuration via environment variables (`PORT`)
- [ ] Rollback strategy (redeploy a previous SHA-tagged image)
- [ ] Separate staging/production environments with a manual approval gate
- [ ] Basic monitoring/logging beyond `docker compose logs`
