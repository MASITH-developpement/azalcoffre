#!/bin/bash
# =============================================================================
# AZALPLUS - Chrome MCP Startup Script
# Démarre Xvfb et Chrome avec l'extension MCP pour l'automatisation
#
# SÉCURITÉ:
# - Chrome debug port uniquement sur 127.0.0.1
# - Mode incognito (pas de données persistantes)
# - Extensions/plugins désactivés
# - Firewall bloque l'accès externe au port 9222
# =============================================================================

set -e

LOG_FILE="/home/ubuntu/azalplus/logs/chrome-mcp.log"
DISPLAY_NUM=99
CHROME_DEBUG_PORT=9222

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Vérification de sécurité: s'assurer que le port n'est pas exposé
check_security() {
    # Vérifier que le port 9222 n'est pas accessible depuis l'extérieur
    if netstat -tlnp 2>/dev/null | grep ":$CHROME_DEBUG_PORT" | grep -v "127.0.0.1" > /dev/null; then
        log "ALERTE SÉCURITÉ: Port $CHROME_DEBUG_PORT exposé publiquement!"
        return 1
    fi
    return 0
}

# Créer le répertoire de logs si nécessaire
mkdir -p /home/ubuntu/azalplus/logs

log "=== Démarrage Chrome MCP ==="

# 1. Vérifier/Démarrer Xvfb
if pgrep -f "Xvfb :$DISPLAY_NUM" > /dev/null; then
    log "Xvfb déjà en cours sur :$DISPLAY_NUM"
else
    log "Démarrage Xvfb sur :$DISPLAY_NUM"
    Xvfb :$DISPLAY_NUM -screen 0 1920x1080x24 &
    sleep 2
    if pgrep -f "Xvfb :$DISPLAY_NUM" > /dev/null; then
        log "Xvfb démarré avec succès"
    else
        log "ERREUR: Impossible de démarrer Xvfb"
        exit 1
    fi
fi

export DISPLAY=:$DISPLAY_NUM

# 2. Arrêter Chrome existant si nécessaire
if pgrep -f "chrome.*remote-debugging-port" > /dev/null; then
    log "Arrêt de Chrome existant..."
    pkill -f "chrome.*remote-debugging-port" || true
    sleep 2
fi

# 3. Démarrer Chrome avec le port de débogage (SÉCURISÉ)
log "Démarrage de Chrome avec remote debugging sur port $CHROME_DEBUG_PORT (localhost only)"
google-chrome \
    --no-sandbox \
    --disable-gpu \
    --disable-dev-shm-usage \
    --remote-debugging-port=$CHROME_DEBUG_PORT \
    --remote-debugging-address=127.0.0.1 \
    --user-data-dir=/home/ubuntu/.config/google-chrome-mcp \
    --no-first-run \
    --disable-default-apps \
    --disable-extensions \
    --disable-plugins \
    --disable-sync \
    --disable-translate \
    --disable-background-networking \
    --safebrowsing-disable-auto-update \
    --disable-client-side-phishing-detection \
    --incognito \
    "https://azalplus.com" &

sleep 5

if pgrep -f "chrome.*remote-debugging-port=$CHROME_DEBUG_PORT" > /dev/null; then
    log "Chrome démarré avec succès sur port $CHROME_DEBUG_PORT"
    # Vérification de sécurité
    sleep 2
    if ! check_security; then
        log "Arrêt de Chrome pour raison de sécurité"
        pkill -f "chrome.*remote-debugging" || true
        exit 1
    fi
    log "Vérification sécurité OK: port accessible uniquement en local"
else
    log "ERREUR: Impossible de démarrer Chrome"
    exit 1
fi

# 4. Démarrer le serveur MCP Claude in Chrome (si disponible)
MCP_SERVER="/home/ubuntu/.npm-global/lib/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/mcp-server-chrome/dist/index.js"
if [ -f "$MCP_SERVER" ]; then
    log "Démarrage du serveur MCP Chrome..."
    node "$MCP_SERVER" --chrome-port=$CHROME_DEBUG_PORT >> "$LOG_FILE" 2>&1 &
    sleep 2
    log "Serveur MCP Chrome démarré"
else
    log "INFO: Serveur MCP Chrome non trouvé, utilisation de l'extension native"
fi

log "=== Chrome MCP prêt ==="
log "Display: :$DISPLAY_NUM"
log "Chrome Debug Port: $CHROME_DEBUG_PORT"

# Garder le script en vie pour systemd
wait
