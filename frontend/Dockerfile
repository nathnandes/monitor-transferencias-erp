
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_TIMEZONE=America/Sao_Paulo
ENV VITE_API_URL="" VITE_TIMEZONE=$VITE_TIMEZONE
RUN npx vite build

FROM nginx:1.29-alpine
COPY nginx/locations.conf nginx/http.conf nginx/https.conf /etc/nginx/erp/
COPY nginx/http.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 nginx/40-tls.sh /docker-entrypoint.d/40-tls.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80 443
