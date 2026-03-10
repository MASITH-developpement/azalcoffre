# =============================================================================
# AUTOPILOT - Système d'auto-correction autonome avec apprentissage
# =============================================================================
"""
AutoPilot: Un système modulaire d'auto-correction de bugs avec apprentissage.

Usage:
    from moteur.autopilot import AutoPilot, ErrorAnalyzer, FixApplicator

    # Initialiser avec un backend de stockage
    autopilot = AutoPilot(
        storage=PostgresStorage(connection_string),
        # ou: storage=SQLiteStorage("learnings.db"),
        # ou: storage=MemoryStorage()
    )

    # Analyser une erreur
    proposal = autopilot.analyze("NameError: name 'Depends' is not defined")

    # Valider un fix
    autopilot.validate(proposal.id, approved=True)

    # Ou rejeter avec explication
    autopilot.validate(proposal.id, approved=False,
                       explanation="L'import existe déjà, le problème est ailleurs")

Le système est conçu pour être:
- Modulaire: chaque composant peut être remplacé
- Scalable: supporte différents backends de stockage
- Encapsulable: peut être intégré dans n'importe quel projet Python
- Apprenant: améliore ses propositions basé sur les validations/rejets
"""

from .core import AutoPilot
from .analyzers import ErrorAnalyzer, PythonErrorAnalyzer, YAMLErrorAnalyzer, SQLErrorAnalyzer
from .storage import StorageBackend, MemoryStorage, PostgresStorage
from .applicators import FixApplicator, PythonFixApplicator
from .models import FixProposal, Learning, FixStatus
from .norms import Norm, NormsChecker, AZALPLUS_NORMS, check_against_norms
from .alerter import AutoPilotAlerter
from .auto_fixer import AutoFixer

__all__ = [
    "AutoPilot",
    "ErrorAnalyzer",
    "PythonErrorAnalyzer",
    "YAMLErrorAnalyzer",
    "SQLErrorAnalyzer",
    "StorageBackend",
    "MemoryStorage",
    "PostgresStorage",
    "FixApplicator",
    "PythonFixApplicator",
    "FixProposal",
    "Learning",
    "FixStatus",
    "Norm",
    "NormsChecker",
    "AZALPLUS_NORMS",
    "check_against_norms",
    "AutoPilotAlerter",
    "AutoFixer",
]

__version__ = "1.0.0"
