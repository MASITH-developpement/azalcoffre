# =============================================================================
# AZALPLUS - Générateur de Thème
# =============================================================================
"""
Génère le CSS automatiquement depuis config/theme.yml
UN SEUL FICHIER YAML = TOUT LE DESIGN
"""

import yaml
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import Response
import structlog

logger = structlog.get_logger()

# =============================================================================
# Theme Manager (avec Hot-Reload)
# =============================================================================
class ThemeManager:
    """Gère le thème depuis le fichier YAML avec hot-reload."""

    _theme: dict = {}
    _css_cache: str = ""
    _last_modified: float = 0
    _theme_path = Path("config/theme.yml")

    @classmethod
    def load(cls):
        """Charge le thème depuis config/theme.yml."""
        if not cls._theme_path.exists():
            logger.warning("theme_file_not_found")
            return

        with open(cls._theme_path, 'r', encoding='utf-8') as f:
            cls._theme = yaml.safe_load(f)

        cls._css_cache = cls._generate_css()
        cls._last_modified = cls._theme_path.stat().st_mtime
        logger.info("theme_loaded", name=cls._theme.get("nom", "Default"))

    @classmethod
    def get_css(cls) -> str:
        """Retourne le CSS généré (avec hot-reload automatique)."""
        # Vérifier si le fichier a été modifié
        if cls._theme_path.exists():
            current_mtime = cls._theme_path.stat().st_mtime
            if current_mtime > cls._last_modified:
                logger.info("theme_hot_reload", reason="file_modified")
                cls.load()

        if not cls._css_cache:
            cls.load()
        return cls._css_cache

    @classmethod
    def _generate_css(cls) -> str:
        """Génère le CSS depuis le thème YAML."""
        t = cls._theme
        c = t.get("couleurs", {})
        typo = t.get("typographie", {})
        esp = t.get("espacement", {})
        bord = t.get("bordures", {})
        omb = t.get("ombres", {})
        lay = t.get("layout", {})
        btn = t.get("boutons", {})
        inp = t.get("inputs", {})
        card = t.get("cartes", {})
        tbl = t.get("tables", {})
        badge = t.get("badges", {})
        login = t.get("login", {})
        bp = t.get("breakpoints", {})
        mobile = t.get("mobile", {})

        # Get breakpoint and mobile settings with defaults
        bp_mobile = bp.get("mobile", "480px")
        bp_tablet = bp.get("tablet", "768px")
        bp_desktop = bp.get("desktop", "1024px")
        bp_wide = bp.get("wide", "1440px")
        touch_min = mobile.get("touch_target_min", "44px")

        return f'''/* AZALPLUS - CSS Genere depuis theme.yml */
/* Mobile-First Responsive Design */

:root {{
    --primary: {c.get("primaire", "#0066FF")};
    --primary-dark: {c.get("primaire_fonce", "#0052CC")};
    --primary-light: {c.get("primaire_clair", "#E6F0FF")};
    --success: {c.get("succes", "#10B981")};
    --success-light: {c.get("succes_clair", "#D1FAE5")};
    --warning: {c.get("attention", "#F59E0B")};
    --warning-light: {c.get("attention_clair", "#FEF3C7")};
    --error: {c.get("erreur", "#EF4444")};
    --error-light: {c.get("erreur_clair", "#FEE2E2")};
    --info: {c.get("info", "#3B82F6")};
    --info-light: {c.get("info_clair", "#DBEAFE")};
    --white: {c.get("blanc", "#FFFFFF")};
    --gray-50: {c.get("gris_50", "#F9FAFB")};
    --gray-100: {c.get("gris_100", "#F3F4F6")};
    --gray-200: {c.get("gris_200", "#E5E7EB")};
    --gray-300: {c.get("gris_300", "#D1D5DB")};
    --gray-400: {c.get("gris_400", "#9CA3AF")};
    --gray-500: {c.get("gris_500", "#6B7280")};
    --gray-600: {c.get("gris_600", "#4B5563")};
    --gray-700: {c.get("gris_700", "#374151")};
    --gray-800: {c.get("gris_800", "#1F2937")};
    --gray-900: {c.get("gris_900", "#111827")};
    --sidebar-width: {lay.get("sidebar_largeur", "220px")};
    --header-height: {lay.get("header_hauteur", "56px")};
    --radius: {bord.get("rayon", "8px")};
    --radius-lg: {bord.get("rayon_grand", "12px")};
    --shadow-sm: {omb.get("petite", "0 1px 2px rgba(0,0,0,0.05)")};
    --shadow: {omb.get("moyenne", "0 4px 6px -1px rgba(0,0,0,0.1)")};
    /* Responsive breakpoints as CSS custom properties */
    --bp-mobile: {bp_mobile};
    --bp-tablet: {bp_tablet};
    --bp-desktop: {bp_desktop};
    --bp-wide: {bp_wide};
    /* Touch target minimum size */
    --touch-min: {touch_min};
    /* Curseur main jaune pour éléments cliquables */
    --cursor-yellow-hand: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='28' viewBox='0 0 28 28'%3E%3Cpath fill='%23FFD700' stroke='%23DAA520' stroke-width='1' d='M14.5 4c0-.8.7-1.5 1.5-1.5s1.5.7 1.5 1.5v7h1c.8 0 1.5.7 1.5 1.5v7c0 2.5-2 4.5-4.5 4.5h-3c-2.5 0-4.5-2-4.5-4.5v-4l-1.8-3.5c-.4-.8-.1-1.7.7-2.1.8-.4 1.7-.1 2.1.7l1.5 3V6.5c0-.8.7-1.5 1.5-1.5s1.5.7 1.5 1.5v5h1.5V4z'/%3E%3C/svg%3E") 8 0, pointer;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
    font-family: {typo.get("police", "sans-serif")};
    font-size: {typo.get("taille_base", "14px")};
    line-height: 1.5;
    color: var(--gray-900);
    background: var(--gray-50);
    -webkit-font-smoothing: antialiased;
    -webkit-tap-highlight-color: transparent;
    overflow-x: hidden;
}}

a {{ color: var(--primary); text-decoration: none; cursor: var(--cursor-yellow-hand); }}
a:hover {{ color: var(--primary-dark); }}

/* ==========================================================================
   CURSOR MAIN JAUNE - Éléments cliquables
   ========================================================================== */
a, button, [role="button"], [onclick], .btn, .nav-item, .stat-card,
.user-box, .card-header.clickable, .table tbody tr, .doc-tab,
.header-notif, .mobile-search-btn, .sidebar-close, .hamburger,
.checkbox-wrapper, .radio-wrapper, .badge.clickable, .dropdown-item,
input[type="checkbox"], input[type="radio"], input[type="submit"],
input[type="button"], select, .select, label[for], .clickable {{
    cursor: var(--cursor-yellow-hand);
}}

/* ==========================================================================
   MOBILE-FIRST LAYOUT (Base styles for mobile)
   ========================================================================== */

.app-layout {{
    display: flex;
    min-height: 100vh;
    flex-direction: column;
}}

/* Mobile Hamburger Menu Toggle */
.mobile-menu-toggle {{
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--touch-min);
    height: var(--touch-min);
    background: transparent;
    border: none;
    cursor: var(--cursor-yellow-hand);
    padding: 8px;
    border-radius: var(--radius);
    color: var(--gray-800);
    -webkit-tap-highlight-color: transparent;
}}
.mobile-menu-toggle:hover,
.mobile-menu-toggle:active {{
    background: var(--gray-200);
}}
.mobile-menu-toggle svg,
.mobile-menu-toggle i {{
    width: 24px;
    height: 24px;
    font-size: 24px;
}}

/* Hamburger icon lines */
.hamburger {{
    width: 22px;
    height: 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}}
.hamburger span {{
    display: block;
    height: 2px;
    width: 100%;
    background: var(--gray-800);
    border-radius: 1px;
    transition: all 0.3s ease;
}}
.hamburger.active span:nth-child(1) {{
    transform: translateY(7px) rotate(45deg);
}}
.hamburger.active span:nth-child(2) {{
    opacity: 0;
}}
.hamburger.active span:nth-child(3) {{
    transform: translateY(-7px) rotate(-45deg);
}}

/* Sidebar - Hidden by default on mobile */
.sidebar {{
    width: var(--sidebar-width);
    background: {c.get("sidebar_fond", "var(--gray-800)")};
    position: fixed;
    top: 0;
    left: calc(-1 * var(--sidebar-width));
    bottom: 0;
    display: flex;
    flex-direction: column;
    z-index: 1000;
    transition: left 0.3s ease, transform 0.3s ease;
    box-shadow: none;
}}

/* Sidebar open state */
.sidebar.open,
.sidebar-open .sidebar {{
    left: 0;
    box-shadow: 4px 0 20px rgba(0,0,0,0.15);
}}

/* Overlay when sidebar is open on mobile */
.sidebar-overlay {{
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.5);
    z-index: 999;
    opacity: 0;
    transition: opacity 0.3s ease;
}}
.sidebar-open .sidebar-overlay {{
    display: block;
    opacity: 1;
}}

/* Close button inside sidebar (mobile only) */
.sidebar-close {{
    display: flex;
    position: absolute;
    top: 8px;
    right: 8px;
    width: 36px;
    height: 36px;
    align-items: center;
    justify-content: center;
    background: rgba(255,255,255,0.1);
    border: none;
    border-radius: var(--radius);
    color: var(--white);
    cursor: var(--cursor-yellow-hand);
    font-size: 20px;
}}
.sidebar-close:hover {{
    background: rgba(255,255,255,0.2);
}}

.sidebar-logo {{
    height: var(--header-height);
    padding: 0 {esp.get("md", "16px")};
    padding-right: 48px;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    font-size: 14px;
    font-weight: 700;
    color: var(--white);
}}
.sidebar-logo-icon {{
    width: 24px;
    height: 24px;
    border-radius: 5px;
}}

.sidebar-nav {{
    flex: 1;
    padding: 12px 8px;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}}
.nav-section {{ margin-bottom: 16px; }}
.nav-title {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 8px 12px 4px;
    color: {c.get("sidebar_texte", "#94A3B8")};
}}

.nav-item {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    min-height: var(--touch-min);
    margin: 2px 0;
    border-radius: 6px;
    color: {c.get("sidebar_texte", "#94A3B8")};
    font-size: {typo.get("taille_petite", "13px")};
    font-weight: 500;
    transition: all 0.15s;
    -webkit-tap-highlight-color: transparent;
    cursor: var(--cursor-yellow-hand);
}}

.nav-item:hover {{ background: {c.get("sidebar_hover", "#334155")}; color: {c.get("sidebar_texte_actif", "#FFFFFF")}; }}
.nav-item:active {{ background: {c.get("sidebar_hover", "#334155")}; transform: scale(0.98); }}
.nav-item.active {{ background: var(--primary); color: var(--white); }}
.nav-icon {{ width: 20px; text-align: center; font-size: 16px; flex-shrink: 0; }}

.sidebar-user {{ padding: 12px; border-top: 1px solid rgba(255,255,255,0.1); }}
.user-box {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px;
    border-radius: 6px;
    min-height: var(--touch-min);
    cursor: var(--cursor-yellow-hand);
}}
.user-box:hover {{ background: {c.get("sidebar_hover", "#334155")}; }}
.user-avatar {{
    width: 36px; height: 36px;
    border-radius: 50%;
    background: var(--primary);
    color: var(--white);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    font-weight: 600;
    flex-shrink: 0;
}}
.user-info {{ overflow: hidden; }}
.user-name {{ font-size: 13px; font-weight: 500; color: var(--white); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.user-email {{ font-size: 11px; color: {c.get("sidebar_texte", "#94A3B8")}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}

/* Main wrapper - Full width on mobile */
.main-wrapper {{
    flex: 1;
    margin-left: 0;
    min-width: 0;
    width: 100%;
}}

.main-header {{
    height: var(--header-height);
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
    border-bottom: none;
    padding: 0 {esp.get("md", "16px")};
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    position: sticky;
    top: 0;
    z-index: 50;
}}

.header-left {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}}

.page-title {{
    font-size: {typo.get("taille_grande", "16px")};
    font-weight: 600;
    color: var(--gray-800);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

/* Search - Hidden on mobile, shown on tablet+ */
.header-search {{
    display: none;
    align-items: center;
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: var(--radius);
    padding: 8px 12px;
    width: 100%;
    max-width: 280px;
}}
.header-search input {{
    border: none;
    background: transparent;
    outline: none;
    font-size: 14px;
    width: 100%;
    color: var(--white);
    min-height: 24px;
}}
.header-search input::placeholder {{ color: rgba(255,255,255,0.6); }}

/* Mobile search button */
.mobile-search-btn {{
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--touch-min);
    height: var(--touch-min);
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: var(--radius);
    color: var(--white);
    cursor: var(--cursor-yellow-hand);
}}

.header-actions {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
}}

.header-notif {{
    position: relative;
    width: var(--touch-min);
    height: var(--touch-min);
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: var(--radius);
    cursor: var(--cursor-yellow-hand);
    color: var(--white);
}}
.header-notif:hover {{ background: rgba(255,255,255,0.25); }}
.notif-badge {{
    position: absolute;
    top: 4px;
    right: 4px;
    background: var(--error);
    color: white;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 5px;
    border-radius: 10px;
    min-width: 18px;
    text-align: center;
}}

.main-content {{
    padding: {esp.get("md", "16px")};
    max-width: 100%;
    overflow-x: hidden;
}}

/* ==========================================================================
   CARDS - Mobile optimized
   ========================================================================== */
.card {{
    background: var(--gray-100);
    border-radius: {card.get("rayon", "12px")};
    border: 1px solid var(--gray-200);
    margin-bottom: {esp.get("md", "16px")};
    box-shadow: var(--shadow-sm);
}}
.card-header {{
    padding: {esp.get("md", "16px")};
    border-bottom: 1px solid var(--gray-200);
    display: flex;
    flex-direction: column;
    gap: 12px;
}}
.card-header-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
}}
.card-title {{ font-size: 15px; font-weight: 600; color: var(--gray-800); }}
.card-body {{ padding: {esp.get("md", "16px")}; }}

/* ==========================================================================
   BUTTONS - Touch-friendly (min 44px tap targets)
   ========================================================================== */
.btn {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 12px 16px;
    min-height: var(--touch-min);
    font-size: {typo.get("taille_base", "14px")};
    font-weight: 500;
    border-radius: {btn.get("rayon", "6px")};
    border: none;
    cursor: var(--cursor-yellow-hand);
    transition: all 0.15s;
    -webkit-tap-highlight-color: transparent;
    touch-action: manipulation;
    white-space: nowrap;
}}
.btn-primary {{ background: var(--primary); color: var(--white); }}
.btn-primary:hover {{ background: var(--primary-dark); }}
.btn-primary:active {{ transform: scale(0.98); }}
.btn-secondary {{ background: var(--gray-100); color: var(--gray-900); border: 1px solid var(--gray-300); }}
.btn-secondary:hover {{ background: var(--gray-200); }}
.btn-success {{ background: var(--success); color: var(--white); }}
.btn-danger {{ background: var(--error); color: var(--white); }}
/* Bouton blanc pour header bleu */
.btn-white {{ background: var(--white); color: var(--primary); font-weight: 600; }}
.btn-white:hover {{ background: rgba(255,255,255,0.9); }}
/* Bouton header (sur fond bleu gradient) */
.main-header .btn-primary {{
    background: var(--white);
    color: var(--primary);
    font-weight: 600;
}}
.main-header .btn-primary:hover {{
    background: rgba(255,255,255,0.9);
}}
.btn-sm {{ padding: 8px 12px; font-size: 13px; min-height: 36px; }}
.btn-lg {{ padding: 14px 24px; font-size: 15px; min-height: 52px; }}

/* Button group - Stack on mobile */
.btn-group {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
}}
.btn-group .btn {{
    width: 100%;
}}

/* ==========================================================================
   FORMS - Stacked layout on mobile
   ========================================================================== */
.form-group {{ margin-bottom: 12px; }}
.label {{
    display: block;
    font-size: 12px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--gray-500);
    margin-bottom: 8px;
}}
.input, .select, textarea, .o-field-char, .o-field-text {{
    width: 100%;
    padding: 16px 20px;
    min-height: 56px;
    font-family: inherit;
    font-size: 15px;
    font-weight: 500;
    border: none;
    border-radius: 14px;
    background: var(--gray-100);
    color: var(--gray-800);
    box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.08);
    transition: all 0.25s ease;
    -webkit-appearance: none;
    appearance: none;
}}
.input:hover, .select:hover, textarea:hover, .o-field-char:hover, .o-field-text:hover {{
    background: var(--gray-50);
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.05), 0 4px 12px rgba(52, 84, 209, 0.1);
}}
.input:focus, .select:focus, textarea:focus, .o-field-char:focus, .o-field-text:focus {{
    outline: none;
    background: var(--white);
    box-shadow: inset 0 0 0 2px var(--primary), 0 4px 20px rgba(52, 84, 209, 0.15);
}}
.input::placeholder, textarea::placeholder, .o-field-char::placeholder, .o-field-text::placeholder {{
    color: var(--gray-400);
    font-weight: 400;
}}

/* Select arrow */
.select {{
    background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
    background-position: right 0 center;
    background-repeat: no-repeat;
    background-size: 14px;
    padding-right: 20px;
    cursor: pointer;
}}

/* Form grid - Single column on mobile */
.form-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: {esp.get("md", "16px")};
}}

/* Form row - Stack on mobile */
.form-row {{
    display: flex;
    flex-direction: column;
    gap: {esp.get("md", "16px")};
}}

/* Checkbox and radio - Touch friendly */
.checkbox-wrapper,
.radio-wrapper {{
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: var(--touch-min);
    padding: 8px 0;
    cursor: var(--cursor-yellow-hand);
}}
.checkbox-wrapper input[type="checkbox"],
.radio-wrapper input[type="radio"] {{
    width: 20px;
    height: 20px;
    flex-shrink: 0;
}}

/* ==========================================================================
   TABLES - Card view on mobile
   ========================================================================== */
.table-wrapper {{
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}}

.table {{
    width: 100%;
    border-collapse: collapse;
    min-width: 600px;
}}
.table th {{
    text-align: left;
    padding: {tbl.get("padding", "12px 14px")};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: var(--gray-500);
    background: {tbl.get("header_fond", "var(--gray-50)")};
    border-bottom: 1px solid var(--gray-200);
    white-space: nowrap;
}}
.table td {{
    padding: {tbl.get("padding", "12px 14px")};
    border-bottom: 1px solid var(--gray-200);
    color: var(--gray-800);
    font-size: {typo.get("taille_petite", "13px")};
}}
.table tbody tr {{
    cursor: var(--cursor-yellow-hand);
    transition: all 0.15s;
    background: var(--gray-100);
}}
.table tbody tr:hover {{
    background: var(--gray-200);
    transform: translateX(2px);
}}
.table tbody tr:active {{ background: var(--gray-200); }}

/* Responsive table - Card view on mobile */
.table-responsive {{
    display: block;
}}
.table-responsive thead {{
    display: none;
}}
.table-responsive tbody {{
    display: flex;
    flex-direction: column;
    gap: 12px;
}}
.table-responsive tr {{
    display: flex;
    flex-direction: column;
    background: var(--gray-100);
    border: 1px solid var(--gray-200);
    border-radius: var(--radius);
    padding: {esp.get("md", "16px")};
}}
.table-responsive td {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 8px 0;
    border-bottom: 1px solid var(--gray-100);
}}
.table-responsive td:last-child {{
    border-bottom: none;
}}
.table-responsive td::before {{
    content: attr(data-label);
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    color: var(--gray-500);
    flex-shrink: 0;
    margin-right: 16px;
}}

/* ==========================================================================
   BADGES - Slightly larger on mobile
   ========================================================================== */
.badge {{
    display: inline-flex;
    align-items: center;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 500;
    border-radius: {badge.get("rayon", "4px")};
}}
/* Badges avec fond semi-transparent (style vidéo démo) */
.badge-gray {{ background: rgba(100, 116, 139, 0.2); color: #94a3b8; }}
.badge-blue, .badge-primary {{ background: rgba(52, 84, 209, 0.2); color: #6B9FFF; }}
.badge-green {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
.badge-yellow {{ background: rgba(251, 191, 36, 0.2); color: #fbbf24; }}
.badge-red {{ background: rgba(239, 68, 68, 0.2); color: #f87171; }}

.status-brouillon {{ background: rgba(100, 116, 139, 0.2); color: #94a3b8; }}
.status-envoye, .status-planifie {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; }}
.status-accepte, .status-valide, .status-termine {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
.status-refuse, .status-annule {{ background: rgba(239, 68, 68, 0.2); color: #f87171; }}
.status-en-cours, .status-a-planifier {{ background: rgba(251, 191, 36, 0.2); color: #fbbf24; }}
.status-en-cours, .status-a-planifier {{ background: var(--warning-light); color: var(--warning); }}

/* ==========================================================================
   STATS CARDS - 2 columns on mobile
   ========================================================================== */
.stats-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: {esp.get("lg", "24px")};
}}
.stat-card {{
    background: var(--gray-100);
    border-radius: var(--radius-lg);
    border: 1px solid var(--gray-200);
    padding: {esp.get("md", "16px")};
    text-decoration: none;
    transition: all 0.2s;
    cursor: var(--cursor-yellow-hand);
}}
.stat-card:hover {{ box-shadow: var(--shadow); border-color: var(--primary); }}
.stat-card:active {{ transform: scale(0.98); }}
.stat-icon {{
    width: 36px; height: 36px;
    border-radius: var(--radius);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    margin-bottom: 10px;
}}
/* Stat icons avec fond semi-transparent (style vidéo démo) */
.stat-icon.blue {{ background: rgba(52, 84, 209, 0.15); color: #6B9FFF; }}
.stat-icon.green {{ background: rgba(16, 185, 129, 0.15); color: #34d399; }}
.stat-icon.yellow {{ background: rgba(251, 191, 36, 0.15); color: #fbbf24; }}
.stat-icon.red {{ background: rgba(239, 68, 68, 0.15); color: #f87171; }}
.stat-value {{ font-size: 20px; font-weight: 700; color: var(--gray-900); }}
.stat-label {{ font-size: 11px; color: var(--gray-500); margin-top: 2px; }}

/* ==========================================================================
   LIST ITEMS - Style vidéo démo AZALPLUS
   ========================================================================== */
.list-container {{
    background: var(--gray-100);
    border-radius: var(--radius-lg);
    overflow: hidden;
}}
.list-item {{
    display: flex;
    align-items: center;
    padding: 15px 20px;
    border-bottom: 1px solid var(--gray-50);
    gap: 15px;
    transition: all 0.15s;
    cursor: var(--cursor-yellow-hand);
}}
.list-item:last-child {{
    border-bottom: none;
}}
.list-item:hover {{
    background: var(--gray-200);
}}
.list-item-info {{
    display: flex;
    flex-direction: column;
    gap: 3px;
    flex: 1;
}}
.list-item-title {{
    color: var(--gray-900);
    font-weight: 600;
    font-size: 14px;
}}
.list-item-subtitle {{
    color: var(--gray-500);
    font-size: 12px;
}}
.list-item-amount {{
    color: var(--gray-900);
    font-weight: 600;
    font-size: 14px;
}}
.list-item.highlight {{
    background: rgba(52, 84, 209, 0.1);
    border: 1px dashed var(--primary);
}}

/* ==========================================================================
   EMPTY STATE
   ========================================================================== */
.empty-state {{ text-align: center; padding: 40px 20px; }}
.empty-icon {{ font-size: 48px; opacity: 0.4; margin-bottom: 16px; }}
.empty-title {{ font-size: 16px; font-weight: 600; color: var(--gray-900); margin-bottom: 6px; }}
.empty-text {{ font-size: 14px; color: var(--gray-500); margin-bottom: 16px; }}

/* ==========================================================================
   LOGIN - Responsive
   ========================================================================== */
.login-page {{
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: {login.get("fond", "linear-gradient(135deg, #0066FF 0%, #0052CC 100%)")};
    padding: {esp.get("md", "16px")};
}}
.login-box {{
    width: 100%;
    max-width: {login.get("carte_largeur", "380px")};
    background: var(--gray-100);
    border-radius: {login.get("carte_rayon", "12px")};
    box-shadow: 0 20px 60px rgba(0,0,0,0.4);
}}
.login-header {{ padding: 24px 20px 16px; text-align: center; }}
.login-logo {{ font-size: 22px; font-weight: 700; color: var(--primary-light); }}
.login-subtitle {{ font-size: 13px; color: var(--gray-600); margin-top: 4px; }}
.login-body {{ padding: 0 20px 24px; }}
.login-error {{
    background: var(--error-light);
    color: var(--error);
    padding: 12px;
    border-radius: 6px;
    font-size: 13px;
    margin-bottom: 16px;
    display: none;
}}
.login-body .btn-primary {{ width: 100%; padding: 14px; min-height: 48px; }}
.password-field {{ position: relative; }}
.password-toggle {{
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    color: var(--gray-400);
    cursor: var(--cursor-yellow-hand);
    font-size: 16px;
    padding: 8px;
    min-width: var(--touch-min);
    min-height: var(--touch-min);
    display: flex;
    align-items: center;
    justify-content: center;
}}

/* ==========================================================================
   DOCUMENT FORM - Mobile optimized
   ========================================================================== */
.doc-section {{ margin-bottom: 20px; }}
.doc-row {{
    display: grid;
    grid-template-columns: 1fr;
    gap: {esp.get("md", "16px")};
    margin-bottom: 12px;
}}
.doc-field {{ }}
.doc-tabs {{
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--gray-200);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}}
.doc-tab {{
    padding: 12px 16px;
    min-height: var(--touch-min);
    background: transparent;
    border: none;
    font-size: 13px;
    font-weight: 500;
    color: var(--gray-500);
    cursor: var(--cursor-yellow-hand);
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    white-space: nowrap;
    flex-shrink: 0;
}}
.doc-tab:hover {{ color: var(--gray-700); }}
.doc-tab.active {{ color: var(--primary-light); border-bottom-color: var(--primary); }}
.doc-actions {{
    display: flex;
    flex-direction: column;
    gap: 8px;
}}
.doc-totals {{ padding: 16px 0; border-top: 1px solid var(--gray-200); }}
.doc-total-row {{
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
}}
.doc-total-row span:last-child {{ font-weight: 500; }}

/* Form fields container - 2 columns layout */
.form-fields-container {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
}}

/* ==========================================================================
   UTILITIES
   ========================================================================== */
.flex {{ display: flex; }}
.flex-col {{ flex-direction: column; }}
.flex-wrap {{ flex-wrap: wrap; }}
.items-center {{ align-items: center; }}
.items-start {{ align-items: flex-start; }}
.justify-between {{ justify-content: space-between; }}
.justify-center {{ justify-content: center; }}
.justify-end {{ justify-content: flex-end; }}
.gap-1 {{ gap: 4px; }}
.gap-2 {{ gap: 8px; }}
.gap-3 {{ gap: 12px; }}
.gap-4 {{ gap: 16px; }}
.text-xs {{ font-size: 11px; }}
.text-sm {{ font-size: 13px; }}
.text-base {{ font-size: 14px; }}
.text-lg {{ font-size: 16px; }}
.text-muted {{ color: var(--gray-500); }}
.font-medium {{ font-weight: 500; }}
.font-bold {{ font-weight: 600; }}
.mb-2 {{ margin-bottom: 8px; }}
.mb-4 {{ margin-bottom: 16px; }}
.mb-6 {{ margin-bottom: 24px; }}
.mt-2 {{ margin-top: 8px; }}
.mt-4 {{ margin-top: 16px; }}
.text-center {{ text-align: center; }}
.text-right {{ text-align: right; }}
.hidden {{ display: none !important; }}
.truncate {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.w-full {{ width: 100%; }}

/* Mobile-only utilities */
.mobile-only {{ display: block; }}
.tablet-only {{ display: none; }}
.desktop-only {{ display: none; }}

/* Hide on mobile */
.hide-mobile {{ display: none !important; }}

/* ==========================================================================
   TABLET BREAKPOINT (768px+)
   ========================================================================== */
@media (min-width: {bp_tablet}) {{
    /* Show search on tablet */
    .header-search {{
        display: flex;
    }}
    .mobile-search-btn {{
        display: none;
    }}

    /* Main content padding */
    .main-content {{
        padding: {esp.get("lg", "24px")};
    }}

    /* Card header inline */
    .card-header {{
        flex-direction: row;
        align-items: center;
        padding: {esp.get("md", "16px")} {card.get("padding", "20px")};
    }}

    /* Button group inline */
    .btn-group {{
        flex-direction: row;
        width: auto;
    }}
    .btn-group .btn {{
        width: auto;
    }}

    /* Form grid 2 columns */
    .form-grid {{
        grid-template-columns: 1fr 1fr;
    }}

    /* Form row inline */
    .form-row {{
        flex-direction: row;
    }}

    /* Doc row 2 columns */
    .doc-row {{
        grid-template-columns: 1fr 1fr;
    }}

    /* Form fields container 2 columns */
    .form-fields-container {{
        grid-template-columns: 1fr 1fr;
    }}

    /* Doc actions inline */
    .doc-actions {{
        flex-direction: row;
    }}

    /* Stats 3 columns */
    .stats-row {{
        grid-template-columns: repeat(3, 1fr);
        gap: {esp.get("md", "16px")};
    }}
    .stat-icon {{
        width: 40px;
        height: 40px;
        font-size: 20px;
    }}
    .stat-value {{
        font-size: 22px;
    }}
    .stat-label {{
        font-size: 12px;
    }}

    /* Login box wider padding */
    .login-header {{
        padding: 28px 28px 20px;
    }}
    .login-body {{
        padding: 0 28px 28px;
    }}

    /* Utilities */
    .mobile-only {{ display: none; }}
    .tablet-only {{ display: block; }}
    .hide-mobile {{ display: block !important; }}
    .hide-tablet {{ display: none !important; }}
}}

/* ==========================================================================
   DESKTOP BREAKPOINT (1024px+)
   ========================================================================== */
@media (min-width: {bp_desktop}) {{
    /* Layout with persistent sidebar */
    .app-layout {{
        flex-direction: row;
    }}

    /* Hide mobile menu toggle */
    .mobile-menu-toggle {{
        display: none;
    }}

    /* Sidebar always visible */
    .sidebar {{
        left: 0;
        box-shadow: none;
    }}
    .sidebar-close {{
        display: none;
    }}
    .sidebar-overlay {{
        display: none !important;
    }}
    .sidebar-logo {{
        padding-right: {esp.get("md", "16px")};
    }}

    /* Nav items slightly smaller padding on desktop */
    .nav-item {{
        padding: 9px 12px;
        min-height: 38px;
    }}

    /* Main wrapper with sidebar margin */
    .main-wrapper {{
        margin-left: var(--sidebar-width);
    }}

    /* Header wider padding */
    .main-header {{
        padding: 0 {esp.get("lg", "24px")};
    }}

    /* Table normal view */
    .table-responsive {{
        display: table;
    }}
    .table-responsive thead {{
        display: table-header-group;
    }}
    .table-responsive tbody {{
        display: table-row-group;
    }}
    .table-responsive tr {{
        display: table-row;
        background: transparent;
        border: none;
        border-radius: 0;
        padding: 0;
    }}
    .table-responsive td {{
        display: table-cell;
        padding: {tbl.get("padding", "12px 14px")};
        border-bottom: 1px solid var(--gray-100);
    }}
    .table-responsive td::before {{
        display: none;
    }}

    /* Stats 4 columns */
    .stats-row {{
        grid-template-columns: repeat(4, 1fr);
    }}

    /* Buttons smaller */
    .btn {{
        padding: {btn.get("padding", "8px 14px")};
        min-height: 36px;
        font-size: {typo.get("taille_petite", "13px")};
    }}
    .btn-lg {{
        padding: 12px 20px;
        min-height: 44px;
    }}

    /* Inputs - Style Premium */
    .input, .select, textarea, .o-field-char, .o-field-text {{
        padding: 16px 20px;
        min-height: 56px;
        font-size: 15px;
    }}

    /* Card body padding */
    .card-body {{
        padding: {card.get("padding", "20px")};
    }}

    /* Doc total row */
    .doc-total-row {{
        justify-content: flex-end;
        gap: 32px;
    }}
    .doc-total-row span:last-child {{
        min-width: 100px;
        text-align: right;
    }}

    /* Utilities */
    .tablet-only {{ display: none; }}
    .desktop-only {{ display: block; }}
    .hide-desktop {{ display: none !important; }}
}}

/* ==========================================================================
   WIDE SCREEN BREAKPOINT (1440px+)
   ========================================================================== */
@media (min-width: {bp_wide}) {{
    /* Stats auto-fit */
    .stats-row {{
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    }}

    /* Main content max width */
    .main-content {{
        max-width: {lay.get("contenu_max", "1200px")};
        margin: 0 auto;
        padding: {esp.get("xl", "32px")};
    }}
}}

/* ==========================================================================
   SMALL MOBILE BREAKPOINT (< 480px) - iPhone SE, etc.
   ========================================================================== */
@media (max-width: {bp_mobile}) {{
    /* Smaller padding */
    .main-content {{
        padding: 12px;
    }}

    /* Stats single column */
    .stats-row {{
        grid-template-columns: 1fr;
        gap: 10px;
    }}
    .stat-card {{
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px;
    }}
    .stat-icon {{
        margin-bottom: 0;
        width: 40px;
        height: 40px;
    }}
    .stat-content {{
        flex: 1;
    }}
    .stat-value {{
        font-size: 18px;
    }}

    /* Card compact */
    .card-header,
    .card-body {{
        padding: 12px;
    }}

    /* Page title smaller */
    .page-title {{
        font-size: 14px;
    }}

    /* Login compact */
    .login-page {{
        padding: 12px;
    }}
    .login-header {{
        padding: 20px 16px 12px;
    }}
    .login-body {{
        padding: 0 16px 20px;
    }}
    .login-logo {{
        font-size: 20px;
    }}

    /* Form group spacing */
    .form-group {{
        margin-bottom: 12px;
    }}
}}

/* ==========================================================================
   PRINT BUTTON STYLES (Screen)
   ========================================================================== */
.print-actions {{
    display: flex;
    gap: 8px;
    align-items: center;
}}

.btn-print {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 500;
    border-radius: 6px;
    border: 1px solid var(--gray-300);
    background: var(--white);
    color: var(--gray-700);
    cursor: var(--cursor-yellow-hand);
    transition: all 0.15s;
}}

.btn-print:hover {{
    background: var(--gray-50);
    border-color: var(--gray-400);
}}

.btn-print-primary {{
    background: var(--primary);
    color: var(--white);
    border-color: var(--primary);
}}

.btn-print-primary:hover {{
    background: var(--primary-dark);
}}

.print-icon {{
    font-size: 16px;
}}

/* Print-only elements - Hidden on screen */
.print-only {{
    display: none !important;
}}

/* Screen-only elements - Hidden on print */
@media print {{
    .screen-only,
    .no-print {{
        display: none !important;
    }}
}}

/* ==========================================================================
   PRINT STYLES - Optimized for A4 Paper
   ========================================================================== */
@media print {{
    /* =========================================================================
       Page Setup - A4 Paper (210mm x 297mm)
       ========================================================================= */
    @page {{
        size: A4;
        margin: 15mm 12mm 20mm 12mm;
    }}

    @page :first {{
        margin-top: 15mm;
    }}

    /* =========================================================================
       Hide Non-Essential Elements
       ========================================================================= */
    .sidebar,
    .main-header,
    .header-search,
    .header-actions,
    .header-notif,
    .sidebar-nav,
    .sidebar-user,
    .sidebar-logo,
    .sidebar-close,
    .sidebar-overlay,
    .nav-section,
    .nav-item,
    .mobile-menu-toggle,
    .btn:not(.btn-print-only),
    .btn-primary:not(.btn-print-only),
    .btn-secondary:not(.btn-print-only),
    .print-actions,
    .no-print,
    .screen-only,
    .upload-zone,
    .doc-actions,
    .card-footer,
    form button[type="submit"],
    .notification,
    #doc-notification,
    .notif-badge,
    [onclick]:not(.print-only),
    .pagination,
    .filters,
    .search-form-large,
    .empty-icon,
    .header-left,
    .mobile-search-btn {{
        display: none !important;
    }}

    /* =========================================================================
       Reset Layout for Print
       ========================================================================= */
    html, body {{
        width: 210mm;
        height: auto;
        margin: 0 !important;
        padding: 0 !important;
        font-size: 11pt !important;
        line-height: 1.4 !important;
        color: #000 !important;
        background: #fff !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }}

    .app-layout {{
        display: block !important;
        min-height: auto !important;
    }}

    .main-wrapper {{
        margin-left: 0 !important;
        width: 100% !important;
    }}

    .main-content {{
        padding: 0 !important;
        max-width: none !important;
    }}

    /* =========================================================================
       Typography for Print
       ========================================================================= */
    h1, h2, h3, h4, h5, h6 {{
        color: #000 !important;
        page-break-after: avoid;
        page-break-inside: avoid;
    }}

    .page-title {{
        font-size: 18pt !important;
        margin-bottom: 12pt !important;
        color: #000 !important;
    }}

    .card-title {{
        font-size: 14pt !important;
        color: #000 !important;
    }}

    p, li, td, th {{
        color: #000 !important;
        font-size: 10pt !important;
    }}

    /* =========================================================================
       Links - Show URLs
       ========================================================================= */
    a {{
        color: #000 !important;
        text-decoration: underline !important;
    }}

    a[href^="http"]:after,
    a[href^="mailto"]:after {{
        content: " (" attr(href) ")";
        font-size: 8pt;
        color: #666;
        word-wrap: break-word;
    }}

    a[href^="#"]:after,
    a[href^="javascript"]:after,
    a.no-print-url:after {{
        content: "" !important;
    }}

    /* =========================================================================
       Cards and Containers
       ========================================================================= */
    .card {{
        background: #fff !important;
        border: 1px solid #ddd !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        page-break-inside: avoid;
        margin-bottom: 12pt;
    }}

    .card-header {{
        background: #f5f5f5 !important;
        border-bottom: 1px solid #ddd !important;
        padding: 8pt 12pt !important;
    }}

    .card-body {{
        padding: 12pt !important;
    }}

    .stats-row {{
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 8pt !important;
    }}

    .stat-card {{
        flex: 1 !important;
        min-width: 100pt !important;
        background: #fff !important;
        border: 1px solid #ddd !important;
        padding: 8pt !important;
        box-shadow: none !important;
    }}

    .stat-icon {{
        display: none !important;
    }}

    .stat-value {{
        font-size: 14pt !important;
        font-weight: bold !important;
        color: #000 !important;
    }}

    .stat-label {{
        font-size: 9pt !important;
        color: #666 !important;
    }}

    /* =========================================================================
       Tables - Optimized for Print
       ========================================================================= */
    .table-wrapper {{
        overflow: visible !important;
    }}

    .table {{
        width: 100% !important;
        border-collapse: collapse !important;
        page-break-inside: auto !important;
        min-width: 0 !important;
    }}

    .table thead {{
        display: table-header-group !important;
    }}

    .table tfoot {{
        display: table-footer-group !important;
    }}

    .table tr {{
        page-break-inside: avoid !important;
        page-break-after: auto !important;
    }}

    .table th {{
        background: #f0f0f0 !important;
        color: #000 !important;
        font-weight: bold !important;
        border: 1px solid #ccc !important;
        padding: 6pt 8pt !important;
        font-size: 9pt !important;
        text-transform: uppercase !important;
    }}

    .table td {{
        border: 1px solid #ddd !important;
        padding: 6pt 8pt !important;
        color: #000 !important;
        font-size: 9pt !important;
        vertical-align: top !important;
    }}

    .table tbody tr:nth-child(even) {{
        background: #fafafa !important;
    }}

    .table tbody tr:hover {{
        background: inherit !important;
    }}

    /* Table responsive - Reset to normal table for print */
    .table-responsive {{
        display: table !important;
    }}
    .table-responsive thead {{
        display: table-header-group !important;
    }}
    .table-responsive tbody {{
        display: table-row-group !important;
    }}
    .table-responsive tr {{
        display: table-row !important;
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
    }}
    .table-responsive td {{
        display: table-cell !important;
    }}
    .table-responsive td::before {{
        display: none !important;
    }}

    /* =========================================================================
       Badges - Print-friendly
       ========================================================================= */
    .badge {{
        background: transparent !important;
        border: 1px solid #999 !important;
        color: #000 !important;
        padding: 2pt 6pt !important;
        font-size: 8pt !important;
        border-radius: 2pt !important;
    }}

    .badge-gray,
    .badge-blue,
    .badge-green,
    .badge-yellow,
    .badge-red {{
        background: transparent !important;
        color: #000 !important;
    }}

    .status-brouillon,
    .status-envoye,
    .status-planifie,
    .status-accepte,
    .status-valide,
    .status-termine,
    .status-refuse,
    .status-annule,
    .status-en-cours,
    .status-a-planifier {{
        background: transparent !important;
        color: #000 !important;
        border: 1px solid #666 !important;
    }}

    /* =========================================================================
       Forms - Print-friendly
       ========================================================================= */
    .form-group {{
        margin-bottom: 8pt !important;
        page-break-inside: avoid !important;
    }}

    .label {{
        font-weight: bold !important;
        color: #000 !important;
        font-size: 9pt !important;
    }}

    .input,
    .select,
    textarea {{
        border: 1px solid #ccc !important;
        background: #fff !important;
        color: #000 !important;
        padding: 4pt 6pt !important;
        font-size: 10pt !important;
        min-height: auto !important;
    }}

    /* =========================================================================
       Document Styles (Devis/Factures)
       ========================================================================= */
    .doc-section {{
        margin-bottom: 12pt !important;
        page-break-inside: avoid !important;
    }}

    .doc-row {{
        display: flex !important;
        gap: 16pt !important;
        margin-bottom: 8pt !important;
    }}

    .doc-field {{
        flex: 1 !important;
    }}

    .doc-tabs {{
        display: none !important;
    }}

    .doc-totals {{
        page-break-inside: avoid !important;
        border-top: 2pt solid #000 !important;
        padding-top: 8pt !important;
        margin-top: 12pt !important;
    }}

    .doc-total-row {{
        display: flex !important;
        justify-content: flex-end !important;
        gap: 24pt !important;
        padding: 4pt 0 !important;
        font-size: 10pt !important;
    }}

    .doc-total-row:last-child {{
        font-weight: bold !important;
        font-size: 12pt !important;
        border-top: 1pt solid #ccc !important;
        padding-top: 6pt !important;
        margin-top: 4pt !important;
    }}

    /* =========================================================================
       Page Breaks
       ========================================================================= */
    .page-break {{
        page-break-before: always !important;
    }}

    .page-break-after {{
        page-break-after: always !important;
    }}

    .avoid-break {{
        page-break-inside: avoid !important;
    }}

    h1, h2, h3 {{
        page-break-after: avoid !important;
    }}

    table, figure, img {{
        page-break-inside: avoid !important;
    }}

    /* =========================================================================
       Print Header (Company Info) - Show when printing
       ========================================================================= */
    .print-header {{
        display: block !important;
        margin-bottom: 16pt !important;
        padding-bottom: 12pt !important;
        border-bottom: 2pt solid #000 !important;
    }}

    .print-header-content {{
        display: flex !important;
        justify-content: space-between !important;
        align-items: flex-start !important;
    }}

    .print-company {{
        flex: 1 !important;
    }}

    .print-company-name {{
        font-size: 16pt !important;
        font-weight: bold !important;
        color: #000 !important;
        margin-bottom: 4pt !important;
    }}

    .print-company-details {{
        font-size: 9pt !important;
        color: #333 !important;
        line-height: 1.4 !important;
    }}

    .print-doc-info {{
        text-align: right !important;
    }}

    .print-doc-type {{
        font-size: 18pt !important;
        font-weight: bold !important;
        color: #000 !important;
        margin-bottom: 4pt !important;
    }}

    .print-doc-number {{
        font-size: 11pt !important;
        font-weight: bold !important;
    }}

    .print-doc-date {{
        font-size: 9pt !important;
        color: #666 !important;
    }}

    /* =========================================================================
       Print Footer (Legal Info + Page Numbers)
       ========================================================================= */
    .print-footer {{
        display: block !important;
        position: fixed !important;
        bottom: 0 !important;
        left: 0 !important;
        right: 0 !important;
        padding: 8pt 0 !important;
        border-top: 1pt solid #ccc !important;
        font-size: 8pt !important;
        color: #666 !important;
        text-align: center !important;
        background: #fff !important;
    }}

    .print-footer-legal {{
        margin-bottom: 4pt !important;
    }}

    .print-footer-page {{
        font-size: 9pt !important;
    }}

    /* Page counter using CSS counters */
    .print-page-counter {{
        counter-reset: page !important;
    }}

    .print-page-number:after {{
        counter-increment: page !important;
        content: "Page " counter(page) !important;
    }}

    /* =========================================================================
       Print-only Elements - Visible when printing
       ========================================================================= */
    .print-only {{
        display: block !important;
    }}

    /* =========================================================================
       Background and Colors - Force print
       ========================================================================= */
    * {{
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }}

    /* =========================================================================
       Images
       ========================================================================= */
    img {{
        max-width: 100% !important;
        page-break-inside: avoid !important;
    }}

    .logo-print {{
        max-height: 50pt !important;
        width: auto !important;
    }}

    /* =========================================================================
       Orphans and Widows
       ========================================================================= */
    p, li {{
        orphans: 3 !important;
        widows: 3 !important;
    }}

    /* =========================================================================
       List Views - Print optimization
       ========================================================================= */
    .list-print-header {{
        display: block !important;
        text-align: center !important;
        margin-bottom: 16pt !important;
    }}

    .list-print-title {{
        font-size: 16pt !important;
        font-weight: bold !important;
        color: #000 !important;
    }}

    .list-print-date {{
        font-size: 9pt !important;
        color: #666 !important;
        margin-top: 4pt !important;
    }}

    .list-print-filters {{
        font-size: 9pt !important;
        color: #666 !important;
        margin-bottom: 12pt !important;
    }}
}}

/* ==========================================================================
   ACCESSIBILITY & REDUCED MOTION
   ========================================================================== */
@media (prefers-reduced-motion: reduce) {{
    *,
    *::before,
    *::after {{
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }}
    .sidebar {{
        transition: none;
    }}
}}

/* Focus visible for keyboard navigation */
:focus-visible {{
    outline: 2px solid var(--primary);
    outline-offset: 2px;
}}

/* Skip to main content link */
.skip-link {{
    position: absolute;
    top: -100%;
    left: 16px;
    background: var(--primary);
    color: white;
    padding: 12px 16px;
    border-radius: var(--radius);
    z-index: 10000;
    font-weight: 500;
}}
.skip-link:focus {{
    top: 16px;
}}
'''

# =============================================================================
# Router pour servir le CSS
# =============================================================================
theme_router = APIRouter()

@theme_router.get("/style.css")
async def get_theme_css():
    """Sert le CSS généré depuis theme.yml."""
    css = ThemeManager.get_css()
    return Response(content=css, media_type="text/css")


@theme_router.get("/manifest.json")
async def get_manifest():
    """Sert le manifest.json pour PWA."""
    from pathlib import Path
    manifest_path = Path(__file__).parent.parent / "static" / "manifest.json"
    if manifest_path.exists():
        return Response(content=manifest_path.read_text(), media_type="application/json")
    # Manifest par défaut si le fichier n'existe pas
    return Response(content='{"name":"AzalPlus","short_name":"AzalPlus","display":"standalone"}', media_type="application/json")


@theme_router.get("/icons/{icon_name}")
async def get_icon(icon_name: str):
    """Sert les icônes PWA."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    icon_path = Path(__file__).parent.parent / "static" / "icons" / icon_name
    if icon_path.exists() and icon_path.suffix in [".png", ".ico", ".svg"]:
        return FileResponse(icon_path)
    # Icône transparente 1x1 par défaut
    return Response(content="", status_code=404)
