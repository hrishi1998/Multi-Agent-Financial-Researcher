FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home appuser

COPY . .
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

CMD streamlit run app.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.headless true
