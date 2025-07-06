# Gunakan base image Python
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Salin file ke dalam container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (harus sama dengan yang kamu jalankan)
EXPOSE 5000

# Jalankan aplikasi
CMD ["python", "main.py"]
