# We use python:3.11-slim-bookworm to match the current RPi OS version.
# If you are on an Apple Silicon Mac, this will naturally run as ARM64 
# (same architecture as the Pi), making it incredibly fast.
FROM python:3.11-slim-bookworm

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies. 
# "build-essential" is often needed to compile python libraries (like numpy or GPIO wrappers)
# "curl" and "git" are standard dev tools.
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user (optional but recommended for security/best practice)
# VS Code handles the user mapping automatically if we stick to root, 
# but let's keep it simple for now and run as root inside the container 
# so you don't hit permission issues while learning.
WORKDIR /workspace