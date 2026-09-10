# LabTutor frontend (Next.js)
FROM node:22-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY frontend/package.json ./

RUN addgroup -g 10002 labtutor && adduser -D -u 10002 -G labtutor labtutor \
    && chown -R labtutor:labtutor /app
USER labtutor

EXPOSE 3000
CMD ["npm", "run", "start"]
