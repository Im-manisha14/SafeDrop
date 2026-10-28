# SafeDrop — Secure File Sharing Platform

A full-stack internship/portfolio project for authenticated file uploads and time-limited sharing. Stack: React + Vite, Flask REST API, PostgreSQL, JWT, Docker Compose, Pytest, and Nginx.

## Features
- Register/login with hashed passwords and JWT authentication.
- Upload files with extension, size, and filename validation.
- Users can list and delete only their own files.
- Create revocable, expiring share links; public download endpoint checks expiration.
- Audit events for uploads, downloads, share creation/revocation, and rejected access.
- PostgreSQL database and persistent upload volume through Docker Compose.
- API tests and a production frontend container served by Nginx.

> Security note: This is a learning project, not a security certification. Before production use, add HTTPS, managed secrets, malware scanning, rate limiting, backups, monitoring, and a formal security review.

## Run with Docker (recommended)
1. Install Docker Desktop and start it.
2. Copy `.env.example` to `.env` and replace `JWT_SECRET_KEY` and `SHARE_TOKEN_SECRET` with long random values.
3. From this directory run:
   ```bash
   docker compose up --build
   ```
4. Open http://localhost:8080. API health: http://localhost:5000/api/health

Default local ports: frontend `8080`, API `5000`, PostgreSQL `5432`. Change values in `.env` if needed. The included defaults are for local development only.

## Run without Docker
### Backend
```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# Set DATABASE_URL, JWT_SECRET_KEY, SHARE_TOKEN_SECRET, UPLOAD_FOLDER in your environment.
flask --app run.py run --debug
```
If PostgreSQL is not available locally, for development you may set `DATABASE_URL=sqlite:///safedrop.db`.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Vite proxies `/api` requests to `http://localhost:5000`.

## Run tests
```bash
cd backend
pip install -r requirements.txt
pytest -q
```
Tests use a temporary SQLite database and temporary upload folder.

## Cloud deployment outline
Deploy the API container and frontend container to a container platform (for example, Render, Railway, Azure Container Apps, AWS App Runner, or Google Cloud Run) and use a managed PostgreSQL service. Configure the environment variables from `.env.example` in the provider dashboard, mount durable object/file storage for uploads, set `FRONTEND_ORIGIN` to the deployed frontend URL, enable HTTPS, and never use the sample secrets. Cloud provider setup is intentionally not performed automatically by this repository.

## API overview
- `POST /api/auth/register` — `{ "email": "...", "password": "..." }`
- `POST /api/auth/login` — returns a JWT
- `GET /api/files` — list current user's files (Bearer token)
- `POST /api/files` — multipart upload field `file` (Bearer token)
- `DELETE /api/files/<id>` — delete owned file (Bearer token)
- `POST /api/files/<id>/shares` — `{ "expires_in_hours": 24 }` (Bearer token)
- `GET /api/share/<token>` — public download, only while link is active
- `DELETE /api/shares/<id>` — revoke a share (Bearer token)
- `GET /api/audit` — recent current-user audit events (Bearer token)

## Important configuration
See `.env.example`. Never commit `.env`, uploaded files, database credentials, or production secrets.
