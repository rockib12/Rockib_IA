"""CLI `rockib` : init, run, skills, audit verify, health, studio."""
from __future__ import annotations

import argparse
import importlib.util
import json
import runpy
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from . import __version__
from .audit import load_entries, verify_entries
from .client import RockibClient
from .errors import RockibError
from .skills import Skill

TEMPLATE = '''"""Projet Rockib — agents gouvernés. Lancer : rockib run agents.py"""
import asyncio
from pathlib import Path

from rockib_sdk import AuditTrail, ConsoleApproval, GovernedAgent, Policy, Swarm, Step, skill


@skill(domain="ops", permission="READ", risk="LOW", keywords=["sante", "diagnostic", "statut"])
def diagnostic_systeme() -> str:
    """Diagnostic de santé du système."""
    return "Tous les services sont opérationnels."


@skill(domain="finance", permission="SPEND", risk="HIGH", reversible=False, spend_arg="montant_eur")
def payer_facture(montant_eur: int, fournisseur: str) -> str:
    """Paie une facture fournisseur."""
    return f"Facture {fournisseur} réglée : {montant_eur} EUR"


orchestrateur = GovernedAgent(
    name="Orchestrateur",
    role="Master Orchestrator",
    autonomy_level=3,
    skills=[diagnostic_systeme, payer_facture],
    budget_ceiling=1000,
    policy=Policy(auto_spend_limit=100),
    approval=ConsoleApproval(),
    audit=AuditTrail(Path(__file__).with_name("rockib_audit.jsonl")),
)
tresorier = orchestrateur.spawn("Trésorier", autonomy_level=2, skills=["payer_facture"], budget_ceiling=500)

swarm = Swarm([orchestrateur])


async def main() -> None:
    print((await swarm.run("Lancer un diagnostic de santé")).summary())
    plan = [Step("Trésorier", "payer_facture", {"montant_eur": 350, "fournisseur": "OVH"})]
    print((await swarm.run("Payer la facture serveur", plan=plan)).summary())


if __name__ == "__main__":
    asyncio.run(main())
'''


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.directory)
    target.mkdir(parents=True, exist_ok=True)
    agents_file = target / "agents.py"
    if agents_file.exists() and not args.force:
        print(f"✗ {agents_file} existe déjà (utilisez --force)")
        return 1
    agents_file.write_text(TEMPLATE, encoding="utf-8")
    print(f"✓ Projet Rockib initialisé : {agents_file}\n  → rockib run {agents_file}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"✗ Fichier introuvable : {path}")
        return 1
    sys.path.insert(0, str(path.parent.resolve()))
    runpy.run_path(str(path), run_name="__main__")
    return 0


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RockibError(f"Module invalide : {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent.resolve()))
    spec.loader.exec_module(module)
    return module


def cmd_skills(args: argparse.Namespace) -> int:
    module = _load_module(Path(args.file))
    found = [v for v in vars(module).values() if isinstance(v, Skill)]
    if not found:
        print("Aucune compétence @skill trouvée.")
        return 1
    status = 0
    for sk in found:
        try:
            sk.verify()
            ok = "✓"
        except RockibError:
            ok, status = "✗ ALTÉRÉE", 2
        print(f"{ok} {sk.name:<28} {sk.domain:<10} {sk.permission.value:<8} {sk.risk.value:<9} {sk.content_hash[:23]}…")
    return status


def cmd_audit(args: argparse.Namespace) -> int:
    try:
        count = verify_entries(load_entries(args.file))
    except RockibError as exc:
        print(f"✗ Journal compromis : {exc}")
        return 2
    print(f"✓ Chaîne d'audit intègre : {count} entrées vérifiées")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    try:
        print(json.dumps(RockibClient(args.url).health(), indent=2, ensure_ascii=False))
        return 0
    except RockibError as exc:
        print(f"✗ {exc}")
        return 1


def cmd_studio(args: argparse.Namespace) -> int:
    url = RockibClient(args.url).base_url + "/"
    print(f"Ouverture du Cockpit 3D Rockib : {url}")
    webbrowser.open(url)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rockib", description="Rockib SDK — agents IA gouvernés")
    parser.add_argument("--version", action="version", version=f"rockib-sdk {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Créer un projet d'agents gouvernés")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("run", help="Exécuter un fichier d'agents")
    p.add_argument("file")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("skills", help="Lister et vérifier les compétences scellées d'un module")
    p.add_argument("file")
    p.set_defaults(func=cmd_skills)

    p = sub.add_parser("audit", help="Vérifier l'intégrité d'un journal d'audit JSONL")
    p.add_argument("file")
    p.set_defaults(func=cmd_audit)

    for name, fn, helptext in (("health", cmd_health, "Santé du serveur Rockib"),
                               ("studio", cmd_studio, "Ouvrir le Cockpit 3D")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--url", default=None, help="URL du serveur (défaut : $ROCKIB_URL ou http://127.0.0.1)")
        p.set_defaults(func=fn)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
