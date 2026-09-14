FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN mkdir -p /app/data/uploads
ENV PYTHONUNBUFFERED=1
EXPOSE 8001
CMD ["sh","-c","uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
