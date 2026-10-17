import asyncio
import logging
import httpx
from decimal import Decimal
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from app.execution.models import ActionRecord
from app.execution.services.executor import ExecutionResult

logger = logging.getLogger(__name__)

# User-Agent pour simuler un navigateur standard et éviter les blocages basiques
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
MAX_TEXT_LENGTH = 50000

import urllib.parse
import xml.etree.ElementTree as ET

def _search_google_news(query: str, max_results: int = 5) -> list[dict]:
    """Recherche d'actualités en temps réel via le flux RSS Google News (100% fiable, jamais bloqué)."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=fr&gl=FR&ceid=FR:fr"
        with httpx.Client(headers=HEADERS, timeout=8.0) as client:
            r = client.get(url)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                items = root.findall(".//item")
                results = []
                for item in items[:max_results]:
                    raw_title = item.find("title").text if item.find("title") is not None else "Sans titre"
                    link = item.find("link").text if item.find("link") is not None else ""
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    source = "Actualité"
                    title = raw_title
                    if " - " in raw_title:
                        parts = raw_title.rsplit(" - ", 1)
                        title = parts[0]
                        source = parts[1]
                    results.append({
                        "title": title,
                        "url": link,
                        "body": f"Date: {pub_date}. Éditeur: {source}.",
                        "source": source,
                    })
                return results
    except Exception as e:
        logger.warning(f"[GOOGLE NEWS] Error: {e}")
    return []


def _search_wikipedia(query: str, max_results: int = 5) -> list[dict]:
    """Recherche encyclopédique via l'API officielle Wikipédia en cas de sujet documentaire."""
    try:
        url = "https://fr.wikipedia.org/w/api.php"
        params = {"action": "query", "list": "search", "srsearch": query, "format": "json"}
        with httpx.Client(headers=HEADERS, timeout=6.0) as client:
            r = client.get(url, params=params)
            if r.status_code == 200:
                data = r.json()
                items = data.get("query", {}).get("search", [])
                results = []
                for item in items[:max_results]:
                    title = item.get("title", "")
                    clean_snippet = BeautifulSoup(item.get("snippet", ""), "html.parser").get_text()
                    results.append({
                        "title": title,
                        "url": f"https://fr.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                        "body": clean_snippet,
                        "source": "Wikipédia",
                    })
                return results
    except Exception as e:
        logger.warning(f"[WIKIPEDIA] Error: {e}")
    return []


