FROM node:24-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
# RUN npm install --frozen-lockfile --registry http://registry.safaricomet.net
RUN npm install ci --registry http://registry.safaricomet.net

COPY . ./
ARG VITE_ADMIN_API_URL=http://localhost:8002/api/v1
ENV VITE_ADMIN_API_URL=${VITE_ADMIN_API_URL}
RUN npm run build

FROM node:22-slim AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000 \
    NITRO_HOST=0.0.0.0 \
    NITRO_PORT=3000

COPY --from=build /app/.output/ ./.output/

EXPOSE 3000

CMD ["node", ".output/server/index.mjs"]
