# Qisas API

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Fresh databases get **admin only** plus category dropdowns (no demo stories or mock users).

- Admin: `0712345678` / `admin1234` (override with `ADMIN_PHONE` / `ADMIN_PASSWORD`)

## Railway

1. New project → Deploy from this repo. Root uses `railway.toml` (`backend/Dockerfile`).
2. Add a **PostgreSQL** plugin. Railway sets `DATABASE_URL`.
3. Variables:

```
SECRET_KEY=<long-random>
CORS_ORIGINS=https://your-frontend.example
ADMIN_PHONE=0712345678
ADMIN_PASSWORD=<strong-password>
ADMIN_NAME=Admin
```

4. Optional volume: set `DATA_DIR=/data` and mount a volume at `/data` for uploads.
5. Point the frontend `VITE_API_URL` at the Railway public URL (no trailing slash).
