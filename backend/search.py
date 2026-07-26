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
from urllib.parse import unquote


async def search_searxng(query: str, base_url: str = "http://localhost:8888", limit: int = 5):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{base_url}/search",
                             params={"q": query, "format": "json"})
        r.raise_for_status()
        data = r.json()
        return [
            {"title": item.get("title", ""), "url": item.get("url", ""),
             "snippet": item.get("content", "")}
            for item in (data.get("results") or [])[:limit]
        ]


async def search_duckduckgo(query: str, limit: int = 5):
    async with httpx.AsyncClient(
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0 (compatible; LocalAI/2.0)"}
    ) as client:
        r = await client.get("https://duckduckgo.com/html/",
                             params={"q": query})
        r.raise_for_status()
        html = r.text
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.S)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
        hrefs = re.findall(r'class="result__a"[^>]+href="([^"]+)"', html)
        out = []
        for i in range(min(limit, len(titles))):
            out.append({
                "title": re.sub(r"<[^>]+>", "", titles[i]).strip(),
                "url": unquote(hrefs[i]) if i < len(hrefs) else "",
                "snippet": re.sub(r"<[^>]+>", "",
                                  snippets[i]).strip() if i < len(snippets) else "",
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
