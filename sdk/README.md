# Rockib SDK

**Framework d'agents IA gouvernés** — chaque action d'un agent passe par un **arbitre déterministe** (`ALLOW` / `ESCALATE` / `DENY`) *avant* d'être exécutée.

Zéro dépendance externe. Python ≥ 3.10.

```bash
pip install -e sdk/          # depuis le dépôt Rockib_IA
rockib init mon_projet
rockib run mon_projet/agents.py
```

## En 15 lignes

```python
import asyncio
from rockib_sdk import GovernedAgent, Swarm, Step, Policy, ConsoleApproval, skill

@skill(domain="finance", permission="SPEND", risk="HIGH", reversible=False, spend_arg="montant_eur")
def virement(montant_eur: int, iban: str) -> str:
    """Virement fournisseur."""
    return f"{montant_eur} EUR → {iban}"

cfo = GovernedAgent("CFO IA", autonomy_level=4, skills=[virement], budget_ceiling=1000,
                    policy=Policy(auto_spend_limit=50), approval=ConsoleApproval())
tresorier = cfo.spawn("Trésorier", autonomy_level=3, budget_ceiling=500)

report = asyncio.run(Swarm([cfo]).run("Payer OVH", plan=[
    Step("Trésorier", "virement", {"montant_eur": 350, "iban": "FR76..."})
]))
print(report.summary())
```

## Garanties

| Garantie | Mécanisme |
| :--- | :--- |
| Aucune action critique sans humain | Risque HIGH/CRITICAL, irréversible, `DELETE` ou dépense > seuil ⇒ `ESCALATE` |
| Refus par défaut (fail-closed) | Sans gestionnaire d'approbation, toute escalade est rejetée (`DenyAll`) |
| Budget infranchissable | `Decimal` uniquement (floats refusés), réservation → consommation / libération, propagation aux ancêtres |
| Pas d'escalade de privilèges | Sous-agent : autonomie ≤ parent, compétences ⊆ parent, budget ≤ restant parent |
| `applied = min(requested, allowed)` | Un agent ne peut jamais s'auto-attribuer plus d'autonomie |
| Compétences infalsifiables | Scellement `sha256:` (métadonnées + code source), vérifié avant chaque exécution |
| Audit infalsifiable | Journal JSONL chaîné par hachage, vérifiable avec `rockib audit fichier.jsonl` |

## Planificateurs

- `plan=[Step(...)]` : plan explicite.
- `keyword_planner` (défaut) : choisit une compétence sans argument par correspondance lexicale.
- `LLMPlanner()` : planification via Groq / toute API compatible OpenAI (`GROQ_API_KEY`).

Le planificateur **propose** ; l'arbitre **décide**. Un LLM ne peut jamais contourner la politique.

## Approbation humaine

`DenyAll` (défaut) · `ConsoleApproval` · `CallableApproval(fn)` · `TelegramNotifier` · `AutoApprove` (tests uniquement).

## Mode connecté au serveur Rockib IA

```python
from rockib_sdk import RockibClient
client = RockibClient("http://127.0.0.1")
client.login("vous@exemple.com", "motdepasse")
client.sandbox_run(workspace_id, "print(2+2)", "assert 2+2 == 4")
client.generate_proposal("Client", "SaaS e-commerce avec agent WhatsApp")
```

## CLI

| Commande | Rôle |
| :--- | :--- |
| `rockib init [dossier]` | Génère un projet d'exemple |
| `rockib run agents.py` | Exécute un fichier d'agents |
| `rockib skills agents.py` | Liste et vérifie les compétences scellées |
| `rockib audit journal.jsonl` | Vérifie l'intégrité du journal d'audit |
| `rockib health --url URL` | Santé du serveur Rockib |
| `rockib studio --url URL` | Ouvre le Cockpit 3D |

## Tests

```bash
cd sdk && python -m pytest -q
```
