# Use Python 3.11 slim image based on Debian Bookworm
# This matches Raspberry Pi OS and runs natively on Apple Silicon (ARM64)
FROM python:3.11-slim-bookworm

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Keep container running
CMD ["sleep", "infinity"]
