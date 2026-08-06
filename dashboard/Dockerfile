FROM node:20.17.0-bookworm-slim

WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json dashboard/tsconfig.json dashboard/index.html /app/
RUN npm install
COPY dashboard/src /app/src
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build
RUN useradd --create-home --uid 10002 appuser
USER appuser
CMD ["npm", "run", "preview"]
