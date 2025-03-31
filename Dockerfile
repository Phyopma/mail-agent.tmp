FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs credentials

# Set environment variables
ENV PYTHONPATH=/app
ENV MAIL_AGENT_LOG_LEVEL=INFO

# Run the application
ENTRYPOINT ["python", "-m", "mail_agent.main", "--process"]
