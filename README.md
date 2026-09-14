

## Local run

1. Start the API: `cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn main:app --reload --port 8001`
2. In a second terminal start the UI: `cd frontend && npm install && npm run dev`
3. Open `http://localhost:5173/pitch`.
4. Demo student: `student@demo.com` / `demo123`.
5. Demo TPO: `tpo@demo.com` / `demo123`.
6. Resume demo: use `demo/sample-resume.txt`; optionally paste `demo/sample-job-description.txt`.
