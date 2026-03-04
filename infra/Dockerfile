# =============================================================================
# AZALPLUS - Dockerfile Production
# =============================================================================

FROM python:3.12-slim AS base

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# =============================================================================
# Stage: Dependencies
# =============================================================================
FROM base AS dependencies

# Installer les dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copier requirements et installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage: Production
# =============================================================================
FROM base AS production

# Installer runtime dependencies seulement
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copier les packages Python installés
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Créer utilisateur non-root
RUN groupadd -r azalplus && useradd -r -g azalplus azalplus

# Créer répertoires nécessaires
RUN mkdir -p /app/data /app/logs /app/static && \
    chown -R azalplus:azalplus /app

# Copier le code
COPY --chown=azalplus:azalplus . .

# Basculer vers utilisateur non-root
USER azalplus

# Port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Commande de démarrage
CMD ["uvicorn", "moteur.core:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
