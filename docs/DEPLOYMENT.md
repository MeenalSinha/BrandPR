# BrandPR Deployment Guide (Render & Railway)

This guide provides step-by-step instructions to deploy the **BrandPR Full-Stack Platform** (PostgreSQL + FastAPI Backend + Next.js Frontend) to **Render** or **Railway**.

---

## Architecture Overview

```
                      ┌────────────────────────────┐
                      │    Next.js 15 Frontend     │
                      │  (Render / Railway / Vercel│
                      └─────────────┬──────────────┘
                                    │ Internal / Public HTTP
                                    ▼
                      ┌────────────────────────────┐
                      │    FastAPI Python API      │
                      │   (Uvicorn + Alembic)      │
                      └──────┬──────────────┬──────┘
                             │              │
              SQLAlchemy /   │              │ Persistent Disk
              Psycopg 3      ▼              ▼
           ┌──────────────────────┐   ┌───────────────────────────┐
           │ Managed PostgreSQL   │   │ Storage Directory         │
           │ (Render/Railway PG)  │   │ (/data/storage for PDFs)  │
           └──────────────────────┘   └───────────────────────────┘
```

---

## Option 1: Deploy on Render (Recommended)

Render offers managed PostgreSQL, persistent disks, and native support for Python and Node.js.

### Method A: 1-Click Blueprint (Fastest)

1. **Push your repository** to GitHub (or GitLab).
2. Go to the [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** in the top navigation and select **Blueprint**.
4. Connect your GitHub repository (`BrandPR`).
5. Render will detect the included `render.yaml` file and automatically configure:
   * **`brandpr-db`**: Managed PostgreSQL database.
   * **`brandpr-backend`**: Python web service with automatic Alembic migrations and persistent disk.
   * **`brandpr-frontend`**: Node.js web service for Next.js.
6. Click **Apply**.
7. Once deployed, update `CORS_ORIGINS` in the backend service to match your actual frontend URL (e.g., `https://brandpr-frontend.onrender.com`).

---

### Method B: Manual Render Setup (Step-by-Step)

If you prefer to configure services manually in Render:

#### Step 1: Create the Managed Database
1. In Render Dashboard, click **New +** → **PostgreSQL**.
2. **Name**: `brandpr-db`
3. **Database**: `brandpr`
4. **User**: `brandpr`
5. Click **Create Database**.
6. Copy the **Internal Database URL** (for backend communication) and **External Database URL**.

#### Step 2: Deploy the FastAPI Backend
1. Click **New +** → **Web Service**.
2. Connect your repository.
3. Configure the service:
   * **Name**: `brandpr-backend`
   * **Root Directory**: `backend`
   * **Runtime**: `Python`
   * **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   * **Start Command**: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add **Environment Variables**:
   * `APP_ENV`: `production`
   * `DATABASE_URL`: *(Select "Add from Database" → `brandpr-db` → Internal Connection String)*
   * `STORAGE_DIR`: `/data/storage`
   * `CORS_ORIGINS`: `https://<YOUR-FRONTEND-NAME>.onrender.com`
   * `DOCS_ENABLED`: `true`
5. (Optional, for persistent files) Under **Disks**, click **Add Disk**:
   * **Name**: `storage`
   * **Mount Path**: `/data/storage`
   * **Size**: `1 GB`
6. Click **Create Web Service**.

#### Step 3: Deploy the Next.js Frontend
1. Click **New +** → **Web Service**.
2. Connect the same repository.
3. Configure the service:
   * **Name**: `brandpr-frontend`
   * **Root Directory**: `frontend`
   * **Runtime**: `Node`
   * **Build Command**: `npm install && npm run build`
   * **Start Command**: `npm start`
4. Add **Environment Variables**:
   * `NODE_ENV`: `production`
   * `BACKEND_URL`: `https://brandpr-backend.onrender.com` *(use your backend's live URL)*
5. Click **Create Web Service**.

---

## Option 2: Deploy on Railway

Railway allows you to deploy all three components within a single canvas project.

### Step 1: Create a Railway Project
1. Log in to [Railway.app](https://railway.app/).
2. Click **New Project** → **Provision PostgreSQL**.
3. Railway immediately creates a managed PostgreSQL instance with a `DATABASE_URL`.

### Step 2: Add Backend Service
1. In the same project canvas, click **+ New** → **GitHub Repo** → select `BrandPR`.
2. Click on the newly created service and open **Settings**:
   * **Service Name**: `brandpr-backend`
   * **Root Directory**: `/backend`
   * **Build Command**: `pip install -r requirements.txt`
   * **Start Command**: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. In **Variables**, add:
   * `APP_ENV`: `production`
   * `DATABASE_URL`: `${{Postgres.DATABASE_URL}}` *(Railway variable reference)*
   * `STORAGE_DIR`: `/tmp/storage` *(or mount a Railway volume at `/data/storage`)*
   * `CORS_ORIGINS`: `https://${{RAILWAY_PUBLIC_DOMAIN}}` *(or your frontend URL)*
   * `DOCS_ENABLED`: `true`
4. In **Settings** → **Networking**, click **Generate Domain** (gives you a public URL like `https://brandpr-backend-production.up.railway.app`).

### Step 3: Add Frontend Service
1. Click **+ New** → **GitHub Repo** → select `BrandPR` again.
2. In **Settings**:
   * **Service Name**: `brandpr-frontend`
   * **Root Directory**: `/frontend`
   * **Build Command**: `npm install && npm run build`
   * **Start Command**: `npm start`
3. In **Variables**:
   * `NODE_ENV`: `production`
   * `BACKEND_URL`: `https://${{brandpr-backend.RAILWAY_PUBLIC_DOMAIN}}` *(or your generated backend URL)*
4. In **Settings** → **Networking**, click **Generate Domain** (e.g. `https://brandpr-frontend-production.up.railway.app`).
5. Go back to `brandpr-backend` and update `CORS_ORIGINS` to include this frontend URL.

---

## Verifying the Live Deployment

Once both services are running:

1. **Backend Health Check**:
   ```bash
   curl -s https://<YOUR-BACKEND-URL>/api/health
   # Expected response: {"status":"ok","environment":"production"}
   ```

2. **Database Connectivity**:
   ```bash
   curl -s https://<YOUR-BACKEND-URL>/api/health/db
   # Expected response: {"status":"ok","database":"connected"}
   ```

3. **Frontend Application**:
   Open `https://<YOUR-FRONTEND-URL>` in your browser:
   * Verify the sidebar indicator shows `API online`.
   * Try creating a brand, uploading a source PDF, creating an approved fact, and running a campaign audit.
