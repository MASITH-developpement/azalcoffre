/**
 * AZALPLUS - Currency Helper Functions
 * Multi-currency support for documents (devis, factures)
 */

// Currency configuration
window.AzalCurrency = {
    devises: {},
    deviseActuelle: 'EUR',
    tauxActuel: 1,
    symboleActuel: 'EUR',
    decimalesActuelles: 2,
    positionSymbole: 'APRES',

    // Default currencies (fallback)
    defaults: {
        EUR: { code: 'EUR', nom: 'Euro', symbole: 'EUR', taux: 1, decimales: 2, position_symbole: 'APRES' },
        USD: { code: 'USD', nom: 'Dollar', symbole: '$', taux: 1.08, decimales: 2, position_symbole: 'AVANT' },
        GBP: { code: 'GBP', nom: 'Livre', symbole: '\u00a3', taux: 0.86, decimales: 2, position_symbole: 'AVANT' },
        CHF: { code: 'CHF', nom: 'Franc suisse', symbole: 'CHF', taux: 0.97, decimales: 2, position_symbole: 'APRES' },
        MAD: { code: 'MAD', nom: 'Dirham', symbole: 'DH', taux: 10.85, decimales: 2, position_symbole: 'APRES' },
        XOF: { code: 'XOF', nom: 'Franc CFA', symbole: 'FCFA', taux: 655.957, decimales: 0, position_symbole: 'APRES' }
    },

    /**
     * Load currencies from API
     */
    async chargerDevises(selectId = 'devise') {
        try {
            const response = await fetch('/api/Devise');
            if (response.ok) {
                const data = await response.json();
                const select = document.getElementById(selectId);

                if (select) {
                    select.innerHTML = '';
                }

                data.forEach(d => {
                    if (d.actif !== false) {
                        this.devises[d.code] = d;

                        if (select) {
                            const option = document.createElement('option');
                            option.value = d.code;
                            option.dataset.symbole = d.symbole || d.code;
                            option.dataset.taux = d.taux || 1;
                            option.dataset.decimales = d.decimales || 2;
                            option.dataset.position = d.position_symbole || 'APRES';
                            option.textContent = `${d.code} - ${d.nom}`;
                            if (d.code === 'EUR') option.selected = true;
                            select.appendChild(option);
                        }
                    }
                });

                this.onDeviseChange(selectId);
                return data;
            }
        } catch (e) {
            console.warn('Erreur chargement devises, utilisation des valeurs par defaut:', e);
            // Use defaults
            this.devises = this.defaults;
            const select = document.getElementById(selectId);
            if (select) {
                select.innerHTML = '';
                Object.values(this.defaults).forEach(d => {
                    const option = document.createElement('option');
                    option.value = d.code;
                    option.dataset.symbole = d.symbole;
                    option.dataset.taux = d.taux;
                    option.dataset.decimales = d.decimales;
                    option.dataset.position = d.position_symbole;
                    option.textContent = `${d.code} - ${d.nom}`;
                    if (d.code === 'EUR') option.selected = true;
                    select.appendChild(option);
                });
                this.onDeviseChange(selectId);
            }
        }
        return [];
    },

    /**
     * Handle currency selection change
     */
    onDeviseChange(selectId = 'devise') {
        const select = document.getElementById(selectId);
        if (!select) return;

        const selectedOption = select.options[select.selectedIndex];
        if (selectedOption) {
            this.deviseActuelle = selectedOption.value;
            this.tauxActuel = parseFloat(selectedOption.dataset.taux) || 1;
            this.symboleActuel = selectedOption.dataset.symbole || this.deviseActuelle;
            this.decimalesActuelles = parseInt(selectedOption.dataset.decimales) || 2;
            this.positionSymbole = selectedOption.dataset.position || 'APRES';

            // Update rate display if exists
            const tauxInfo = document.getElementById('taux-info');
            if (tauxInfo) {
                tauxInfo.textContent = this.tauxActuel.toFixed(4);
            }

            // Show/hide conversion info
            const conversionInfo = document.getElementById('conversion-info');
            if (conversionInfo) {
                conversionInfo.style.display = this.deviseActuelle !== 'EUR' ? 'block' : 'none';
            }

            // Trigger recalculation if function exists
            if (typeof window.calculerTotaux === 'function') {
                window.calculerTotaux();
            }
        }
    },

    /**
     * Format an amount with current currency
     */
    formatMontant(montant, devise = null) {
        const d = devise ? (this.devises[devise] || this.defaults[devise]) : null;
        const decimales = d ? d.decimales : this.decimalesActuelles;
        const symbole = d ? d.symbole : this.symboleActuel;
        const position = d ? d.position_symbole : this.positionSymbole;

        const formatted = montant.toLocaleString('fr-FR', {
            minimumFractionDigits: decimales,
            maximumFractionDigits: decimales
        });

        if (position === 'AVANT') {
            return `${symbole}${formatted}`;
        } else {
            return `${formatted} ${symbole}`;
        }
    },

    /**
     * Convert amount to base currency (EUR)
     */
    convertirVersEUR(montant, fromCurrency = null) {
        const taux = fromCurrency
            ? (this.devises[fromCurrency]?.taux || this.defaults[fromCurrency]?.taux || 1)
            : this.tauxActuel;
        return montant / taux;
    },

    /**
     * Convert amount from base currency (EUR) to target
     */
    convertirDepuisEUR(montant, toCurrency = null) {
        const taux = toCurrency
            ? (this.devises[toCurrency]?.taux || this.defaults[toCurrency]?.taux || 1)
            : this.tauxActuel;
        return montant * taux;
    },

    /**
     * Convert between any two currencies
     */
    convert(montant, fromCurrency, toCurrency) {
        if (fromCurrency === toCurrency) return montant;

        // Convert via EUR
        const enEUR = this.convertirVersEUR(montant, fromCurrency);
        return this.convertirDepuisEUR(enEUR, toCurrency);
    },

    /**
     * Get current exchange rate
     */
    getTaux(currency = null) {
        if (!currency) return this.tauxActuel;
        return this.devises[currency]?.taux || this.defaults[currency]?.taux || 1;
    },

    /**
     * Get currency symbol
     */
    getSymbole(currency = null) {
        if (!currency) return this.symboleActuel;
        return this.devises[currency]?.symbole || this.defaults[currency]?.symbole || currency;
    }
};

// Auto-bind to client selection change
function bindClientCurrencySwitch(clientSelectId = 'client_id', deviseSelectId = 'devise') {
    const clientSelect = document.getElementById(clientSelectId);
    if (clientSelect) {
        clientSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            if (selectedOption && selectedOption.dataset.devise) {
                const deviseClient = selectedOption.dataset.devise;
                const deviseSelect = document.getElementById(deviseSelectId);
                if (deviseSelect) {
                    for (let i = 0; i < deviseSelect.options.length; i++) {
                        if (deviseSelect.options[i].value === deviseClient) {
                            deviseSelect.selectedIndex = i;
                            AzalCurrency.onDeviseChange(deviseSelectId);
                            break;
                        }
                    }
                }
            }
        });
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AzalCurrency, bindClientCurrencySwitch };
}
