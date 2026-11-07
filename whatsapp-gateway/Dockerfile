FROM node:22-alpine

RUN apk add --no-cache git

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY src ./src

ENV GATEWAY_AUTH_DIR=/app/auth \
    GATEWAY_HOST=0.0.0.0 \
    GATEWAY_PORT=3100
RUN mkdir -p /app/auth && chown node:node /app/auth
USER node

CMD ["node", "src/index.js"]
