FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# CPU-only PyTorch keeps the image small; the forecaster does not need a GPU
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.2.0" \
 && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000 8501
CMD ["uvicorn", "mock_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
