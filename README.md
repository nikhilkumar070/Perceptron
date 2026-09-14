# Preceptron — Know what to improve. Know what to do next.

Placement intelligence platform turning readiness signals into a personalized action loop:
assessment, diagnosis, roadmap, practice, interview, and resume improvement.

## Local Run

1. **Start the API**:
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8001
   ```
2. **Start the UI** in a second terminal:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
3. Open `http://localhost:5173/pitch`.
4. **Demo Student**: `student@demo.com` / `demo123`.
5. **Demo TPO**: `tpo@demo.com` / `demo123`.
6. **Resume Demo**: use `demo/sample-resume.txt`; optionally paste `demo/sample-job-description.txt`.

---

## Migrating Local SQLite Database to Neon PostgreSQL

When you are ready to migrate your actual local SQLite database (`data/preceptron.db`) into your production Neon PostgreSQL database:

### 1. Set your Neon connection string

```bash
export DATABASE_URL="postgresql://<user>:<password>@<ep-xxxx>.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
```

### 2. Run a Dry Run first (Safe, inspects & reports without modifying Neon)

```bash
python backend/migrate_sqlite_to_neon.py --dry-run
```

This will:

- Check connection to Neon
- Read all rows from `data/preceptron.db`
- Display the exact counts of rows to be migrated across all tables

### 3. Run the Actual Migration

```bash
python backend/migrate_sqlite_to_neon.py
```

### What the Migration Tool Does:

- **Zero data loss & idempotent**: Uses `ON CONFLICT DO NOTHING` so re-running will not duplicate rows.
- **Preserves primary keys**: All UUIDs, timestamps, JSON payloads, and user relations are preserved.
- **Safe credentials**: Never prints raw passwords or secrets in logs; connection strings are masked.
- **Local DB untouched**: The local SQLite database is strictly read-only during migration.
- **Maintains sequences**: Verifies sequence consistency for future inserts.
