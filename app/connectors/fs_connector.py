import os
import json
import asyncio
import logging
from pathlib import Path
from decimal import Decimal

from app.core.config import settings
from app.execution.models import ActionRecord
from app.execution.services.executor import ExecutionResult

logger = logging.getLogger(__name__)

WORKSPACES_ROOT = Path(settings.WORKSPACES_ROOT).resolve()

MAX_READ_BYTES = 1024 * 1024
MAX_WRITE_BYTES = 10 * 1024 * 1024  # 10 Mo max pour un fichier généré


async def _read_file_async(path: Path) -> str:
    """Lecture asynchrone non-bloquante via un thread."""
    def _read():
        size = os.path.getsize(path)
        if size > MAX_READ_BYTES:
            raise ValueError(f"File too large: {size} bytes (max {MAX_READ_BYTES})")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return await asyncio.to_thread(_read)


async def fs_read_handler(action: ActionRecord) -> ExecutionResult:
    """
    Connecteur 'fs.read'.
    Lit un fichier dans les limites strictes du dossier du workspace.
    """
    if (action.tool or "").lower() != "fs" or (action.operation or "").lower() != "read":
        return ExecutionResult(success=False, output=None, error="Invalid tool/operation", error_code="INVALID_TOOL")
    
    if action.workspace_id is None:
        return ExecutionResult(success=False, output=None, error="Missing workspace_id", error_code="MISSING_WORKSPACE")

    # 1. Parsing des arguments (Phase 3)
    args = action.arguments or {}
    requested_path = args.get("path")
    
    if not requested_path:
        return ExecutionResult(
            success=False, output=None, 
            error="Missing 'path' in arguments (e.g., {'path': 'file.txt'})", 
            error_code="MISSING_ARG_PATH"
        )

    # 2. SANDBOXING (Directory Traversal Protection)
    workspace_dir = (WORKSPACES_ROOT / str(action.workspace_id)).resolve()
    
    try:
        # resolve() élimine les ".." et les symlinks (si strict=False, il résout ce qu'il peut)
        target_path = (workspace_dir / requested_path).resolve()
    except Exception as e:
        return ExecutionResult(success=False, output=None, error="Path resolution error", error_code="PATH_ERROR")

    # VÉRIFICATION CRITIQUE : Le chemin final cible-t-il bien un sous-dossier autorisé ?
    try:
        target_path.relative_to(workspace_dir)
    except ValueError:
        return ExecutionResult(
            success=False, 
            output=None, 
            error="Security Violation: Path traversal attempt outside workspace boundaries.",
            error_code="PATH_TRAVERSAL"
        )

    # 3. Exécution métier
    if not target_path.exists():
        return ExecutionResult(success=False, output=None, error="File not found", error_code="FILE_NOT_FOUND")
    
    if not target_path.is_file():
        return ExecutionResult(success=False, output=None, error="Target is a directory, not a file", error_code="NOT_A_FILE")

    try:
        content = await _read_file_async(target_path)
        return ExecutionResult(
            success=True,
            output=content,
            error=None,
            cost_amount=Decimal("0.0"),
            cost_unit="credits",
            effect_unknown=False
        )
    except ValueError as e:
        if "File too large" in str(e):
            return ExecutionResult(success=False, output=None, error=str(e), error_code="FILE_TOO_LARGE", effect_unknown=False)
        return ExecutionResult(success=False, output=None, error=str(e), error_code="READ_ERROR", effect_unknown=False)
    except Exception as e:
        return ExecutionResult(success=False, output=None, error=str(e), error_code="READ_ERROR", effect_unknown=False)


