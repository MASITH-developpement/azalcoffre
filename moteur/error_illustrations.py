"""
AZALPLUS - Illustrations SVG pour pages d'erreur
=================================================

Illustrations alignées avec l'identité visuelle AZALPLUS :
- Bleu Roi : #3454D1 (couleur principale)
- Bleu Accent : #6B9FFF (point lumineux)
- Bleu Marine : #1E3A8A (sidebar)
- Dégradé hero : #3454D1 → #6B9FFF
"""

# Couleurs AZALPLUS
BLEU_ROI = "#3454D1"
BLEU_ACCENT = "#6B9FFF"
BLEU_MARINE = "#1E3A8A"
BLANC = "#FFFFFF"
GRIS_600 = "#475569"
GRIS_400 = "#94A3B8"
ROUGE = "#EF4444"
ORANGE = "#F59E0B"
VERT = "#10B981"

SVG_ILLUSTRATIONS = {
    # 400 - Requête invalide
    400: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .pulse {{ animation: pulse 2s ease-in-out infinite; }}
            .float {{ animation: float 3s ease-in-out infinite; }}
            @keyframes pulse {{ 0%,100%{{opacity:0.6}}50%{{opacity:1}} }}
            @keyframes float {{ 0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-8px)}} }}
        </style>
        <!-- Cercle principal AZAL -->
        <circle cx="100" cy="100" r="75" fill="{BLEU_ROI}"/>
        <circle cx="100" cy="100" r="65" fill="{BLEU_MARINE}" opacity="0.3"/>
        <!-- Point accent -->
        <circle cx="155" cy="55" r="12" fill="{BLEU_ACCENT}" class="pulse"/>
        <!-- Symbole ? stylisé -->
        <text x="100" y="125" font-family="Inter, system-ui, sans-serif" font-weight="800" font-size="80" fill="{BLANC}" text-anchor="middle">?</text>
        <!-- Éléments flottants -->
        <g class="float">
            <circle cx="40" cy="50" r="8" fill="{BLEU_ACCENT}" opacity="0.4"/>
            <circle cx="170" cy="140" r="6" fill="{BLEU_ACCENT}" opacity="0.3"/>
        </g>
        <!-- Lignes de connexion brisées -->
        <path d="M30 100 L50 100" stroke="{GRIS_400}" stroke-width="3" stroke-linecap="round" stroke-dasharray="4 4"/>
        <path d="M150 100 L170 100" stroke="{GRIS_400}" stroke-width="3" stroke-linecap="round" stroke-dasharray="4 4"/>
    </svg>''',

    # 401 - Non authentifié
    401: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .lock {{ animation: shake 0.5s ease-in-out infinite; transform-origin: center; }}
            .glow {{ animation: glow 2s ease-in-out infinite; }}
            @keyframes shake {{ 0%,100%{{transform:rotate(-2deg)}}50%{{transform:rotate(2deg)}} }}
            @keyframes glow {{ 0%,100%{{opacity:0.5}}50%{{opacity:1}} }}
        </style>
        <!-- Cercle de fond -->
        <circle cx="100" cy="100" r="80" fill="{BLEU_MARINE}" opacity="0.1"/>
        <!-- Cadenas -->
        <g class="lock">
            <!-- Anse -->
            <path d="M70 85 L70 65 Q70 40 100 40 Q130 40 130 65 L130 85" stroke="{BLEU_ROI}" stroke-width="10" fill="none" stroke-linecap="round"/>
            <!-- Corps -->
            <rect x="55" y="80" width="90" height="70" rx="12" fill="{BLEU_ROI}"/>
            <rect x="60" y="85" width="80" height="60" rx="10" fill="{BLEU_MARINE}"/>
            <!-- Trou de serrure -->
            <circle cx="100" cy="108" r="12" fill="{BLEU_ROI}"/>
            <path d="M100 115 L95 135 L105 135 Z" fill="{BLEU_ROI}"/>
        </g>
        <!-- Point accent -->
        <circle cx="160" cy="45" r="10" fill="{BLEU_ACCENT}" class="glow"/>
        <!-- Lettre A+ subtile -->
        <text x="100" y="170" font-family="Inter, system-ui, sans-serif" font-weight="700" font-size="14" fill="{GRIS_400}" text-anchor="middle" opacity="0.5">Connexion requise</text>
    </svg>''',

    # 403 - Accès refusé
    403: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .shield {{ animation: pulse 2s ease-in-out infinite; }}
            @keyframes pulse {{ 0%,100%{{transform:scale(1)}}50%{{transform:scale(1.02)}} }}
        </style>
        <!-- Cercle de fond -->
        <circle cx="100" cy="100" r="80" fill="{ROUGE}" opacity="0.1"/>
        <!-- Bouclier AZAL -->
        <g class="shield">
            <path d="M100 30 L155 55 L155 100 Q155 145 100 170 Q45 145 45 100 L45 55 Z" fill="{BLEU_ROI}"/>
            <path d="M100 40 L145 60 L145 100 Q145 138 100 158 Q55 138 55 100 L55 60 Z" fill="{BLEU_MARINE}"/>
            <!-- Croix d'interdiction -->
            <g stroke="{BLANC}" stroke-width="8" stroke-linecap="round">
                <line x1="75" y1="80" x2="125" y2="120"/>
                <line x1="125" y1="80" x2="75" y2="120"/>
            </g>
        </g>
        <!-- Point accent -->
        <circle cx="155" cy="35" r="8" fill="{BLEU_ACCENT}"/>
    </svg>''',

    # 404 - Page introuvable
    404: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .search {{ animation: search 3s ease-in-out infinite; transform-origin: center; }}
            .float {{ animation: float 4s ease-in-out infinite; }}
            @keyframes search {{ 0%,100%{{transform:rotate(-5deg)}}50%{{transform:rotate(5deg)}} }}
            @keyframes float {{ 0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-5px)}} }}
        </style>
        <!-- Cercle principal -->
        <circle cx="100" cy="100" r="75" fill="{BLEU_ROI}"/>
        <!-- Loupe intégrée au design -->
        <g class="search">
            <!-- Cercle de la loupe -->
            <circle cx="90" cy="90" r="35" fill="none" stroke="{BLANC}" stroke-width="8"/>
            <circle cx="90" cy="90" r="25" fill="{BLEU_MARINE}" opacity="0.5"/>
            <!-- Manche -->
            <line x1="115" y1="115" x2="145" y2="145" stroke="{BLANC}" stroke-width="10" stroke-linecap="round"/>
        </g>
        <!-- 404 dans la loupe -->
        <text x="90" y="98" font-family="Inter, system-ui, sans-serif" font-weight="700" font-size="18" fill="{BLANC}" text-anchor="middle">404</text>
        <!-- Point accent -->
        <circle cx="155" cy="50" r="10" fill="{BLEU_ACCENT}" class="float"/>
        <!-- Points décoratifs -->
        <circle cx="45" cy="45" r="4" fill="{BLEU_ACCENT}" opacity="0.4"/>
        <circle cx="160" cy="160" r="3" fill="{BLEU_ACCENT}" opacity="0.3"/>
    </svg>''',

    # 405 - Méthode non autorisée
    405: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .block {{ animation: pulse 1.5s ease-in-out infinite; }}
            @keyframes pulse {{ 0%,100%{{opacity:1}}50%{{opacity:0.7}} }}
        </style>
        <!-- Cercle principal -->
        <circle cx="100" cy="100" r="75" fill="{BLEU_ROI}"/>
        <!-- Symbole sens interdit -->
        <circle cx="100" cy="100" r="50" fill="none" stroke="{BLANC}" stroke-width="6" class="block"/>
        <rect x="55" y="94" width="90" height="12" rx="3" fill="{BLANC}" class="block"/>
        <!-- Point accent -->
        <circle cx="160" cy="50" r="8" fill="{BLEU_ACCENT}"/>
        <!-- Flèches bloquées -->
        <g stroke="{GRIS_400}" stroke-width="3" fill="none" stroke-linecap="round">
            <path d="M25 100 L40 100 M35 95 L40 100 L35 105"/>
            <path d="M175 100 L160 100 M165 95 L160 100 L165 105"/>
        </g>
    </svg>''',

    # 408 - Timeout
    408: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .hand {{ animation: tick 2s steps(60) infinite; transform-origin: 100px 100px; }}
            .pulse {{ animation: pulse 1s ease-in-out infinite; }}
            @keyframes tick {{ from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}} }}
            @keyframes pulse {{ 0%,100%{{opacity:0.5}}50%{{opacity:1}} }}
        </style>
        <!-- Cercle horloge -->
        <circle cx="100" cy="100" r="75" fill="{BLEU_ROI}"/>
        <circle cx="100" cy="100" r="65" fill="{BLEU_MARINE}"/>
        <!-- Cadran -->
        <circle cx="100" cy="100" r="55" fill="{BLANC}" opacity="0.1"/>
        <!-- Marqueurs -->
        <g fill="{BLANC}">
            <rect x="97" y="35" width="6" height="15" rx="2"/>
            <rect x="97" y="150" width="6" height="15" rx="2"/>
            <rect x="35" y="97" width="15" height="6" rx="2"/>
            <rect x="150" y="97" width="15" height="6" rx="2"/>
        </g>
        <!-- Aiguilles -->
        <line x1="100" y1="100" x2="100" y2="55" stroke="{BLANC}" stroke-width="4" stroke-linecap="round"/>
        <line x1="100" y1="100" x2="130" y2="100" stroke="{ORANGE}" stroke-width="3" stroke-linecap="round" class="hand"/>
        <circle cx="100" cy="100" r="6" fill="{BLANC}"/>
        <!-- Point accent -->
        <circle cx="160" cy="40" r="8" fill="{BLEU_ACCENT}" class="pulse"/>
    </svg>''',

    # 422 - Données invalides
    422: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .error {{ animation: shake 0.3s ease-in-out infinite; transform-origin: center; }}
            @keyframes shake {{ 0%,100%{{transform:translateX(0)}}25%{{transform:translateX(-2px)}}75%{{transform:translateX(2px)}} }}
        </style>
        <!-- Document -->
        <rect x="45" y="30" width="110" height="140" rx="10" fill="{BLEU_ROI}"/>
        <rect x="50" y="35" width="100" height="130" rx="8" fill="{BLANC}"/>
        <!-- Lignes de texte -->
        <rect x="65" y="55" width="70" height="8" rx="2" fill="{GRIS_400}" opacity="0.3"/>
        <rect x="65" y="75" width="50" height="8" rx="2" fill="{GRIS_400}" opacity="0.3"/>
        <!-- Champ en erreur -->
        <g class="error">
            <rect x="60" y="95" width="80" height="25" rx="5" fill="#FEE2E2" stroke="{ROUGE}" stroke-width="2"/>
            <circle cx="130" cy="107" r="8" fill="{ROUGE}"/>
            <text x="130" y="112" font-size="12" fill="{BLANC}" text-anchor="middle" font-weight="bold">!</text>
        </g>
        <!-- Champ valide -->
        <rect x="60" y="130" width="80" height="25" rx="5" fill="#D1FAE5" stroke="{VERT}" stroke-width="2"/>
        <circle cx="130" cy="142" r="8" fill="{VERT}"/>
        <path d="M126 142 L129 145 L135 139" stroke="{BLANC}" stroke-width="2" fill="none" stroke-linecap="round"/>
        <!-- Point accent -->
        <circle cx="155" cy="35" r="8" fill="{BLEU_ACCENT}"/>
    </svg>''',

    # 429 - Trop de requêtes
    429: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .bar {{ animation: grow 0.5s ease-in-out infinite alternate; transform-origin: bottom; }}
            .warning {{ animation: blink 0.8s ease-in-out infinite; }}
            @keyframes grow {{ from{{transform:scaleY(0.8)}}to{{transform:scaleY(1)}} }}
            @keyframes blink {{ 0%,100%{{opacity:1}}50%{{opacity:0.5}} }}
        </style>
        <!-- Cercle principal -->
        <circle cx="100" cy="100" r="75" fill="{BLEU_ROI}"/>
        <!-- Graphique en barres (surcharge) -->
        <g transform="translate(50, 50)">
            <rect x="10" y="60" width="15" height="40" rx="3" fill="{BLEU_ACCENT}" class="bar"/>
            <rect x="30" y="40" width="15" height="60" rx="3" fill="{BLEU_ACCENT}" class="bar" style="animation-delay:0.1s"/>
            <rect x="50" y="20" width="15" height="80" rx="3" fill="{ORANGE}" class="bar" style="animation-delay:0.2s"/>
            <rect x="70" y="5" width="15" height="95" rx="3" fill="{ROUGE}" class="bar warning" style="animation-delay:0.3s"/>
        </g>
        <!-- Ligne de limite -->
        <line x1="55" y1="65" x2="145" y2="65" stroke="{BLANC}" stroke-width="2" stroke-dasharray="5 3"/>
        <text x="148" y="68" font-size="10" fill="{BLANC}" font-family="monospace">MAX</text>
        <!-- Point accent -->
        <circle cx="160" cy="45" r="8" fill="{BLEU_ACCENT}"/>
    </svg>''',

    # 500 - Erreur serveur
    500: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .gear {{ animation: rotate 4s linear infinite; transform-origin: 100px 100px; }}
            .spark {{ animation: spark 0.5s ease-in-out infinite; }}
            @keyframes rotate {{ from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}} }}
            @keyframes spark {{ 0%,100%{{opacity:1}}50%{{opacity:0.3}} }}
        </style>
        <!-- Cercle principal -->
        <circle cx="100" cy="100" r="75" fill="{BLEU_ROI}"/>
        <!-- Engrenage cassé -->
        <g class="gear">
            <circle cx="100" cy="100" r="40" fill="{BLEU_MARINE}"/>
            <circle cx="100" cy="100" r="25" fill="{BLEU_ROI}"/>
            <!-- Dents -->
            <rect x="92" y="52" width="16" height="15" rx="2" fill="{BLEU_MARINE}"/>
            <rect x="92" y="133" width="16" height="15" rx="2" fill="{BLEU_MARINE}"/>
            <rect x="52" y="92" width="15" height="16" rx="2" fill="{BLEU_MARINE}"/>
            <rect x="133" y="92" width="15" height="16" rx="2" fill="{BLEU_MARINE}"/>
        </g>
        <!-- Éclair d'erreur -->
        <g class="spark">
            <path d="M95 85 L105 98 L98 98 L108 115 L95 100 L102 100 Z" fill="{ORANGE}"/>
        </g>
        <!-- Point accent -->
        <circle cx="155" cy="50" r="10" fill="{ROUGE}" class="spark"/>
        <!-- Croix d'erreur -->
        <g stroke="{BLANC}" stroke-width="4" stroke-linecap="round" class="spark">
            <line x1="85" y1="85" x2="115" y2="115"/>
            <line x1="115" y1="85" x2="85" y2="115"/>
        </g>
    </svg>''',

    # 502 - Bad Gateway
    502: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .server1 {{ animation: pulse1 2s ease-in-out infinite; }}
            .server2 {{ animation: pulse2 2s ease-in-out infinite; }}
            .break {{ animation: break 1s ease-in-out infinite; }}
            @keyframes pulse1 {{ 0%,100%{{opacity:1}}50%{{opacity:0.7}} }}
            @keyframes pulse2 {{ 0%,100%{{opacity:0.7}}50%{{opacity:1}} }}
            @keyframes break {{ 0%,100%{{stroke-dashoffset:0}}50%{{stroke-dashoffset:10}} }}
        </style>
        <!-- Serveur A (AZAL) -->
        <g class="server1">
            <rect x="25" y="60" width="50" height="80" rx="8" fill="{BLEU_ROI}"/>
            <rect x="30" y="65" width="40" height="70" rx="6" fill="{BLEU_MARINE}"/>
            <circle cx="45" cy="80" r="5" fill="{VERT}"/>
            <circle cx="45" cy="95" r="5" fill="{VERT}"/>
            <circle cx="45" cy="110" r="5" fill="{BLEU_ACCENT}"/>
        </g>
        <!-- Serveur B (externe) -->
        <g class="server2">
            <rect x="125" y="60" width="50" height="80" rx="8" fill="{GRIS_600}"/>
            <rect x="130" y="65" width="40" height="70" rx="6" fill="#374151"/>
            <circle cx="145" cy="80" r="5" fill="{ROUGE}"/>
            <circle cx="145" cy="95" r="5" fill="{ROUGE}"/>
            <circle cx="145" cy="110" r="5" fill="{ORANGE}"/>
        </g>
        <!-- Connexion brisée -->
        <path d="M75 100 L90 100" stroke="{BLEU_ACCENT}" stroke-width="4" stroke-linecap="round"/>
        <path d="M110 100 L125 100" stroke="{GRIS_400}" stroke-width="4" stroke-linecap="round"/>
        <g class="break">
            <path d="M92 90 L100 100 L92 110" stroke="{ROUGE}" stroke-width="3" fill="none" stroke-dasharray="4 2"/>
            <path d="M108 90 L100 100 L108 110" stroke="{ROUGE}" stroke-width="3" fill="none" stroke-dasharray="4 2"/>
        </g>
        <!-- Point accent -->
        <circle cx="170" cy="45" r="8" fill="{BLEU_ACCENT}"/>
    </svg>''',

    # 503 - Service indisponible
    503: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .gear1 {{ animation: rotate1 3s linear infinite; transform-origin: 75px 100px; }}
            .gear2 {{ animation: rotate2 3s linear infinite; transform-origin: 125px 100px; }}
            @keyframes rotate1 {{ from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}} }}
            @keyframes rotate2 {{ from{{transform:rotate(0deg)}}to{{transform:rotate(-360deg)}} }}
        </style>
        <!-- Fond -->
        <circle cx="100" cy="100" r="80" fill="{BLEU_MARINE}" opacity="0.1"/>
        <!-- Engrenage 1 -->
        <g class="gear1">
            <circle cx="75" cy="100" r="30" fill="{BLEU_ROI}"/>
            <circle cx="75" cy="100" r="18" fill="{BLEU_MARINE}"/>
            <circle cx="75" cy="100" r="8" fill="{BLEU_ACCENT}"/>
            <rect x="68" y="65" width="14" height="12" rx="2" fill="{BLEU_ROI}"/>
            <rect x="68" y="123" width="14" height="12" rx="2" fill="{BLEU_ROI}"/>
            <rect x="40" y="93" width="12" height="14" rx="2" fill="{BLEU_ROI}"/>
            <rect x="98" y="93" width="12" height="14" rx="2" fill="{BLEU_ROI}"/>
        </g>
        <!-- Engrenage 2 -->
        <g class="gear2">
            <circle cx="125" cy="100" r="25" fill="{BLEU_ACCENT}"/>
            <circle cx="125" cy="100" r="15" fill="{BLEU_ROI}"/>
            <circle cx="125" cy="100" r="6" fill="{BLANC}"/>
            <rect x="119" y="72" width="12" height="10" rx="2" fill="{BLEU_ACCENT}"/>
            <rect x="119" y="118" width="12" height="10" rx="2" fill="{BLEU_ACCENT}"/>
            <rect x="97" y="94" width="10" height="12" rx="2" fill="{BLEU_ACCENT}"/>
            <rect x="143" y="94" width="10" height="12" rx="2" fill="{BLEU_ACCENT}"/>
        </g>
        <!-- Badge maintenance -->
        <rect x="55" y="155" width="90" height="28" rx="6" fill="{ORANGE}"/>
        <text x="100" y="174" font-family="Inter, system-ui, sans-serif" font-weight="600" font-size="12" fill="{BLANC}" text-anchor="middle">MAINTENANCE</text>
    </svg>''',

    # 504 - Gateway Timeout
    504: f'''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .progress {{ animation: stuck 2s ease-in-out infinite; }}
            .dots {{ animation: dots 1.5s steps(4) infinite; }}
            @keyframes stuck {{ 0%,100%{{width:90px}}50%{{width:95px}} }}
            @keyframes dots {{ 0%{{opacity:0.2}}25%{{opacity:0.5}}50%{{opacity:0.8}}75%{{opacity:1}} }}
        </style>
        <!-- Cercle principal -->
        <circle cx="100" cy="100" r="75" fill="{BLEU_ROI}"/>
        <!-- Barre de progression -->
        <rect x="40" y="90" width="120" height="20" rx="10" fill="{BLEU_MARINE}"/>
        <rect x="45" y="95" width="90" height="10" rx="5" fill="{BLEU_ACCENT}" class="progress"/>
        <!-- Pourcentage bloqué -->
        <text x="100" y="75" font-family="Inter, system-ui, sans-serif" font-weight="700" font-size="24" fill="{BLANC}" text-anchor="middle">73%</text>
        <!-- Points d'attente -->
        <g fill="{BLANC}" class="dots">
            <circle cx="80" cy="130" r="4"/>
            <circle cx="100" cy="130" r="4" style="animation-delay:0.3s"/>
            <circle cx="120" cy="130" r="4" style="animation-delay:0.6s"/>
        </g>
        <!-- Point accent -->
        <circle cx="160" cy="45" r="8" fill="{BLEU_ACCENT}"/>
        <!-- Horloge mini -->
        <g transform="translate(155, 140)">
            <circle r="15" fill="{BLEU_MARINE}"/>
            <circle r="12" fill="{BLANC}" opacity="0.2"/>
            <line x1="0" y1="0" x2="0" y2="-8" stroke="{BLANC}" stroke-width="2" stroke-linecap="round"/>
            <line x1="0" y1="0" x2="5" y2="3" stroke="{ORANGE}" stroke-width="2" stroke-linecap="round"/>
        </g>
    </svg>''',
}
