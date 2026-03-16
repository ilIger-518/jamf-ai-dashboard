# ── Stage 1: generate api.html from Documentation.md ─────────────────────────
FROM python:3.12-alpine AS builder

WORKDIR /build

# Copy the docs-static source (build context is the workspace root)
COPY docs-static/ ./docs-static/
# Copy the markdown source that drives auto-generation
COPY Documentation.md ./

# Run the generator — outputs docs-static/site/api.html
RUN python docs-static/build.py

# ── Stage 2: serve the static site via nginx ──────────────────────────────────
FROM nginx:1.27-alpine

# Copy the full site directory (includes hand-crafted index.html + generated api.html)
COPY --from=builder /build/docs-static/site/ /usr/share/nginx/html/
# Also expose the full markdown handbook so static docs include complete content.
COPY --from=builder /build/Documentation.md /usr/share/nginx/html/Documentation.md

EXPOSE 80
