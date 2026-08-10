FROM node:20.20.2-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS build

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
