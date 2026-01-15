# Use Python 3.11 as the base image
FROM python:3.11-slim

# 1. Install system dependencies required for Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Google Chrome (Stable)
# Note: We download the signing key and add the repository to install the latest stable version
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# 3. Set up the Python environment
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# 4. Command to run the application
# We use the shell form to ensure the $PORT variable is expanded correctly by Render
CMD python main.py