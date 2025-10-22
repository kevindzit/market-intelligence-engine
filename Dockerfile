# Dockerfile for Trading Bot - RTX 4090/5090 Optimized
# Works identically on local Windows, cloud GPU servers (RunPod, Vast.ai, Lambda Labs)

FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    postgresql-client \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Set working directory
WORKDIR /app

# Copy requirements first (for layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs outputs chroma_db_news

# Environment variables (override with docker run -e)
ENV POSTGRES_HOST=localhost
ENV POSTGRES_PORT=54594
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
ENV OLLAMA_HOST=http://localhost:11434

# Expose Ollama port (optional, for debugging)
EXPOSE 11434

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:11434/api/tags || exit 1

# Default command: Start Ollama and run orchestrator
CMD ["bash", "-c", "ollama serve & sleep 5 && python3 orchestrator.py"]
