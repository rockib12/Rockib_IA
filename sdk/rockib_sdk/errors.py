"""Exceptions typées du SDK Rockib."""


class RockibError(Exception):
    """Erreur racine du SDK."""


class SkillIntegrityError(RockibError):
    """Le contenu d'une compétence ne correspond plus à son scellement SHA-256."""


class SkillNotGrantedError(RockibError):
    """L'agent tente d'utiliser une compétence qui ne lui a pas été attribuée."""


class AutonomyEscalationError(RockibError):
    """Tentative de créer un sous-agent plus autonome que son parent."""


class BudgetViolationError(RockibError):
    """Dépassement de plafond budgétaire ou montant invalide."""


class AuditIntegrityError(RockibError):
    """La chaîne de hachage du journal d'audit a été altérée."""
