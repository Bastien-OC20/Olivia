"""
Recherche web pluggable. Trois providers au choix, sélectionnés depuis settings.json :
  - 'searxng'    : instance SearXNG auto-hébergée (recommandé)
  - 'duckduckgo' : scraping HTML lite (sans clé, fragile)
  - 'brave'      : API Brave Search (variable d'env BRAVE_API_KEY requise)

Retourne une liste uniforme de {title, url, snippet}.
"""
import os
import re

import httpx
from html import unescape
from urllib.parse import unquote


def _strip_html(fragment: str) -> str:
    """Retire les balises et décode les entités (&#x27;, &amp;…) d'un extrait HTML."""
    return unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _unwrap_ddg_url(href: str) -> str:
    """DuckDuckGo enveloppe chaque lien dans //duckduckgo.com/l/?uddg=<url encodée>.

    On extrait l'URL réelle : c'est elle qu'Olivia affiche et cite en source.
    """
    href = unescape(href)
    m = re.search(r"[?&]uddg=([^&]+)", href)
    if m:
        return unquote(m.group(1))
    return f"https:{href}" if href.startswith("//") else href


async def search_searxng(query: str, base_url: str = "http://localhost:8888", limit: int = 5):
    """Interroge une instance SearXNG locale (métamoteur : Google, DuckDuckGo, etc.).

    L'instance doit autoriser le format JSON : dans son `settings.yml`,
    `search.formats` doit contenir `json` (absent de la configuration par
    défaut, ce qui provoque sinon un HTTP 403).
    """
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "format": "json", "language": "fr-FR"},
        )
        if r.status_code == 403:
            raise RuntimeError(
                "SearXNG refuse le format JSON (HTTP 403). Ajoutez 'json' à "
                "search.formats dans le settings.yml de votre instance, puis "
                "redémarrez-la."
            )
        r.raise_for_status()
        data = r.json()
        return [
            {"title": item.get("title", ""), "url": item.get("url", ""),
             "snippet": item.get("content", "")}
            for item in (data.get("results") or [])[:limit]
        ]


async def search_duckduckgo(query: str, limit: int = 5):
    # duckduckgo.com/html/ redirige (302) vers html.duckduckgo.com : on vise
    # directement l'hôte final et on suit les redirections restantes, sans quoi
    # httpx renvoie la réponse 302 et le parsing ne trouve aucun résultat.
    async with httpx.AsyncClient(
        timeout=10,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; LocalAI/2.0)"}
    ) as client:
        r = await client.get("https://html.duckduckgo.com/html/",
                             params={"q": query})
        r.raise_for_status()
        html = r.text
        # Sous protection anti-robot, DuckDuckGo sert une page de blocage en
        # HTTP 202 (et non un 4xx) : sans ce garde-fou elle serait interprétée
        # comme « zéro résultat », ce qui masquerait la vraie cause.
        if r.status_code == 202 and 'class="result__a"' not in html:
            raise RuntimeError(
                "DuckDuckGo a bloqué la requête (protection anti-robot). "
                "Réessayez dans un instant, ou passez au moteur SearXNG "
                "(plus fiable — voir Paramètres → Recherche web)."
            )
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.S)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
        hrefs = re.findall(r'class="result__a"[^>]+href="([^"]+)"', html)
        out = []
        for i in range(min(limit, len(titles))):
            out.append({
                "title": _strip_html(titles[i]),
                "url": _unwrap_ddg_url(hrefs[i]) if i < len(hrefs) else "",
                "snippet": _strip_html(snippets[i]) if i < len(snippets) else "",
            })
        return out


async def search_brave(query: str, api_key: str, limit: int = 5):
    if not api_key:
        raise ValueError("BRAVE_API_KEY non définie dans l'environnement")
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": limit},
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
        return [
            {"title": item.get("title", ""), "url": item.get("url", ""),
             "snippet": item.get("description", "")}
            for item in (data.get("web", {}).get("results") or [])[:limit]
        ]


async def web_search(provider: str, query: str, **kwargs) -> list[dict]:
    if provider == "searxng":
        return await search_searxng(query, kwargs.get("searxng_url", "http://localhost:8888"),
                                    kwargs.get("limit", 5))
    if provider == "duckduckgo":
        return await search_duckduckgo(query, kwargs.get("limit", 5))
    if provider == "brave":
        return await search_brave(query, os.getenv("BRAVE_API_KEY", ""),
                                  kwargs.get("limit", 5))
    raise ValueError(f"Provider inconnu : {provider}")
