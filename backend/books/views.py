import requests
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework import status
from django.conf import settings
from django.core.cache import cache
import re
def _isbn13_to_isbn10(isbn13: str) -> str | None:
    if len(isbn13) != 13 or not isbn13.isdigit() or not isbn13.startswith('978'):
        return None
    core = isbn13[3:12]
    total = 0
    for idx, ch in enumerate(core, start=1):
        total += int(ch) * (10 - idx)
    check_val = 11 - (total % 11)
    if check_val == 10:
        check = 'X'
    elif check_val == 11:
        check = '0'
    else:
        check = str(check_val)
    return core + check



def _normalize_google_books_item(item: dict) -> dict:
    volume = item.get('volumeInfo', {})
    industry_identifiers = volume.get('industryIdentifiers', []) or []
    isbn_10 = next((i.get('identifier') for i in industry_identifiers if i.get('type') == 'ISBN_10'), None)
    isbn_13 = next((i.get('identifier') for i in industry_identifiers if i.get('type') == 'ISBN_13'), None)
    return {
        'title': volume.get('title'),
        'subtitle': volume.get('subtitle'),
        'authors': volume.get('authors') or [],
        'publisher': volume.get('publisher'),
        'publishedDate': volume.get('publishedDate'),
        'description': volume.get('description'),
        'pageCount': volume.get('pageCount'),
        'categories': volume.get('categories') or [],
        'thumbnail': (volume.get('imageLinks') or {}).get('thumbnail'),
        'language': volume.get('language'),
        'previewLink': volume.get('previewLink'),
        'infoLink': volume.get('infoLink'),
        'isbn10': isbn_10,
        'isbn13': isbn_13,
    }


