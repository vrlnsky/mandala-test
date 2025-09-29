# ISBN Book Search App

Full-stack app to search books by ISBN via Google Books API.

## Stack
- Frontend: Next.js (App Router) + TypeScript
- Backend: Django + Django REST Framework, CORS headers

## Local Development

### Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Optional: set Google Books API key (improves quota)
# echo "GOOGLE_BOOKS_API_KEY=your_key_here" > .env && export $(cat .env | xargs)
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Endpoints:
- `GET /api/books/{isbn}/` → normalized book details
  - Behavior: tries Google Books (`q=isbn:<isbn>`), if no items:
    1) attempts ISBN-10 conversion from ISBN-13 and retries
    2) falls back to Open Library `https://openlibrary.org/isbn/{isbn}.json`

### Frontend
```bash
cd frontend
npm install
# Optionally set API base (defaults to http://localhost:8000/api)
# echo "NEXT_PUBLIC_API_BASE=http://localhost:8000/api" > .env.local
npm run dev
```

Open `http://localhost:3000` and search by ISBN-10 or ISBN-13.

## Deployment
- Deploy frontend to Vercel or Netlify
- Deploy backend to a Python host (Railway/Fly/Render). Ensure `ALLOWED_HOSTS` and CORS allow the frontend origin.
  - Set `GOOGLE_BOOKS_API_KEY` in your deployment environment.
  - Optional: set `GOOGLE_BOOKS_COUNTRY` (e.g., `US`, `JP`) to influence search market.

## Notes on Data Source
- Uses Google Books (`https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}`)

## AI/Tooling Transparency
- Portions of this repository were scaffolded and refactored with the assistance of an AI coding environment(Cursor). All generated code was reviewed and adjusted for quality, security and clarity.

