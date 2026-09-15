FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --default-timeout=2000 --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Expose ports for FastAPI and Streamlit
EXPOSE 8000
EXPOSE 8501

# The start command is handled by docker-compose
CMD ["bash"]
