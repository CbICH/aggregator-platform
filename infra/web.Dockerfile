FROM node:22.12.0-alpine AS build
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM nginx:1.28.0-alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