@api_view(['GET'])
def get_book_by_isbn(request, isbn: str):
    # Sanitize and validate ISBN: remove non [0-9Xx], uppercase X
    cleaned = re.sub(r"[^0-9xX]", "", isbn).upper()
    if len(cleaned) not in (10, 13):
        return JsonResponse({'detail': 'Invalid ISBN. Use ISBN-10 or ISBN-13.', 'code': 'INVALID_ISBN'}, status=status.HTTP_400_BAD_REQUEST)

    # Cache by cleaned ISBN
    cached = cache.get(f"isbn:{cleaned}")
    if cached is not None:
        return JsonResponse(cached, status=status.HTTP_200_OK)

    query = f"isbn:{cleaned}"
    url = 'https://www.googleapis.com/books/v1/volumes'
    params = {'q': query}
    if getattr(settings, 'GOOGLE_BOOKS_API_KEY', None):
        params['key'] = settings.GOOGLE_BOOKS_API_KEY
    if getattr(settings, 'GOOGLE_BOOKS_COUNTRY', None):
        params['country'] = settings.GOOGLE_BOOKS_COUNTRY
    try:
        # Prepare the exact URL for logging/debug
        prepared = requests.Request('GET', url, params=params).prepare()
        if settings.DEBUG:
            print("[GoogleBooks] GET", prepared.url)
        response = requests.Session().send(prepared, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        payload = {'detail': 'Upstream error', 'error': str(exc)}
        if settings.DEBUG:
            payload['debug'] = {'url': url, 'params': params}
        return JsonResponse(payload, status=status.HTTP_502_BAD_GATEWAY)

    items = data.get('items') or []
    # Fallback 1: try ISBN-10 if possible
    if not items and len(cleaned) == 13:
        maybe10 = _isbn13_to_isbn10(cleaned)
        if maybe10:
            alt_params = dict(params)
            alt_params['q'] = f"isbn:{maybe10}"
            prepared_alt = requests.Request('GET', url, params=alt_params).prepare()
            if settings.DEBUG:
                print("[GoogleBooks:Fallback-ISBN10] GET", prepared_alt.url)
            try:
                alt_resp = requests.Session().send(prepared_alt, timeout=10)
                alt_resp.raise_for_status()
                alt_data = alt_resp.json()
                items = alt_data.get('items') or []
            except requests.RequestException:
                items = []

    # Fallback 2: Open Library if still empty
    if not items:
        try:
            ol_url = f"https://openlibrary.org/isbn/{cleaned}.json"
            if settings.DEBUG:
                print("[OpenLibrary] GET", ol_url)
            ol_resp = requests.get(ol_url, timeout=10)
            if ol_resp.status_code == 200:
                ol = ol_resp.json()
                normalized = {
                    'title': ol.get('title'),
                    'subtitle': None,
                    'authors': [],
                    'publisher': (ol.get('publishers') or [None])[0],
                    'publishedDate': ol.get('publish_date'),
                    'description': ol.get('description', None) if isinstance(ol.get('description'), str) else (ol.get('description', {}) or {}).get('value'),
                    'pageCount': ol.get('number_of_pages'),
                    'categories': [],
                    'thumbnail': f"https://covers.openlibrary.org/b/isbn/{cleaned}-L.jpg",
                    'language': None,
                    'previewLink': None,
                    'infoLink': f"https://openlibrary.org{ol.get('key')}" if ol.get('key') else None,
                    'isbn10': (ol.get('isbn_10') or [None])[0],
                    'isbn13': (ol.get('isbn_13') or [None])[0],
                }
                cache.set(f"isbn:{cleaned}", normalized, 600)
                return JsonResponse(normalized, status=status.HTTP_200_OK)
        except requests.RequestException:
            pass

    # Fallback 3: Open Library Books API exact lookup
    if not items:
        try:
            books_url = "https://openlibrary.org/api/books"
            books_params = {"bibkeys": f"ISBN:{cleaned}", "format": "json", "jscmd": "data"}
            prepared_books = requests.Request('GET', books_url, params=books_params).prepare()
            if settings.DEBUG:
                print("[OpenLibrary:BooksAPI] GET", prepared_books.url)
            books_resp = requests.Session().send(prepared_books, timeout=10)
            if books_resp.status_code == 200:
                data_map = books_resp.json() or {}
                record = data_map.get(f"ISBN:{cleaned}")
                if record:
                    authors = [a.get('name') for a in (record.get('authors') or []) if isinstance(a, dict)]
                    publishers = [p.get('name') for p in (record.get('publishers') or []) if isinstance(p, dict)]
                    subjects = [s.get('name') for s in (record.get('subjects') or []) if isinstance(s, dict)]
                    cover = (record.get('cover') or {})
                    normalized = {
                        'title': record.get('title'),
                        'subtitle': None,
                        'authors': authors,
                        'publisher': publishers[0] if publishers else None,
                        'publishedDate': record.get('publish_date'),
                        'description': None,
                        'pageCount': record.get('number_of_pages'),
                        'categories': subjects,
                        'thumbnail': cover.get('large') or cover.get('medium') or cover.get('small') or f"https://covers.openlibrary.org/b/isbn/{cleaned}-L.jpg",
                        'language': None,
                        'previewLink': record.get('url'),
                        'infoLink': record.get('url'),
                        'isbn10': None,
                        'isbn13': cleaned,
                    }
                    cache.set(f"isbn:{cleaned}", normalized, 600)
                    return JsonResponse(normalized, status=status.HTTP_200_OK)
        except requests.RequestException:
            pass

    # Fallback 4: Open Library search API (only if exact ISBN appears in doc)
    if not items:
        try:
            search_url = "https://openlibrary.org/search.json"
            search_params = {"isbn": cleaned, "limit": 5}
            prepared_search = requests.Request('GET', search_url, params=search_params).prepare()
            if settings.DEBUG:
                print("[OpenLibrary:Search] GET", prepared_search.url)
            search_resp = requests.Session().send(prepared_search, timeout=10)
            if search_resp.status_code == 200:
                sr = search_resp.json()
                docs = sr.get('docs') or []
                # Only accept docs that explicitly include the exact ISBN
                exact_docs = [d for d in docs if cleaned in (d.get('isbn') or [])]
                if exact_docs:
                    chosen = exact_docs[0]
                    d0 = chosen
                    author_names = d0.get('author_name') or []
                    publisher = (d0.get('publisher') or [None])[0]
                    publish_year = (d0.get('publish_year') or [None])[0]
                    all_isbns = d0.get('isbn') or []
                    isbn10_val = next((x for x in all_isbns if x and len(x) == 10), None)
                    normalized = {
                        'title': d0.get('title'),
                        'subtitle': None,
                        'authors': author_names,
                        'publisher': publisher,
                        'publishedDate': str(publish_year) if publish_year else None,
                        'description': None,
                        'pageCount': None,
                        'categories': d0.get('subject') or [],
                        'thumbnail': f"https://covers.openlibrary.org/b/isbn/{cleaned}-L.jpg",
                        'language': (d0.get('language') or [None])[0],
                        'previewLink': None,
                        'infoLink': f"https://openlibrary.org{d0.get('key')}" if d0.get('key') else None,
                        'isbn10': isbn10_val,
                        'isbn13': cleaned,
                    }
                    cache.set(f"isbn:{cleaned}", normalized, 600)
                    return JsonResponse(normalized, status=status.HTTP_200_OK)
        except requests.RequestException:
            pass

    if not items:
        payload = {'detail': 'Book not found'}
        if settings.DEBUG:
            payload['debug'] = {
                'url': url,
                'params': params,
                'totalItems': data.get('totalItems')
            }
        return JsonResponse(payload, status=status.HTTP_404_NOT_FOUND)

    normalized = _normalize_google_books_item(items[0])
    cache.set(f"isbn:{cleaned}", normalized, 600)
    return JsonResponse(normalized, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_related_by_isbn(request, isbn: str):
    cleaned = re.sub(r"[^0-9xX]", "", isbn).upper()
    if len(cleaned) not in (10, 13):
        return JsonResponse({'detail': 'Invalid ISBN. Use ISBN-10 or ISBN-13.', 'code': 'INVALID_ISBN'}, status=status.HTTP_400_BAD_REQUEST)

    cached = cache.get(f"related:{cleaned}")
    if cached is not None:
        return JsonResponse({'items': cached}, status=status.HTTP_200_OK)

    # First fetch the primary book to derive author/categories
    primary = cache.get(f"isbn:{cleaned}")
    if primary is None:
        prim_resp = get_book_by_isbn(request, cleaned)
        if prim_resp.status_code != 200:
            return prim_resp
        primary = prim_resp.json()

    authors = primary.get('authors') or []
    categories = primary.get('categories') or []

    search_terms = []
    if authors:
        search_terms.append(f"inauthor:{authors[0]}")
    if categories:
        # Take first category as a seed
        search_terms.append(f"subject:{categories[0]}")
    if not search_terms and primary.get('title'):
        search_terms.append(primary['title'])

    related: list[dict] = []
    url = 'https://www.googleapis.com/books/v1/volumes'
    for term in search_terms:
        params = {'q': term, 'maxResults': 10}
        if getattr(settings, 'GOOGLE_BOOKS_API_KEY', None):
            params['key'] = settings.GOOGLE_BOOKS_API_KEY
        if getattr(settings, 'GOOGLE_BOOKS_COUNTRY', None):
            params['country'] = settings.GOOGLE_BOOKS_COUNTRY

        try:
            prepared = requests.Request('GET', url, params=params).prepare()
            if settings.DEBUG:
                print("[GoogleBooks:Related] GET", prepared.url)
            resp = requests.Session().send(prepared, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            continue

        items = data.get('items') or []
        for it in items:
            norm = _normalize_google_books_item(it)
            # Skip if same as primary
            if norm.get('isbn13') == primary.get('isbn13') or norm.get('isbn10') == primary.get('isbn10'):
                continue
            # Deduplicate by infoLink/title
            key = (norm.get('isbn13') or norm.get('isbn10') or norm.get('infoLink') or norm.get('title'))
            if key and all((key != (x.get('isbn13') or x.get('isbn10') or x.get('infoLink') or x.get('title'))) for x in related):
                related.append({
                    'title': norm.get('title'),
                    'authors': norm.get('authors') or [],
                    'thumbnail': norm.get('thumbnail'),
                    'infoLink': norm.get('infoLink'),
                    'isbn10': norm.get('isbn10'),
                    'isbn13': norm.get('isbn13'),
                })
        if len(related) >= 10:
            break

    cache.set(f"related:{cleaned}", related[:10], 600)
    return JsonResponse({'items': related[:10]}, status=status.HTTP_200_OK)
