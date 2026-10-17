# =========================================================
# ROCKIB AI — FRONTEND DOCKERFILE (WITH NGINX)
# =========================================================

# Stage 1: Build Stage (Vite + React)
FROM node:20-alpine AS build

WORKDIR /app

# Copy package files first for caching
COPY package*.json ./

# Install npm dependencies
RUN npm ci

# Copy the rest of the frontend source
COPY . .

# Build the SPA
RUN npm run build

# Stage 2: Runtime Stage (Nginx Web Server & Reverse Proxy)
FROM nginx:1.25-alpine

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy build files from Stage 1 to Nginx default HTML directory
COPY --from=build /app/dist /usr/share/nginx/html

# Expose default HTTP port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
