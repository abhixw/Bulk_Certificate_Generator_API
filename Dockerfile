# Use the official Python 3.12 slim image as the base
FROM python:3.12-slim

# Set environment variables
# PYTHONDONTWRITEBYTECODE: Prevents Python from writing .pyc files to disk
# PYTHONUNBUFFERED: Prevents Python from buffering stdout and stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Add a default non-root user id
    UID=1000 \
    GID=1000

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
# gcc and python3-dev are sometimes needed for certain C-extensions
# We clean up the apt cache to keep the image small
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . /app/

# Generate the template at build time so the container always has it
RUN python scripts/generate_template.py

# Create a non-root user and give them ownership of the app directory.
# Running as a non-root user is a security best practice.
RUN groupadd -g "${GID}" pythonuser \
    && useradd --create-home --no-log-init -u "${UID}" -g "${GID}" pythonuser \
    && chown -R pythonuser:pythonuser /app

# Switch to the non-root user
USER pythonuser

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