async def web_search_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur 'web.search' robuste multi-fournisseurs (Google News RSS, DuckDuckGo, Wikipédia)."""
    args = action.arguments or {}
    query = args.get("query")
    max_results = args.get("max_results", 5)
    
    if not query:
        return ExecutionResult(success=False, output=None, error="Missing 'query' argument")
        
    try:
        def _search():
            q_lower = query.lower()
            is_news = any(kw in q_lower for kw in ["actu", "actualit", "news", "recent", "récent", "aujourd", "2026", "2025"])
            results = []
            
            # 1. Si requête d'actualité, interroger Google News RSS en priorité (fraîcheur temps réel garantie)
            if is_news:
                results = _search_google_news(query, max_results=max_results)
                
            # 2. Si non concluant ou pas orienté actu, tenter DuckDuckGo (news puis text)
            if not results:
                try:
                    with DDGS() as ddgs:
                        try:
                            results = list(ddgs.news(query, max_results=max_results))
                        except Exception:
                            results = []
                        if not results:
                            try:
                                results = list(ddgs.text(query, max_results=max_results))
                            except Exception:
                                results = []
                except Exception as ddg_err:
                    logger.warning(f"[DDG SEARCH] Skipped due to rate-limit/error: {ddg_err}")
            
            # 3. Fallback universel : Google News ou Wikipédia
            if not results:
                results = _search_google_news(query, max_results=max_results)
            if not results:
                results = _search_wikipedia(query, max_results=max_results)
                
            return results
                
        results = await asyncio.to_thread(_search)
        
        # Formater les résultats proprement pour le LLM et l'affichage utilisateur
        formatted_results = []
        for i, res in enumerate(results, 1):
            title = res.get('title', 'No Title')
            link = res.get('href') or res.get('url', 'No URL')
            snippet = res.get('body') or res.get('snippet', 'No Snippet')
            source = res.get('source', '')
            source_tag = f" ({source})" if source else ""
            formatted_results.append(f"[{i}] {title}{source_tag}\nURL: {link}\nSnippet: {snippet}\n")
            
        output = "\n".join(formatted_results)
        if not output:
            output = f"Aucun résultat trouvé pour la requête : '{query}'"
            
        logger.info(f"[WEB SEARCH] '{query}' -> {len(results)} results")
        return ExecutionResult(success=True, output=output, error=None, cost_amount=Decimal("0.0"), cost_unit="credits")
        
    except Exception as e:
        logger.error(f"[WEB SEARCH] Error: {e}")
        return ExecutionResult(success=False, output=None, error=str(e), error_code="SEARCH_ERROR")



async def web_fetch_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur 'web.fetch' pour lire le texte d'une page (Web Scraping avec protection anti-SSRF et anti-DNS-rebinding)."""
    from urllib.parse import urljoin
    from app.core.network_security import (
        SSRFSecurityViolation,
        validate_url_for_ssrf,
        create_pinned_async_transport,
    )

    args = action.arguments or {}
    url = args.get("url")
    
    if not url:
        return ExecutionResult(success=False, output=None, error="Missing 'url' argument")

    current_url = url
    max_redirects = 3
    redirect_count = 0

    try:
        while True:
            # 1. Validation anti-SSRF de l'URL courante
            try:
                validated_ips = validate_url_for_ssrf(current_url)
            except SSRFSecurityViolation as e:
                err_code = "SSRF_REDIRECT_BLOCKED" if redirect_count > 0 else "SSRF_SECURITY_VIOLATION"
                err_msg = f"SSRF Security Violation{' in redirect' if redirect_count > 0 else ''}: {str(e)}"
                logger.warning(f"[WEB FETCH] SSRF violation ({err_code}) blocked for URL '{current_url}': {e}")
                return ExecutionResult(
                    success=False,
                    output=None,
                    error=err_msg,
                    error_code=err_code,
                )

            # 2. Établissement de la connexion HTTPX épinglée sur l'IP validée (immunité DNS rebinding)
            transport = create_pinned_async_transport(validated_ips[0])
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False, headers=HEADERS, transport=transport) as client:
                response = await client.get(current_url)

            if response.is_redirect:
                redirect_count += 1
                if redirect_count > max_redirects:
                    return ExecutionResult(
                        success=False,
                        output=None,
                        error="Too many redirects",
                        error_code="TOO_MANY_REDIRECTS",
                    )
                location = response.headers.get("location")
                if not location:
                    break
                next_url = urljoin(current_url, location)
                current_url = next_url
            else:
                break

        response.raise_for_status()
        
        # Utiliser BeautifulSoup pour extraire uniquement le texte visible
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Supprimer les balises indésirables (scripts, styles)
        for script in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            script.decompose()
            
        text = soup.get_text(separator="\n", strip=True)
        
        # Tronquer le texte si trop long pour éviter de faire exploser le LLM
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "\n\n[TRUNCATED: Page too long]"
            
        logger.info(f"[WEB FETCH] {url} -> {len(text)} chars extracted")
        return ExecutionResult(success=True, output=text, error=None, cost_amount=Decimal("0.0"), cost_unit="credits")
            
    except httpx.HTTPStatusError as e:
        return ExecutionResult(success=False, output=None, error=f"HTTP Error: {e.response.status_code}", error_code="FETCH_HTTP_ERROR")
    except Exception as e:
        logger.error(f"[WEB FETCH] Error for {url}: {e}")
        return ExecutionResult(success=False, output=None, error=str(e), error_code="FETCH_ERROR")
