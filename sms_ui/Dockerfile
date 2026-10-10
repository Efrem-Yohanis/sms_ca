FROM node:22-bookworm-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
# RUN npm ci --no-audit --no-fund --verbose
ARG NPM_REGISTRY=http://registry.safaricomet.net
RUN npm ci --no-audit --no-fund --verbose --registry="${NPM_REGISTRY}"

COPY . ./
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ARG VITE_ADMIN_API_BASE_URL=http://localhost:8002
ENV VITE_ADMIN_API_BASE_URL=${VITE_ADMIN_API_BASE_URL}
RUN npm run build

FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/

EXPOSE 80
