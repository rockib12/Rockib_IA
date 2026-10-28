"""Exemple : un Trésorier IA qui ne peut JAMAIS dépasser son budget ni payer sans validation.

    python sdk/examples/tresorier.py
"""
import asyncio

from rockib_sdk import AuditTrail, AutoApprove, GovernedAgent, Policy, Step, Swarm, skill


@skill(domain="finance", permission="READ", risk="LOW", keywords=["solde", "tresorerie", "compte"])
def consulter_solde() -> str:
    """Consulte le solde de trésorerie."""
    return "Solde disponible : 4 250 EUR"


@skill(domain="finance", permission="SPEND", risk="HIGH", reversible=False, spend_arg="montant_eur")
def virement_fournisseur(montant_eur: int, iban: str) -> str:
    """Exécute un virement fournisseur."""
    return f"Virement de {montant_eur} EUR vers {iban} exécuté"


cfo = GovernedAgent(
    name="CFO IA",
    role="Financial Controller",
    autonomy_level=4,
    skills=[consulter_solde, virement_fournisseur],
    budget_ceiling=1000,
    policy=Policy(auto_spend_limit=50),
    approval=AutoApprove(),  # démo : remplacez par ConsoleApproval() ou TelegramNotifier()
    audit=AuditTrail(),
)
tresorier = cfo.spawn("Trésorier", autonomy_level=3, skills=["virement_fournisseur"], budget_ceiling=500)


async def main() -> None:
    swarm = Swarm([cfo])
    print((await swarm.run("Quel est le solde de trésorerie ?")).summary())

    ok = [Step("Trésorier", "virement_fournisseur", {"montant_eur": 350, "iban": "FR76 3000 6000 0112"})]
    print((await swarm.run("Payer la facture serveur", plan=ok)).summary())

    trop = [Step("Trésorier", "virement_fournisseur", {"montant_eur": 400, "iban": "FR76 9999"})]
    print((await swarm.run("Tentative de dépassement", plan=trop)).summary())

    print(f"\nBudget restant Trésorier : {tresorier.budget.remaining()} EUR")
    print(f"Journal d'audit : {cfo.audit.verify()} entrées chaînées et vérifiées")


if __name__ == "__main__":
    asyncio.run(main())
