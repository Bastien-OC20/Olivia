"""
Recherche web pluggable. Trois providers au choix, sélectionnés depuis settings.json :
  - 'searxng'    : instance SearXNG auto-hébergée (recommandé)
  - 'duckduckgo' : scraping HTML (sans clé, fragile par nature)
  - 'brave'      : API Brave Search (clé requise, voir Paramètres → Recherche web)

Retourne une liste uniforme de {title, url, snippet}.

`web_search()` est le point d'entrée public : c'est une cascade qui essaie le
provider demandé puis, s'il échoue ou ne renvoie rien, les autres moteurs
réellement disponibles — pensée pour les machines sans Docker (SearXNG
indisponible) où DuckDuckGo reste parfois bloqué par sa protection anti-robot.
"""
import os
import re

import httpx
from html import unescape
from urllib.parse import unquote

# Ordre de tentative par défaut de la cascade (le provider demandé est
# toujours essayé en premier, puis les autres dans cet ordre).
_ALL_PROVIDERS = ("searxng", "duckduckgo", "brave")

# DuckDuckGo bloque plus volontiers les clients qui s'annoncent comme robots
# (l'ancien "Mozilla/5.0 (compatible; LocalAI/2.0)" en est un exemple type).
# Un User-Agent de vrai navigateur réduit — sans l'éliminer — le risque de
# blocage. Le scraping HTML reste par nature fragile.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


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


def _parse_ddg_html(html: str, limit: int) -> list[dict]:
    """Parse la page de résultats classique (html.duckduckgo.com/html/)."""
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


def _parse_ddg_lite(html: str, limit: int) -> list[dict]:
    """Parse la page allégée (lite.duckduckgo.com/lite/), utilisée en repli.

    Son HTML diffère de la version classique : simple tableau, lien de
    résultat en classe `result-link` (guillemets simples), extrait en
    classe `result-snippet` dans la cellule suivante.
    """
    links = re.findall(
        r"""<a rel="nofollow" href="([^"]+)" class='result-link'>(.*?)</a>""",
        html, re.S,
    )
    snippets = re.findall(r"""class='result-snippet'>(.*?)</td>""", html, re.S)
    out = []
    for i in range(min(limit, len(links))):
        href, title = links[i]
        out.append({
            "title": _strip_html(title),
            "url": _unwrap_ddg_url(href),
            "snippet": _strip_html(snippets[i]) if i < len(snippets) else "",
        })
    return out


async def _fetch_ddg_lite(query: str, limit: int) -> list[dict]:
    """Repli sur la page allégée quand la version classique est bloquée ou vide.

    Son HTML étant plus simple, elle échappe parfois à la détection
    anti-robot qui vise la version classique — mais rien ne le garantit : le
    scraping reste fragile par nature, cette page pouvant être bloquée à
    son tour ou changer de structure sans préavis.
    """
    async with httpx.AsyncClient(
        timeout=10, follow_redirects=True, headers={"User-Agent": _BROWSER_UA}
    ) as client:
        r = await client.get("https://lite.duckduckgo.com/lite/", params={"q": query})
        r.raise_for_status()
        return _parse_ddg_lite(r.text, limit)


async def search_duckduckgo(query: str, limit: int = 5):
    # duckduckgo.com/html/ redirige (302) vers html.duckduckgo.com : on vise
    # directement l'hôte final et on suit les redirections restantes, sans quoi
    # httpx renvoie la réponse 302 et le parsing ne trouve aucun résultat.
    async with httpx.AsyncClient(
        timeout=10, follow_redirects=True, headers={"User-Agent": _BROWSER_UA}
    ) as client:
        r = await client.get("https://html.duckduckgo.com/html/",
                             params={"q": query})
        r.raise_for_status()
        html = r.text
        # Sous protection anti-robot, DuckDuckGo sert une page de blocage en
        # HTTP 202 (et non un 4xx) : sans ce garde-fou elle serait interprétée
        # comme « zéro résultat », ce qui masquerait la vraie cause.
        blocked = r.status_code == 202 and 'class="result__a"' not in html
        results = [] if blocked else _parse_ddg_html(html, limit)

    if results:
        return results

    # Repli sur la page allégée : un User-Agent de navigateur réduit les
    # blocages mais ne les supprime pas, ce second essai sur une page au
    # HTML différent capture les cas où seule la version classique bloque.
    try:
        results = await _fetch_ddg_lite(query, limit)
    except Exception as e:
        if blocked:
            raise RuntimeError(
                "DuckDuckGo a bloqué la requête (protection anti-robot), y "
                f"compris via la page allégée ({e}). Réessayez dans un "
                "instant, ou passez au moteur SearXNG (voir Paramètres → "
                "Recherche web)."
            ) from e
        raise
    if not results and blocked:
        raise RuntimeError(
            "DuckDuckGo a bloqué la requête (protection anti-robot), y "
            "compris via la page allégée. Réessayez dans un instant, ou "
            "passez au moteur SearXNG (voir Paramètres → Recherche web)."
        )
    return results


async def search_brave(query: str, api_key: str, limit: int = 5):
    if not api_key:
        raise ValueError("Clé Brave non configurée (Paramètres → Recherche web, "
                         "ou variable d'env BRAVE_API_KEY)")
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


async def web_search(provider: str, query: str, **kwargs) -> tuple[str, list[dict]]:
    """Cascade de recherche : essaie `provider`, puis les autres moteurs
    réellement disponibles si celui-ci échoue ou ne renvoie rien.

    kwargs reconnus : `limit`, `searxng_url`, `brave_api_key`.

    Renvoie `(provider_effectif, résultats)` — le provider qui a réellement
    répondu, pas forcément celui demandé. Lève RuntimeError si tous les
    moteurs disponibles ont échoué, avec le détail de chaque tentative.
    """
    if provider not in _ALL_PROVIDERS:
        raise ValueError(f"Provider inconnu : {provider}")

    limit = kwargs.get("limit", 5)
    searxng_url = kwargs.get("searxng_url", "http://localhost:8888")
    # La clé Brave configurée dans l'UI prime ; à défaut, repli sur la
    # variable d'environnement (compatibilité avec les installations
    # existantes qui la définissaient déjà).
    brave_key = kwargs.get("brave_api_key") or os.getenv("BRAVE_API_KEY", "")

    # Le provider demandé passe en premier, puis les autres moteurs, dans
    # l'ordre par défaut. Brave n'est tenté que si une clé est disponible :
    # inutile d'ajouter une tentative vouée à l'échec à la cascade.
    order = [provider] + [p for p in _ALL_PROVIDERS if p != provider]
    order = [p for p in order if p != "brave" or brave_key]

    errors = []
    # Moteur ayant répondu correctement mais sans résultat : une requête sans
    # réponse n'est PAS une panne. On distingue les deux cas, sinon l'UI
    # annoncerait « recherche indisponible » pour une simple requête infructueuse.
    empty_provider = None
    for p in order:
        try:
            if p == "searxng":
                results = await search_searxng(query, searxng_url, limit)
            elif p == "duckduckgo":
                results = await search_duckduckgo(query, limit)
            else:
                results = await search_brave(query, brave_key, limit)
        except Exception as e:
            errors.append(f"{p} : {e}")
            continue
        if results:
            return p, results
        if empty_provider is None:
            empty_provider = p
        errors.append(f"{p} : aucun résultat")

    if empty_provider is not None:
        return empty_provider, []

    raise RuntimeError(
        "Recherche web indisponible : tous les moteurs ont échoué — " + " ; ".join(errors)
    )
