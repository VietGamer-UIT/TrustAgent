# Sử dụng Node.js 20 Alpine siêu nhẹ
FROM node:20-alpine

WORKDIR /app

# Copy các file config dependency
COPY package.json package-lock.json* ./

# Cài đặt dependency
RUN npm install

# Copy toàn bộ mã nguồn Frontend
COPY . .

# Build ứng dụng cho Production
RUN npm run build

EXPOSE 3000

# Khởi động Next.js server
CMD ["npm", "start"]
