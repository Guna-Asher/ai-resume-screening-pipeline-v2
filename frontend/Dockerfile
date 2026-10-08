# --- deps: reproducible install from the lockfile (never needs host Node) ---
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- dev: used by docker compose (Vite dev server; sources are bind-mounted) ---
FROM deps AS dev
ENV NODE_ENV=development
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# --- build: production bundle ---
FROM deps AS build
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
COPY . .
RUN npm run build

# --- prod: static files behind nginx (no Node, no source mounts) ---
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 3000
