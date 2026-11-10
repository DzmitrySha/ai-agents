# syntax=docker/dockerfile:1
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend/ .
RUN npm run build

FROM nginx:alpine
# Резолвер для runtime-DNS берётся entrypoint'ом из /etc/resolv.conf
# (15-local-resolvers.envsh → NGINX_LOCAL_RESOLVERS), конфиг рендерится из шаблона.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx/frontend.conf.template /etc/nginx/templates/frontend.conf.template
RUN rm -f /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