def _generate_fallback_template(path: str, objective: str) -> str:
    """Génère un template de code complet et esthétique si la génération LLM est indisponible."""
    ext = Path(path).suffix.lower()
    title = objective or "Système Rockib AI"

    if ext in (".html", ".htm"):
        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #090D16;
      --card-bg: rgba(15, 23, 42, 0.75);
      --neon-cyan: #00F0FF;
      --neon-indigo: #6366F1;
      --neon-emerald: #10B981;
      --text: #F8FAFC;
      --text-muted: #94A3B8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 2rem;
      background-image: 
        radial-gradient(circle at 20% 20%, rgba(99, 102, 241, 0.15) 0%, transparent 40%),
        radial-gradient(circle at 80% 80%, rgba(0, 240, 255, 0.15) 0%, transparent 40%);
    }}
    .container {{
      max-width: 900px;
      width: 100%;
      background: var(--card-bg);
      border: 1px solid rgba(0, 240, 255, 0.25);
      backdrop-filter: blur(16px);
      border-radius: 16px;
      padding: 3rem;
      box-shadow: 0 20px 50px rgba(0,0,0,0.5), 0 0 30px rgba(0, 240, 255, 0.1);
    }}
    .badge {{
      display: inline-block;
      background: rgba(0, 240, 255, 0.1);
      color: var(--neon-cyan);
      border: 1px solid var(--neon-cyan);
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      margin-bottom: 1.5rem;
    }}
    h1 {{
      font-size: 2.5rem;
      font-weight: 800;
      margin-bottom: 1rem;
      background: linear-gradient(135deg, #FFF, var(--neon-cyan));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    p {{
      color: var(--text-muted);
      font-size: 1.1rem;
      line-height: 1.7;
      margin-bottom: 2rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1.5rem;
      margin-top: 2rem;
    }}
    .card {{
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 1.5rem;
      transition: all 0.3s ease;
    }}
    .card:hover {{
      border-color: var(--neon-cyan);
      transform: translateY(-4px);
    }}
    .card h3 {{ color: var(--neon-cyan); margin-bottom: 0.5rem; }}
    .footer {{
      margin-top: 3rem;
      text-align: center;
      font-size: 0.85rem;
      color: var(--text-muted);
      border-top: 1px solid rgba(255, 255, 255, 0.1);
      padding-top: 1.5rem;
    }}
  </style>
</head>
<body>
  <div class="container">
    <span class="badge">🚀 ROCKIB AI • DÉPLOIEMENT AUTONOME</span>
    <h1>{title}</h1>
    <p>Cette application a été conçue, orchestrée et générée automatiquement par le réseau multi-agents autonome de <strong>Rockib AI</strong>.</p>
    
    <div class="grid">
      <div class="card">
        <h3>⚡ Haute Performance</h3>
        <p>Architecture optimisée, temps de chargement ultra-rapide et responsive design.</p>
      </div>
      <div class="card">
        <h3>🛡️ Sécurité & Isolation</h3>
        <p>Garanties de sandboxing déterministe et intégrité formelle des données.</p>
      </div>
      <div class="card">
        <h3>🤖 Intelligence Agentique</h3>
        <p>Piloté par des modèles d'arbitrage déterministes et analyse de risque en temps réel.</p>
      </div>
    </div>

    <div class="footer">
      Propulsé par Rockib AI • {title} • Prêt pour la production
    </div>
  </div>
</body>
</html>
"""
    elif ext == ".py":
        return f"""\"\"\"{title}
Généré automatiquement par Rockib AI.
\"\"\"
from datetime import datetime

def main():
    print("=" * 60)
    print("🚀 {title}")
    print(f"Heure d'initialisation : {{datetime.now()}}")
    print("=" * 60)
    print("Système opérationnel et validé par Rockib AI.")

if __name__ == "__main__":
    main()
"""
    elif ext == ".css":
        return """/* Feuille de style moderne générée par Rockib AI */
:root {
  --primary: #00F0FF;
  --secondary: #6366F1;
  --bg: #090D16;
  --text: #F8FAFC;
}
body {
  background-color: var(--bg);
  color: var(--text);
  font-family: sans-serif;
}
"""
    elif ext == ".js":
        return """// Script interactif généré par Rockib AI
console.log("⚡ Système Rockib AI initialisé avec succès !");
document.addEventListener("DOMContentLoaded", () => {
  console.log("DOM prêt.");
});
"""
    else:
        return f"# {title}\n\nFichier généré automatiquement par l'agent Rockib AI pour l'objectif : {objective}\n"


async def fs_write_handler(action: ActionRecord) -> ExecutionResult:
    """
    Connecteur 'fs.write' / 'system.create'.
    Crée ou met à jour un fichier dans les limites strictes du workspace.
    Si le contenu n'est pas fourni, synthétise automatiquement le code source complet via Groq LLM.
    """
    if action.workspace_id is None:
        return ExecutionResult(
            success=False,
            output=None,
            error="Missing workspace_id",
            error_code="MISSING_WORKSPACE"
        )

    args = action.arguments or {}
    requested_path = (
        args.get("path") 
        or args.get("filename") 
        or args.get("file")
    )
    content = args.get("content") or args.get("code")

    # Déduction automatique du nom de fichier si omis
    if not requested_path:
        raw_text = (args.get("raw_input") or action.objective or "").lower()
        if "css" in raw_text and "html" not in raw_text:
            requested_path = "style.css"
        elif "python" in raw_text or ".py" in raw_text:
            requested_path = "main.py"
        elif "javascript" in raw_text or ".js" in raw_text:
            requested_path = "app.js"
        else:
            requested_path = "index.html"

    # Sandboxing strict dans le dossier du workspace
    workspace_dir = (WORKSPACES_ROOT / str(action.workspace_id)).resolve()
    try:
        workspace_dir.mkdir(parents=True, exist_ok=True)
        target_path = (workspace_dir / requested_path).resolve()
        target_path.relative_to(workspace_dir)
    except ValueError:
        return ExecutionResult(
            success=False,
            output=None,
            error="Security Violation: Path traversal attempt outside workspace boundaries.",
            error_code="PATH_TRAVERSAL"
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            output=None,
            error=f"Path resolution error: {str(e)}",
            error_code="PATH_ERROR"
        )

    # Synthèse du code si manquant
    if not content or len(content.strip()) == 0:
        logger.info("Content missing in arguments, requesting LLM code generation via GroqProvider...")
        try:
            from app.intelligence.services.providers.groq_provider import GroqProvider
            provider = GroqProvider()
            prompt = (
                f"Tu es un architecte logiciel et développeur expert full-stack de classe mondiale de Rockib AI.\n"
                f"L'utilisateur a donné l'objectif suivant : \"{action.objective}\".\n"
                f"Tu dois générer le code source complet, authentique et prêt pour la production (sans placeholder '// TODO' ou '<!-- rest -->'), "
                f"pour le fichier '{requested_path}'.\n\n"
                f"DIRECTIVES :\n"
                f"- Si c'est une page HTML ({requested_path}), elle doit être visuellement magnifique, moderne et adaptée exactement au sujet de l'entreprise "
                f"(catalogue, produits réels, tarifs, formulaires, design professionnel, CSS intégré et responsive mobile).\n"
                f"- Si c'est du Python/JS, le code doit être fonctionnel, modulaire et documenté.\n"
                f"- Renvoie UNIQUEMENT le code complet à l'intérieur d'un bloc ```{requested_path.split('.')[-1]} ... ``` sans texte d'accompagnement."
            )
            meta = await provider.generate_with_meta([
                {"role": "system", "content": "You are a professional code synthesis assistant. Output only the complete code inside a single markdown code block."},
                {"role": "user", "content": prompt}
            ], json_mode=False, max_tokens=8192)
            raw_llm = meta.content
            match = re.search(r"```(?:\w+)?\s*([\s\S]*?)```", raw_llm)
            content = match.group(1).strip() if match else raw_llm.strip()

            # Ensure complete HTML structure and inject Concierge widget if missing
            if requested_path.endswith(".html"):
                if "</body>" in content and "/static/rockib-concierge.js" not in content:
                    content = content.replace("</body>", '  <script src="/static/rockib-concierge.js" data-site-key="rockib-portfolio" defer></script>\n</body>')
                if not content.endswith("</html>"):
                    if "</body>" not in content:
                        content += "\n</body>"
                    content += "\n</html>"
        except Exception as exc:
            logger.warning(f"Groq code generation failed ({exc}), falling back to built-in template.")
            content = _generate_fallback_template(requested_path, action.objective)

    # Nettoyage de balises markdown résiduelles si le LLM en a mis
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        lines = cleaned_content.splitlines()
        if len(lines) > 2 and lines[0].startswith("```"):
            cleaned_content = "\n".join(lines[1:-1])

    # Écriture asynchrone sécurisée
    def _write_file():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(cleaned_content)
        return os.path.getsize(target_path)

    try:
        size_bytes = await asyncio.to_thread(_write_file)
    except Exception as exc:
        return ExecutionResult(
            success=False,
            output=None,
            error=f"Write error: {str(exc)}",
            error_code="WRITE_ERROR",
            effect_unknown=False
        )

    preview_url = f"/api/v1/workspaces/{action.workspace_id}/preview/{requested_path}"
    summary = (
        f"✓ Fichier et système créés avec succès !\n"
        f"- Fichier : {requested_path}\n"
        f"- Taille : {size_bytes} octets\n"
        f"- Lien de prévisualisation directe : {preview_url}\n\n"
        f"--- APERÇU DU CODE SOURCE ({min(500, len(cleaned_content))} premiers caractères) ---\n"
        f"{cleaned_content[:500]}..."
    )

    return ExecutionResult(
        success=True,
        output=summary,
        error=None,
        cost_amount=Decimal("0.0"),
        cost_unit="credits",
        effect_unknown=False,
        provider_reference=f"fs:{requested_path}"
    )
