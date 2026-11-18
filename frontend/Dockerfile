FROM node:24-bookworm-slim
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend .
COPY proto /app/proto
RUN npm run generate
CMD ["npm", "run", "dev"]
