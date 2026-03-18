"""
AZALPLUS - Pages d'erreur personnalisées
========================================

Gère l'affichage de pages d'erreur stylisées pour les codes HTTP courants.
"""

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
import os

# Configuration Jinja2 pour les templates d'erreur
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "errors")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

# Import des illustrations SVG ULTRA FUN
from .error_illustrations import SVG_ILLUSTRATIONS

# Ancien code SVG gardé pour référence - maintenant dans error_illustrations.py
_OLD_SVG_ILLUSTRATIONS = {
    400: '''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .confuse { animation: spin 4s ease-in-out infinite; transform-origin: center; }
            .question { animation: float 1s ease-in-out infinite; }
            .question2 { animation: float 1s ease-in-out infinite 0.3s; }
            .question3 { animation: float 1s ease-in-out infinite 0.6s; }
            .blink { animation: blink 3s infinite; }
            @keyframes spin { 0%,100%{transform:rotate(-5deg)}50%{transform:rotate(5deg)} }
            @keyframes float { 0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)} }
            @keyframes blink { 0%,48%,52%,100%{opacity:1}50%{opacity:0} }
        </style>
        <!-- Nuage de confusion -->
        <ellipse cx="100" cy="115" rx="70" ry="20" fill="#E5E7EB" opacity="0.5"/>
        <!-- Tête emoji confus -->
        <circle cx="100" cy="85" r="60" fill="#FBBF24"/>
        <circle cx="100" cy="85" r="55" fill="#FCD34D"/>
        <!-- Sourcils confus -->
        <path d="M60 60 Q75 55 85 65" stroke="#92400E" stroke-width="4" fill="none" class="confuse"/>
        <path d="M115 65 Q125 55 140 60" stroke="#92400E" stroke-width="4" fill="none" class="confuse"/>
        <!-- Yeux -->
        <ellipse cx="75" cy="80" rx="10" ry="12" fill="white"/>
        <ellipse cx="125" cy="80" rx="10" ry="12" fill="white"/>
        <circle cx="78" cy="82" r="6" fill="#1F2937" class="blink"/>
        <circle cx="128" cy="82" r="6" fill="#1F2937" class="blink"/>
        <!-- Bouche confuse -->
        <path d="M70 115 Q85 105 100 115 Q115 125 130 115" stroke="#92400E" stroke-width="5" fill="none" stroke-linecap="round"/>
        <!-- Points d'interrogation flottants -->
        <text x="25" y="45" font-size="35" fill="#F59E0B" font-weight="bold" class="question">?</text>
        <text x="155" y="40" font-size="28" fill="#FBBF24" font-weight="bold" class="question2">?</text>
        <text x="165" y="70" font-size="20" fill="#FCD34D" font-weight="bold" class="question3">?</text>
        <!-- Spirales -->
        <path d="M30 90 Q20 70 35 60" stroke="#F59E0B" stroke-width="3" fill="none" stroke-linecap="round"/>
        <path d="M170 85 Q180 65 165 55" stroke="#F59E0B" stroke-width="3" fill="none" stroke-linecap="round"/>
    </svg>''',

    401: '''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .lock-shake { animation: shake 0.5s ease-in-out infinite; transform-origin: center bottom; }
            .key-wiggle { animation: wiggle 1s ease-in-out infinite; transform-origin: right center; }
            .zzz1 { animation: zzz 2s ease-in-out infinite; }
            .zzz2 { animation: zzz 2s ease-in-out infinite 0.3s; }
            .zzz3 { animation: zzz 2s ease-in-out infinite 0.6s; }
            .eye-blink { animation: blink 4s infinite; }
            @keyframes shake { 0%,100%{transform:rotate(-3deg)}50%{transform:rotate(3deg)} }
            @keyframes wiggle { 0%,100%{transform:rotate(-10deg)}50%{transform:rotate(10deg)} }
            @keyframes zzz { 0%,100%{opacity:0.3;transform:translateY(0)}50%{opacity:1;transform:translateY(-5px)} }
            @keyframes blink { 0%,45%,55%,100%{transform:scaleY(1)}50%{transform:scaleY(0.1)} }
        </style>
        <!-- Ombre -->
        <ellipse cx="100" cy="175" rx="50" ry="10" fill="#00000022"/>
        <!-- Cadenas kawaii -->
        <g class="lock-shake">
            <rect x="50" y="90" width="100" height="80" rx="15" fill="#F59E0B"/>
            <rect x="55" y="95" width="90" height="70" rx="12" fill="#FBBF24"/>
            <!-- Arc du cadenas -->
            <path d="M65 90 V60 Q65 25 100 25 Q135 25 135 60 V90" stroke="#92400E" stroke-width="12" fill="none" stroke-linecap="round"/>
            <!-- Trou de serrure forme cœur -->
            <ellipse cx="100" cy="125" rx="12" ry="10" fill="#92400E"/>
            <path d="M100 132 L90 150 L100 160 L110 150 Z" fill="#92400E"/>
            <!-- Visage kawaii -->
            <ellipse cx="80" cy="115" rx="8" ry="10" fill="white" class="eye-blink"/>
            <ellipse cx="120" cy="115" rx="8" ry="10" fill="white" class="eye-blink"/>
            <circle cx="82" cy="117" r="4" fill="#1F2937"/>
            <circle cx="122" cy="117" r="4" fill="#1F2937"/>
            <!-- Joues roses -->
            <ellipse cx="65" cy="130" rx="8" ry="5" fill="#FCA5A5" opacity="0.6"/>
            <ellipse cx="135" cy="130" rx="8" ry="5" fill="#FCA5A5" opacity="0.6"/>
        </g>
        <!-- Clé qui essaie d'entrer -->
        <g class="key-wiggle" transform="translate(150, 130)">
            <rect x="0" y="-5" width="35" height="10" rx="3" fill="#FCD34D"/>
            <circle cx="40" cy="0" r="12" fill="#FCD34D" stroke="#F59E0B" stroke-width="3"/>
            <rect x="-5" y="-3" width="8" height="6" fill="#FBBF24"/>
            <rect x="-10" y="-2" width="6" height="4" fill="#FBBF24"/>
        </g>
        <!-- ZZZ -->
        <text x="140" y="50" font-size="24" fill="#6366F1" font-weight="bold" class="zzz1">Z</text>
        <text x="155" y="35" font-size="20" fill="#818CF8" font-weight="bold" class="zzz2">z</text>
        <text x="168" y="23" font-size="16" fill="#A5B4FC" font-weight="bold" class="zzz3">z</text>
    </svg>''',

    403: '''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .guard-body { animation: breathe 2s ease-in-out infinite; transform-origin: center bottom; }
            .stop-pulse { animation: pulse 1s ease-in-out infinite; transform-origin: center; }
            .sunglasses { animation: glint 3s ease-in-out infinite; }
            @keyframes breathe { 0%,100%{transform:scaleY(1)}50%{transform:scaleY(1.02)} }
            @keyframes pulse { 0%,100%{transform:scale(1)}50%{transform:scale(1.1)} }
            @keyframes glint { 0%,100%{opacity:1}50%{opacity:0.8} }
        </style>
        <!-- Ombre -->
        <ellipse cx="100" cy="185" rx="55" ry="12" fill="#00000022"/>
        <!-- Corps du garde -->
        <g class="guard-body">
            <!-- Corps -->
            <rect x="55" y="95" width="90" height="85" rx="10" fill="#1F2937"/>
            <!-- Badge -->
            <circle cx="130" cy="115" r="10" fill="#FCD34D"/>
            <text x="126" y="119" font-size="10" fill="#92400E" font-weight="bold">G</text>
            <!-- Bras croisés -->
            <path d="M55 130 Q30 120 40 150 Q50 170 70 160" fill="#FECACA"/>
            <path d="M145 130 Q170 120 160 150 Q150 170 130 160" fill="#FECACA"/>
            <ellipse cx="70" cy="155" rx="20" ry="8" fill="#FECACA"/>
            <ellipse cx="130" cy="155" rx="20" ry="8" fill="#FECACA"/>
        </g>
        <!-- Tête -->
        <circle cx="100" cy="65" r="40" fill="#FECACA"/>
        <!-- Lunettes de soleil cool -->
        <g class="sunglasses">
            <rect x="62" y="55" width="30" height="20" rx="5" fill="#111827"/>
            <rect x="108" y="55" width="30" height="20" rx="5" fill="#111827"/>
            <line x1="92" y1="65" x2="108" y2="65" stroke="#111827" stroke-width="4"/>
            <line x1="62" y1="60" x2="50" y2="50" stroke="#111827" stroke-width="3"/>
            <line x1="138" y1="60" x2="150" y2="50" stroke="#111827" stroke-width="3"/>
            <!-- Reflet -->
            <rect x="65" y="58" width="8" height="3" rx="1" fill="white" opacity="0.4"/>
            <rect x="111" y="58" width="8" height="3" rx="1" fill="white" opacity="0.4"/>
        </g>
        <!-- Bouche sérieuse -->
        <path d="M85 88 L115 88" stroke="#991B1B" stroke-width="4" stroke-linecap="round"/>
        <!-- Panneau STOP animé -->
        <g class="stop-pulse" transform="translate(155, 30)">
            <polygon points="0,-25 22,-12 22,12 0,25 -22,12 -22,-12" fill="#EF4444" stroke="#B91C1C" stroke-width="3"/>
            <text x="-18" y="6" font-size="14" fill="white" font-weight="bold">STOP</text>
        </g>
        <!-- Étoiles de méchanceté -->
        <text x="30" y="50" font-size="16" fill="#F59E0B">💢</text>
    </svg>''',

    404: '''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .ghost { animation: ghostFloat 3s ease-in-out infinite; }
            .ghost-tail { animation: tailWiggle 1s ease-in-out infinite; }
            .eyes { animation: lookAround 4s ease-in-out infinite; }
            .magnifier { animation: search 2s ease-in-out infinite; }
            .question { animation: pop 2s ease-in-out infinite; }
            @keyframes ghostFloat { 0%,100%{transform:translateY(0)}50%{transform:translateY(-15px)} }
            @keyframes tailWiggle { 0%,100%{d:path("M30,140 Q40,130 50,140 Q60,150 70,140 Q80,130 90,140 Q100,150 110,140 Q120,130 130,140 Q140,150 150,140 L150,100 Q150,50 90,50 Q30,50 30,100 Z")}50%{d:path("M30,140 Q40,150 50,140 Q60,130 70,140 Q80,150 90,140 Q100,130 110,140 Q120,150 130,140 Q140,130 150,140 L150,100 Q150,50 90,50 Q30,50 30,100 Z")} }
            @keyframes lookAround { 0%,100%{transform:translateX(0)}25%{transform:translateX(-5px)}75%{transform:translateX(5px)} }
            @keyframes search { 0%,100%{transform:rotate(-10deg) translateY(0)}50%{transform:rotate(10deg) translateY(-5px)} }
            @keyframes pop { 0%,100%{transform:scale(1);opacity:0.7}50%{transform:scale(1.2);opacity:1} }
        </style>
        <!-- Ombre -->
        <ellipse cx="90" cy="175" rx="50" ry="12" fill="#00000022" class="ghost"/>
        <!-- Fantôme kawaii -->
        <g class="ghost">
            <!-- Corps du fantôme -->
            <path d="M30,140 Q40,130 50,140 Q60,150 70,140 Q80,130 90,140 Q100,150 110,140 Q120,130 130,140 Q140,150 150,140 L150,100 Q150,50 90,50 Q30,50 30,100 Z" fill="white" stroke="#E5E7EB" stroke-width="2"/>
            <!-- Dégradé fantomatique -->
            <path d="M30,140 Q40,130 50,140 Q60,150 70,140 Q80,130 90,140 Q100,150 110,140 Q120,130 130,140 Q140,150 150,140 L150,100 Q150,50 90,50 Q30,50 30,100 Z" fill="url(#ghostGrad)" opacity="0.3"/>
            <!-- Yeux kawaii -->
            <g class="eyes">
                <ellipse cx="70" cy="90" rx="15" ry="18" fill="#1F2937"/>
                <ellipse cx="110" cy="90" rx="15" ry="18" fill="#1F2937"/>
                <ellipse cx="73" cy="87" rx="6" ry="7" fill="white"/>
                <ellipse cx="113" cy="87" rx="6" ry="7" fill="white"/>
            </g>
            <!-- Bouche étonnée -->
            <ellipse cx="90" cy="115" rx="10" ry="12" fill="#374151"/>
            <!-- Joues roses -->
            <ellipse cx="50" cy="100" rx="10" ry="6" fill="#FCA5A5" opacity="0.5"/>
            <ellipse cx="130" cy="100" rx="10" ry="6" fill="#FCA5A5" opacity="0.5"/>
        </g>
        <!-- Loupe -->
        <g class="magnifier" transform="translate(140, 120)">
            <circle cx="15" cy="15" r="20" stroke="#6366F1" stroke-width="6" fill="#EEF2FF"/>
            <line x1="30" y1="30" x2="50" y2="50" stroke="#6366F1" stroke-width="8" stroke-linecap="round"/>
            <text x="5" y="22" font-size="20">👀</text>
        </g>
        <!-- Points d'interrogation -->
        <text x="15" y="60" font-size="30" fill="#A5B4FC" class="question">?</text>
        <text x="165" y="50" font-size="24" fill="#C4B5FD" class="question" style="animation-delay:0.5s">?</text>
        <text x="25" y="170" font-size="20" fill="#DDD6FE" class="question" style="animation-delay:1s">?</text>
        <defs>
            <linearGradient id="ghostGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:#C4B5FD"/>
                <stop offset="100%" style="stop-color:#E5E7EB"/>
            </linearGradient>
        </defs>
    </svg>''',

    405: '''<svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
        <!-- Panneau de signalisation -->
        <rect x="55" y="50" width="10" height="60" fill="#6B7280"/>
        <polygon points="60,10 100,35 100,55 60,80 20,55 20,35" fill="#FCD34D" stroke="#92400E" stroke-width="3"/>
        <!-- Bonhomme interdit -->
        <circle cx="60" cy="35" r="8" fill="#92400E"/>
        <line x1="60" y1="43" x2="60" y2="58" stroke="#92400E" stroke-width="3"/>
        <line x1="50" y1="50" x2="70" y2="50" stroke="#92400E" stroke-width="3"/>
        <line x1="60" y1="58" x2="52" y2="70" stroke="#92400E" stroke-width="3"/>
        <line x1="60" y1="58" x2="68" y2="70" stroke="#92400E" stroke-width="3"/>
        <!-- Cercle barré -->
        <circle cx="60" cy="45" r="25" stroke="#EF4444" stroke-width="4" fill="none"/>
        <line x1="42" y1="27" x2="78" y2="63" stroke="#EF4444" stroke-width="4"/>
    </svg>''',

    408: '''<svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
        <!-- Horloge stressée -->
        <circle cx="60" cy="60" r="45" fill="#FEF3C7" stroke="#F59E0B" stroke-width="4"/>
        <circle cx="60" cy="60" r="38" fill="white"/>
        <!-- Aiguilles affolées -->
        <line x1="60" y1="60" x2="60" y2="30" stroke="#1F2937" stroke-width="4" stroke-linecap="round"/>
        <line x1="60" y1="60" x2="85" y2="70" stroke="#EF4444" stroke-width="3" stroke-linecap="round"/>
        <circle cx="60" cy="60" r="5" fill="#1F2937"/>
        <!-- Visage paniqué -->
        <ellipse cx="45" cy="50" rx="5" ry="7" fill="#1F2937"/>
        <ellipse cx="75" cy="50" rx="5" ry="7" fill="#1F2937"/>
        <ellipse cx="60" cy="75" rx="10" ry="8" fill="#1F2937"/>
        <!-- Gouttes de sueur -->
        <path d="M25 40 Q22 50 25 55 Q28 50 25 40" fill="#60A5FA"/>
        <path d="M95 45 Q92 52 95 57 Q98 52 95 45" fill="#60A5FA"/>
        <!-- Éclairs de stress -->
        <path d="M15 60 L20 55 L18 60 L23 58" stroke="#F59E0B" stroke-width="2" fill="none"/>
        <path d="M100 55 L105 50 L103 55 L108 53" stroke="#F59E0B" stroke-width="2" fill="none"/>
    </svg>''',

    422: '''<svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
        <!-- Formulaire froissé -->
        <path d="M25 15 L85 15 L95 25 L95 105 L25 105 Z" fill="white" stroke="#D1D5DB" stroke-width="2"/>
        <path d="M85 15 L85 25 L95 25" fill="#E5E7EB" stroke="#D1D5DB" stroke-width="2"/>
        <!-- Lignes de texte -->
        <line x1="35" y1="40" x2="75" y2="40" stroke="#E5E7EB" stroke-width="3"/>
        <line x1="35" y1="55" x2="85" y2="55" stroke="#E5E7EB" stroke-width="3"/>
        <line x1="35" y1="70" x2="65" y2="70" stroke="#E5E7EB" stroke-width="3"/>
        <!-- Croix rouges -->
        <g stroke="#EF4444" stroke-width="3">
            <line x1="78" y1="37" x2="88" y2="47"/>
            <line x1="88" y1="37" x2="78" y2="47"/>
            <line x1="78" y1="52" x2="88" y2="62"/>
            <line x1="88" y1="52" x2="78" y2="62"/>
        </g>
        <!-- Crayon triste -->
        <rect x="5" y="80" width="40" height="12" rx="2" fill="#FCD34D" transform="rotate(-30 5 80)"/>
        <polygon points="5,92 0,98 8,95" fill="#F59E0B" transform="rotate(-30 5 80)"/>
        <!-- Visage triste sur crayon -->
        <circle cx="18" cy="72" r="2" fill="#92400E"/>
        <circle cx="28" cy="68" r="2" fill="#92400E"/>
        <path d="M20 78 Q24 75 28 78" stroke="#92400E" stroke-width="1.5" fill="none"/>
    </svg>''',

    429: '''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .wheel { animation: spin 2s linear infinite; transform-origin: center; }
            .hamster { animation: run 0.3s steps(2) infinite; }
            .sweat { animation: drip 1s ease-in-out infinite; }
            .stars { animation: twinkle 0.5s ease-in-out infinite; }
            .tongue { animation: pant 0.5s ease-in-out infinite; }
            @keyframes spin { from{transform:rotate(0deg)}to{transform:rotate(360deg)} }
            @keyframes run { 0%{transform:translateY(0)}50%{transform:translateY(-3px)} }
            @keyframes drip { 0%{transform:translateY(0);opacity:1}100%{transform:translateY(20px);opacity:0} }
            @keyframes twinkle { 0%,100%{opacity:1}50%{opacity:0.3} }
            @keyframes pant { 0%,100%{transform:scaleY(1)}50%{transform:scaleY(1.3)} }
        </style>
        <!-- Ombre -->
        <ellipse cx="100" cy="180" rx="60" ry="15" fill="#00000022"/>
        <!-- Roue de hamster -->
        <g class="wheel">
            <circle cx="100" cy="100" r="70" stroke="#E5E7EB" stroke-width="12" fill="none"/>
            <circle cx="100" cy="100" r="55" fill="#FEF3C7" stroke="#D1D5DB" stroke-width="2"/>
            <!-- Barreaux -->
            <line x1="100" y1="30" x2="100" y2="170" stroke="#D1D5DB" stroke-width="3"/>
            <line x1="30" y1="100" x2="170" y2="100" stroke="#D1D5DB" stroke-width="3"/>
            <line x1="50" y1="50" x2="150" y2="150" stroke="#D1D5DB" stroke-width="3"/>
            <line x1="150" y1="50" x2="50" y2="150" stroke="#D1D5DB" stroke-width="3"/>
        </g>
        <!-- Hamster kawaii épuisé -->
        <g class="hamster">
            <!-- Corps -->
            <ellipse cx="100" cy="110" rx="30" ry="22" fill="#FBBF24"/>
            <!-- Tête -->
            <circle cx="100" cy="85" r="22" fill="#FCD34D"/>
            <!-- Oreilles -->
            <ellipse cx="82" cy="68" rx="8" ry="12" fill="#FBBF24"/>
            <ellipse cx="118" cy="68" rx="8" ry="12" fill="#FBBF24"/>
            <ellipse cx="82" cy="68" rx="5" ry="8" fill="#FCA5A5"/>
            <ellipse cx="118" cy="68" rx="5" ry="8" fill="#FCA5A5"/>
            <!-- Yeux spirale (vertige) -->
            <g stroke="#92400E" fill="none" stroke-width="2">
                <circle cx="90" cy="82" r="8"/>
                <circle cx="90" cy="82" r="5"/>
                <circle cx="90" cy="82" r="2"/>
                <circle cx="110" cy="82" r="8"/>
                <circle cx="110" cy="82" r="5"/>
                <circle cx="110" cy="82" r="2"/>
            </g>
            <!-- Langue qui pend -->
            <ellipse cx="100" cy="100" rx="5" ry="10" fill="#F87171" class="tongue"/>
            <!-- Joues -->
            <ellipse cx="75" cy="90" rx="8" ry="5" fill="#FCA5A5" opacity="0.7"/>
            <ellipse cx="125" cy="90" rx="8" ry="5" fill="#FCA5A5" opacity="0.7"/>
            <!-- Pattes -->
            <ellipse cx="80" cy="125" rx="8" ry="5" fill="#FBBF24"/>
            <ellipse cx="120" cy="125" rx="8" ry="5" fill="#FBBF24"/>
        </g>
        <!-- Gouttes de sueur -->
        <path d="M65 60 Q60 65 65 75" fill="#60A5FA" class="sweat"/>
        <path d="M140 55 Q135 60 140 70" fill="#60A5FA" class="sweat" style="animation-delay:0.3s"/>
        <!-- Étoiles de vertige -->
        <text x="55" y="50" font-size="20" class="stars">⭐</text>
        <text x="135" y="45" font-size="16" class="stars" style="animation-delay:0.2s">✨</text>
        <text x="45" y="75" font-size="14" class="stars" style="animation-delay:0.4s">💫</text>
        <!-- Message -->
        <text x="100" y="20" font-size="14" fill="#EF4444" text-anchor="middle" font-weight="bold">TROP VITE!</text>
    </svg>''',

    500: '''<svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <style>
            .robot { animation: shake 0.3s ease-in-out infinite; transform-origin: center bottom; }
            .smoke { animation: rise 2s ease-out infinite; }
            .spark { animation: spark 0.5s ease-out infinite; }
            .antenna { animation: zap 0.2s ease-in-out infinite; }
            .eye-x { animation: blink-x 1s ease-in-out infinite; }
            @keyframes shake { 0%,100%{transform:translateX(-2px) rotate(-1deg)}50%{transform:translateX(2px) rotate(1deg)} }
            @keyframes rise { 0%{transform:translateY(0);opacity:0.8}100%{transform:translateY(-30px);opacity:0} }
            @keyframes spark { 0%{opacity:1;transform:scale(1)}100%{opacity:0;transform:scale(1.5)} }
            @keyframes zap { 0%,100%{fill:#EF4444}50%{fill:#FCD34D} }
            @keyframes blink-x { 0%,100%{opacity:1}50%{opacity:0.5} }
        </style>
        <!-- Ombre -->
        <ellipse cx="100" cy="185" rx="55" ry="12" fill="#00000022"/>
        <!-- Robot kawaii cassé -->
        <g class="robot">
            <!-- Corps -->
            <rect x="55" y="95" width="90" height="75" rx="15" fill="#6B7280"/>
            <rect x="60" y="100" width="80" height="65" rx="12" fill="#4B5563"/>
            <!-- Panneau de contrôle -->
            <rect x="75" y="115" width="50" height="35" rx="5" fill="#374151"/>
            <circle cx="85" cy="125" r="4" fill="#EF4444"/>
            <circle cx="100" cy="125" r="4" fill="#F59E0B"/>
            <circle cx="115" cy="125" r="4" fill="#EF4444"/>
            <rect x="80" y="135" width="40" height="8" rx="2" fill="#1F2937"/>
            <!-- Bras -->
            <rect x="30" y="110" width="25" height="12" rx="6" fill="#9CA3AF"/>
            <rect x="145" y="110" width="25" height="12" rx="6" fill="#9CA3AF"/>
            <circle cx="25" cy="116" r="10" fill="#6B7280"/>
            <circle cx="175" cy="116" r="10" fill="#6B7280"/>
            <!-- Pieds -->
            <rect x="65" y="170" width="25" height="15" rx="5" fill="#374151"/>
            <rect x="110" y="170" width="25" height="15" rx="5" fill="#374151"/>
        </g>
        <!-- Tête -->
        <rect x="50" y="35" width="100" height="65" rx="20" fill="#9CA3AF"/>
        <rect x="55" y="40" width="90" height="55" rx="15" fill="#6B7280"/>
        <!-- Antenne -->
        <g class="antenna">
            <line x1="100" y1="35" x2="100" y2="15" stroke="#9CA3AF" stroke-width="6"/>
            <circle cx="100" cy="12" r="8" fill="#EF4444"/>
            <!-- Éclairs -->
            <path d="M90 8 L82 2" stroke="#FCD34D" stroke-width="3"/>
            <path d="M110 8 L118 2" stroke="#FCD34D" stroke-width="3"/>
            <path d="M100 5 L100 -5" stroke="#FCD34D" stroke-width="3"/>
        </g>
        <!-- Yeux X X -->
        <g class="eye-x" stroke="#EF4444" stroke-width="5" stroke-linecap="round">
            <line x1="70" y1="55" x2="85" y2="70"/>
            <line x1="85" y1="55" x2="70" y2="70"/>
            <line x1="115" y1="55" x2="130" y2="70"/>
            <line x1="130" y1="55" x2="115" y2="70"/>
        </g>
        <!-- Bouche erreur -->
        <path d="M75 85 L82 80 L89 88 L96 78 L103 88 L110 80 L117 85" stroke="#EF4444" stroke-width="4" fill="none" stroke-linecap="round"/>
        <!-- Fumée -->
        <ellipse cx="60" cy="25" rx="15" ry="10" fill="#9CA3AF" opacity="0.6" class="smoke"/>
        <ellipse cx="75" cy="15" rx="12" ry="8" fill="#D1D5DB" opacity="0.5" class="smoke" style="animation-delay:0.5s"/>
        <ellipse cx="140" cy="20" rx="14" ry="9" fill="#9CA3AF" opacity="0.6" class="smoke" style="animation-delay:0.3s"/>
        <!-- Étincelles -->
        <g class="spark">
            <polygon points="35,50 40,55 35,60 30,55" fill="#FCD34D"/>
            <polygon points="165,45 170,50 165,55 160,50" fill="#FCD34D"/>
        </g>
        <g class="spark" style="animation-delay:0.25s">
            <polygon points="25,70 30,75 25,80 20,75" fill="#F59E0B"/>
            <polygon points="175,65 180,70 175,75 170,70" fill="#F59E0B"/>
        </g>
        <!-- Message d'erreur -->
        <text x="100" y="145" font-size="8" fill="#EF4444" text-anchor="middle" font-family="monospace">ERR_ROBOT_BROKEN</text>
    </svg>''',

    502: '''<svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
        <!-- Deux serveurs qui ne communiquent pas -->
        <rect x="10" y="40" width="35" height="50" rx="5" fill="#4B5563"/>
        <rect x="75" y="40" width="35" height="50" rx="5" fill="#4B5563"/>
        <!-- LEDs serveur gauche (OK) -->
        <circle cx="20" cy="50" r="4" fill="#34D399"/>
        <circle cx="20" cy="62" r="4" fill="#34D399"/>
        <circle cx="20" cy="74" r="4" fill="#34D399"/>
        <!-- LEDs serveur droit (erreur) -->
        <circle cx="85" cy="50" r="4" fill="#EF4444"/>
        <circle cx="85" cy="62" r="4" fill="#EF4444"/>
        <circle cx="85" cy="74" r="4" fill="#F59E0B"/>
        <!-- Câble cassé -->
        <path d="M45 65 L52 65" stroke="#6B7280" stroke-width="4" stroke-linecap="round"/>
        <path d="M68 65 L75 65" stroke="#6B7280" stroke-width="4" stroke-linecap="round"/>
        <!-- Éclairs (déconnexion) -->
        <path d="M55 55 L60 62 L56 62 L62 72" stroke="#EF4444" stroke-width="2" fill="none"/>
        <path d="M62 58 L67 65 L63 65 L68 75" stroke="#F59E0B" stroke-width="2" fill="none"/>
        <!-- Visages sur serveurs -->
        <circle cx="30" cy="55" r="2" fill="white"/>
        <circle cx="38" cy="55" r="2" fill="white"/>
        <path d="M28 68 Q33 72 38 68" stroke="white" stroke-width="1.5" fill="none"/>
        <line x1="95" y1="53" x2="100" y2="57" stroke="white" stroke-width="2"/>
        <line x1="100" y1="53" x2="95" y2="57" stroke="white" stroke-width="2"/>
        <line x1="102" y1="53" x2="107" y2="57" stroke="white" stroke-width="2"/>
        <line x1="107" y1="53" x2="102" y2="57" stroke="white" stroke-width="2"/>
        <path d="M95 70 Q100 66 105 70" stroke="white" stroke-width="1.5" fill="none"/>
    </svg>''',

    503: '''<svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
        <!-- Serveur en réparation -->
        <rect x="30" y="25" width="60" height="70" rx="8" fill="#6B7280"/>
        <!-- Panneau "En travaux" -->
        <rect x="10" y="5" width="100" height="25" rx="4" fill="#FCD34D" stroke="#92400E" stroke-width="2"/>
        <text x="22" y="22" font-size="12" fill="#92400E" font-weight="bold">EN TRAVAUX</text>
        <!-- Bandes de chantier -->
        <rect x="30" y="95" width="60" height="15" fill="#FCD34D"/>
        <line x1="30" y1="95" x2="45" y2="110" stroke="#1F2937" stroke-width="3"/>
        <line x1="45" y1="95" x2="60" y2="110" stroke="#1F2937" stroke-width="3"/>
        <line x1="60" y1="95" x2="75" y2="110" stroke="#1F2937" stroke-width="3"/>
        <line x1="75" y1="95" x2="90" y2="110" stroke="#1F2937" stroke-width="3"/>
        <!-- LEDs (en attente) -->
        <circle cx="45" cy="45" r="5" fill="#F59E0B"/>
        <circle cx="60" cy="45" r="5" fill="#F59E0B"/>
        <circle cx="75" cy="45" r="5" fill="#F59E0B"/>
        <!-- Outils -->
        <g transform="translate(75, 60)">
            <rect x="0" y="0" width="25" height="8" rx="2" fill="#EF4444"/>
            <rect x="20" y="-5" width="15" height="18" rx="2" fill="#9CA3AF"/>
        </g>
        <!-- Clé à molette -->
        <g transform="translate(5, 55) rotate(-30)">
            <rect x="0" y="0" width="30" height="6" rx="2" fill="#9CA3AF"/>
            <circle cx="32" cy="3" r="8" stroke="#9CA3AF" stroke-width="4" fill="none"/>
        </g>
        <!-- Casque de chantier -->
        <ellipse cx="60" cy="78" rx="18" ry="8" fill="#FCD34D"/>
        <path d="M42 78 Q42 65 60 65 Q78 65 78 78" fill="#FCD34D"/>
    </svg>''',

    504: '''<svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
        <!-- Sablier presque vide -->
        <path d="M30 15 L90 15 L90 25 L70 55 L70 65 L90 95 L90 105 L30 105 L30 95 L50 65 L50 55 L30 25 Z" fill="none" stroke="#92400E" stroke-width="4"/>
        <!-- Verre du haut (vide) -->
        <path d="M35 20 L85 20 L85 27 L68 52 L52 52 L35 27 Z" fill="#FEF3C7"/>
        <!-- Verre du bas (plein) -->
        <path d="M52 68 L68 68 L85 93 L85 100 L35 100 L35 93 Z" fill="#F59E0B"/>
        <!-- Derniers grains qui tombent -->
        <circle cx="60" cy="58" r="2" fill="#F59E0B"/>
        <circle cx="60" cy="64" r="2" fill="#F59E0B"/>
        <!-- Toile d'araignée (attente longue) -->
        <path d="M25 30 Q20 35 25 40" stroke="#D1D5DB" stroke-width="1"/>
        <path d="M20 35 L30 35" stroke="#D1D5DB" stroke-width="1"/>
        <path d="M25 30 L25 40" stroke="#D1D5DB" stroke-width="1"/>
        <!-- Araignée mignonne -->
        <circle cx="18" cy="45" r="4" fill="#374151"/>
        <line x1="18" y1="45" x2="25" y2="40" stroke="#374151" stroke-width="1"/>
        <circle cx="16" cy="43" r="1" fill="white"/>
        <circle cx="20" cy="43" r="1" fill="white"/>
        <!-- Escargot qui attend -->
        <ellipse cx="95" cy="100" rx="12" ry="6" fill="#FCD34D"/>
        <path d="M100 94 Q108 85 100 80 Q92 85 100 94" fill="#92400E" stroke="#92400E" stroke-width="1"/>
        <circle cx="103" cy="92" r="1.5" fill="#1F2937"/>
        <circle cx="97" cy="92" r="1.5" fill="#1F2937"/>
        <!-- ZZZ -->
        <text x="85" y="70" font-size="10" fill="#9CA3AF" font-weight="bold">Z</text>
        <text x="92" y="63" font-size="8" fill="#9CA3AF" font-weight="bold">z</text>
    </svg>''',
}

