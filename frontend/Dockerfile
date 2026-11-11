FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY frontend ./frontend
RUN pip install --no-cache-dir ".[frontend]"

ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501
CMD ["streamlit", "run", "frontend/app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
