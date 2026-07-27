# Sử dụng Python 3.12 slim cho hiệu suất và dung lượng tối ưu
FROM python:3.12-slim

WORKDIR /app

# Khắc phục lỗi thiếu C-compiler cho thư viện asyncpg và chroma
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements trước để tận dụng Docker Cache
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn Backend
COPY . .

EXPOSE 8000

# Chạy ứng dụng FastAPI bằng Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
