FROM node:26.7.0-bookworm-slim@sha256:cd565714d4da3e84bfd341e31448f81d47c6362198f152345297c9c1154e6341 AS build

WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json dashboard/tsconfig.json dashboard/index.html /app/
RUN npm ci
COPY dashboard/src /app/src
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM busybox:1.37.0-uclibc@sha256:8d7b1636e974e0adfd8d945955fca609304f0a56c18799dfd032d6e661382d84

COPY --from=build --chown=10002:10002 /app/dist /www
USER 10002:10002
EXPOSE 5173
CMD ["httpd", "-f", "-p", "5173", "-h", "/www"]
