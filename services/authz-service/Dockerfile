FROM python:3.12-slim

WORKDIR /app

# Copy requirements first for better caching
COPY authz-service/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY shared /app/shared

# Copy application code
COPY authz-service/ .

# Expose port (documentation only - not exposed in docker-compose for security)
EXPOSE 9000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