# Couleurs AZALPLUS
BLEU_ROI = "#3454D1"
BLEU_ACCENT = "#6B9FFF"
BLEU_MARINE = "#1E3A8A"
ROUGE = "#EF4444"
ORANGE = "#F59E0B"

# Configuration des erreurs - Style AZALPLUS
ERROR_CONFIGS = {
    400: {
        "title": "Requête invalide",
        "message": "Le serveur n'a pas compris votre demande. Vérifiez les paramètres et réessayez.",
        "icon": SVG_ILLUSTRATIONS[400],
        "color": BLEU_ROI,
        "actions": [
            {"label": "Retour", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    401: {
        "title": "Authentification requise",
        "message": "Vous devez être connecté pour accéder à cette ressource. Identifiez-vous pour continuer.",
        "icon": SVG_ILLUSTRATIONS[401],
        "color": BLEU_MARINE,
        "actions": [
            {"label": "Se connecter", "url": "/login", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    403: {
        "title": "Accès refusé",
        "message": "Vous n'avez pas les permissions nécessaires pour accéder à cette ressource.",
        "icon": SVG_ILLUSTRATIONS[403],
        "color": BLEU_ROI,
        "actions": [
            {"label": "Retour", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    404: {
        "title": "Page introuvable",
        "message": "La page que vous recherchez n'existe pas ou a été déplacée.",
        "icon": SVG_ILLUSTRATIONS[404],
        "color": BLEU_ROI,
        "actions": [
            {"label": "Retour", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    405: {
        "title": "Méthode non autorisée",
        "message": "La méthode HTTP utilisée n'est pas supportée pour cette ressource.",
        "icon": SVG_ILLUSTRATIONS[405],
        "color": BLEU_ROI,
        "actions": [
            {"label": "Retour", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    408: {
        "title": "Délai dépassé",
        "message": "Le serveur a mis trop de temps à répondre. Veuillez réessayer.",
        "icon": SVG_ILLUSTRATIONS[408],
        "color": BLEU_MARINE,
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    422: {
        "title": "Données invalides",
        "message": "Les données soumises contiennent des erreurs. Vérifiez votre saisie.",
        "icon": SVG_ILLUSTRATIONS[422],
        "color": BLEU_ROI,
        "actions": [
            {"label": "Corriger", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    429: {
        "title": "Trop de requêtes",
        "message": "Vous avez effectué trop de requêtes. Patientez quelques instants avant de réessayer.",
        "icon": SVG_ILLUSTRATIONS[429],
        "color": BLEU_ROI,
        "actions": [
            {"label": "Patienter", "url": "javascript:setTimeout(()=>location.reload(),30000)", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    500: {
        "title": "Erreur serveur",
        "message": "Une erreur inattendue s'est produite. Notre équipe technique a été notifiée.",
        "icon": SVG_ILLUSTRATIONS[500],
        "color": BLEU_ROI,
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    502: {
        "title": "Passerelle invalide",
        "message": "Le serveur a reçu une réponse invalide d'un serveur en amont.",
        "icon": SVG_ILLUSTRATIONS[502],
        "color": BLEU_MARINE,
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    503: {
        "title": "Service indisponible",
        "message": "Le service est temporairement indisponible pour maintenance. Revenez bientôt.",
        "icon": SVG_ILLUSTRATIONS[503],
        "color": ORANGE,
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    504: {
        "title": "Délai de passerelle",
        "message": "Le serveur en amont n'a pas répondu à temps. Veuillez réessayer.",
        "icon": SVG_ILLUSTRATIONS[504],
        "color": BLEU_ROI,
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
}


def render_error_page(
    status_code: int,
    request: Request = None,
    custom_message: str = None,
    show_details: bool = True
) -> HTMLResponse:
    """
    Génère une page d'erreur HTML stylisée.

    Args:
        status_code: Code HTTP de l'erreur
        request: Objet Request FastAPI (optionnel)
        custom_message: Message personnalisé (optionnel)
        show_details: Afficher le chemin de la requête

    Returns:
        HTMLResponse avec la page d'erreur
    """
    config = ERROR_CONFIGS.get(status_code, {
        "title": "Erreur",
        "message": "Une erreur s'est produite.",
        "icon": "❌",
        "color": "#ef4444",
        "actions": [
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    })

    # Générer les boutons d'action
    actions_html = ""
    for action in config["actions"]:
        btn_class = "btn-primary" if action["style"] == "primary" else "btn-secondary"
        actions_html += f'<a href="{action["url"]}" class="btn {btn_class}">{action["label"]}</a>\n'

    # Charger et rendre le template
    try:
        template = env.get_template("base_error.html")
        html = template.render(
            error_code=status_code,
            error_title=config["title"],
            error_message=custom_message or config["message"],
            error_icon=config["icon"],
            header_color=config["color"],
            error_actions=actions_html,
            request_path=request.url.path if request else None,
            show_details=show_details
        )
    except Exception:
        # Fallback si le template n'existe pas
        html = generate_fallback_error_page(status_code, config, custom_message)

    return HTMLResponse(content=html, status_code=status_code)


def generate_fallback_error_page(status_code: int, config: dict, custom_message: str = None) -> str:
    """Génère une page d'erreur de secours sans template."""
    return f'''
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{status_code} - {config["title"]} | AZALPLUS</title>
        <style>
            body {{
                font-family: -apple-system, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                color: white;
                text-align: center;
            }}
            .error {{ max-width: 400px; padding: 20px; }}
            .code {{ font-size: 96px; font-weight: 800; opacity: 0.9; }}
            .title {{ font-size: 24px; margin: 20px 0; }}
            .message {{ opacity: 0.8; line-height: 1.6; }}
            .btn {{
                display: inline-block;
                margin-top: 30px;
                padding: 12px 24px;
                background: white;
                color: #667eea;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
            }}
            .btn:hover {{ transform: translateY(-2px); }}
        </style>
    </head>
    <body>
        <div class="error">
            <div class="code">{status_code}</div>
            <h1 class="title">{config["title"]}</h1>
            <p class="message">{custom_message or config["message"]}</p>
            <a href="/" class="btn">Retour à l'accueil</a>
        </div>
    </body>
    </html>
    '''


# Fonctions utilitaires pour les handlers FastAPI
def error_400(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(400, request, message)

def error_401(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(401, request, message)

def error_403(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(403, request, message)

def error_404(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(404, request, message)

def error_500(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(500, request, message)

def error_502(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(502, request, message)

def error_503(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(503, request, message)
