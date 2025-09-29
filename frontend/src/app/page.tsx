"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Book = {
  title?: string;
  subtitle?: string;
  authors: string[];
  publisher?: string;
  publishedDate?: string;
  description?: string;
  pageCount?: number;
  categories: string[];
  thumbnail?: string;
  language?: string;
  previewLink?: string;
  infoLink?: string;
  isbn10?: string | null;
  isbn13?: string | null;
};

export default function Home() {
  const [isbn, setIsbn] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [book, setBook] = useState<Book | null>(null);
  const [related, setRelated] = useState<Book[] | null>(null);
  type RecentItem = { isbn: string; title?: string; pinned: boolean; ts: number };
  const [recents, setRecents] = useState<RecentItem[]>([]);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

  // Load recents on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem("recent:isbn");
      if (raw) {
        const parsed = JSON.parse(raw) as RecentItem[];
        if (Array.isArray(parsed)) setRecents(parsed);
      }
    } catch {}
  }, []);

  const persistRecents = useCallback((items: RecentItem[]) => {
    setRecents(items);
    try { localStorage.setItem("recent:isbn", JSON.stringify(items)); } catch {}
  }, []);

  const upsertRecent = useCallback((nextIsbn: string, title?: string) => {
    const now = Date.now();
    const existing = recents.find(r => r.isbn === nextIsbn);
    let updated: RecentItem[];
    if (existing) {
      const merged: RecentItem = { ...existing, title: title ?? existing.title, ts: now };
      updated = [merged, ...recents.filter(r => r.isbn !== nextIsbn)];
    } else {
      updated = [{ isbn: nextIsbn, title, pinned: false, ts: now }, ...recents];
    }
    // keep pins, cap to 10 total
    const pins = updated.filter(r => r.pinned);
    const nonPins = updated.filter(r => !r.pinned).slice(0, Math.max(0, 10 - pins.length));
    persistRecents([...pins, ...nonPins]);
  }, [persistRecents, recents]);

  const togglePin = useCallback((target: string) => {
    const updated = recents.map(r => r.isbn === target ? { ...r, pinned: !r.pinned, ts: Date.now() } : r);
    // keep pins on top
    updated.sort((a,b) => (b.pinned?1:0) - (a.pinned?1:0) || b.ts - a.ts);
    // enforce cap again
    const pins = updated.filter(r => r.pinned);
    const nonPins = updated.filter(r => !r.pinned).slice(0, Math.max(0, 10 - pins.length));
    persistRecents([...pins, ...nonPins]);
  }, [recents, persistRecents]);

  const removeRecent = useCallback((target: string) => {
    persistRecents(recents.filter(r => r.isbn !== target));
  }, [recents, persistRecents]);

  const sortedRecents = useMemo(() => {
    const copy = [...recents];
    copy.sort((a,b) => (b.pinned?1:0) - (a.pinned?1:0) || b.ts - a.ts);
    return copy;
  }, [recents]);

  const fetchBook = useCallback(async (raw: string) => {
    setError(null);
    setBook(null);
    setRelated(null);
    const trimmed = raw.trim();
    const cleaned = trimmed.replace(/[^0-9xX]/g, "");
    if (!trimmed) {
      setError("Please enter an ISBN.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/books/${encodeURIComponent(cleaned)}/`, {
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        const maybe = await res.json().catch(() => null);
        throw new Error(maybe?.detail || `Request failed with ${res.status}`);
      }
      const data: Book = await res.json();
      setBook(data);
      upsertRecent(cleaned, data.title);
      // Fetch related
      try {
        const r = await fetch(`${apiBase}/related/${encodeURIComponent(cleaned)}/`, { headers: { "Accept": "application/json" } });
        if (r.ok) {
          const rel = await r.json();
          const items = (rel?.items || []) as Book[];
          setRelated(items);
        }
      } catch {}
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unexpected error";
      setError(message);
      upsertRecent(cleaned);
    } finally {
      setLoading(false);
    }
  }, [apiBase, upsertRecent]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    fetchBook(isbn);
  }

  return (
    <div>
      <div>
        <h1 style={{ fontSize: 32, marginBottom: 8 }}>ISBN Book Search</h1>
        <p className="muted" style={{ marginBottom: 16 }}>Enter an ISBN-10 or ISBN-13 to retrieve book details.</p>
        <form onSubmit={onSubmit} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <label htmlFor="isbn-input" className="label-hidden">ISBN</label>
          <input
            id="isbn-input"
            className="input"
            value={isbn}
            onChange={(e) => setIsbn(e.target.value)}
            placeholder="e.g. 9780131103627"
            inputMode="numeric"
            style={{ flex: 1, minWidth: 260 }}
          />
          <button className="btn" type="submit" disabled={loading}>
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        {error && (
          <div style={{ marginTop: 16, color: "#b00020" }}>{error}</div>
        )}

        {book && (
          <div className="card" style={{ marginTop: 24, display: "grid", gridTemplateColumns: "120px 1fr", gap: 16 }}>
            {book.thumbnail ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={book.thumbnail} alt={book.title || "Book cover"} style={{ width: 120, height: 160, objectFit: "cover", borderRadius: 8 }} />
            ) : (
              <div style={{ width: 120, height: 160, background: "#f3f3f3", borderRadius: 8 }} />
            )}
            <div>
              <h2 style={{ margin: 0 }}>{book.title}</h2>
              {book.subtitle && <p style={{ marginTop: 4, color: "#555" }}>{book.subtitle}</p>}
              <p style={{ marginTop: 8 }}>
                <strong>Authors:</strong> {book.authors?.length ? book.authors.join(", ") : "Unknown"}
              </p>
              <p style={{ marginTop: 4 }}>
                <strong>Publisher:</strong> {book.publisher || "Unknown"} {book.publishedDate ? `(${book.publishedDate})` : ""}
              </p>
              <p style={{ marginTop: 4 }}>
                <strong>Pages:</strong> {book.pageCount ?? "N/A"}
              </p>
              <p style={{ marginTop: 4 }}>
                <strong>Categories:</strong> {book.categories?.length ? book.categories.join(", ") : "N/A"}
              </p>
              <p style={{ marginTop: 4 }}>
                <strong>ISBN-10:</strong> {book.isbn10 ?? "N/A"} | <strong>ISBN-13:</strong> {book.isbn13 ?? "N/A"}
              </p>
              <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                {book.previewLink && (
                  <a href={book.previewLink} target="_blank" rel="noreferrer" style={{ color: "#0366d6" }}>Preview</a>
                )}
                {book.infoLink && (
                  <a href={book.infoLink} target="_blank" rel="noreferrer" style={{ color: "#0366d6" }}>More info</a>
                )}
              </div>
              {book.description && (
                <p style={{ marginTop: 12, color: "#333" }}>{book.description}</p>
              )}
            </div>
          </div>
        )}

        {related && related.length > 0 && (
          <div style={{ marginTop: 24 }}>
            <h3 style={{ margin: 0, fontSize: 18 }}>Related books</h3>
            <div className="grid" style={{ marginTop: 12 }}>
              {related.map((rb, idx) => (
                <div key={`${rb.isbn13 || rb.isbn10 || rb.infoLink || idx}`} className="card">
                  {rb.thumbnail ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={rb.thumbnail} alt={rb.title || "Book cover"} style={{ width: "100%", height: 220, objectFit: "cover", borderRadius: 6 }} />
                  ) : (
                    <div style={{ width: "100%", height: 220, background: "#f3f3f3", borderRadius: 6 }} />
                  )}
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, lineHeight: 1.3 }}>{rb.title}</div>
                    <div style={{ color: "#666", fontSize: 12 }}>{rb.authors?.join(", ")}</div>
                    {rb.infoLink && (
                      <a href={rb.infoLink} target="_blank" rel="noreferrer" style={{ color: "#0366d6", fontSize: 12 }}>Details</a>
                    )}
                  </div>
                </div>
              ))}
            </div>
        </div>
        )}

        {/* Recent searches */}
        {sortedRecents.length > 0 && (
          <div style={{ marginTop: 24 }}>
            <h3 style={{ margin: 0, fontSize: 18 }}>Recent</h3>
            <ul style={{ listStyle: "none", padding: 0, marginTop: 12, display: "grid", gap: 8 }}>
              {sortedRecents.map(r => (
                <li key={r.isbn} style={{ display: "flex", alignItems: "center", gap: 8, border: "1px solid #eee", borderRadius: 8, padding: 8 }}>
                  <button
                    onClick={() => fetchBook(r.isbn)}
                    style={{ background: "transparent", border: "none", textAlign: "left", flex: 1, cursor: "pointer" }}
                    title={r.title || r.isbn}
                  >
                    <span style={{ fontWeight: 600 }}>{r.isbn}</span>
                    {r.title && <span style={{ color: "#666", marginLeft: 8 }}>{r.title}</span>}
                    {r.pinned && <span style={{ marginLeft: 8, color: "#c47" }}>★</span>}
                  </button>
                  <button
                    onClick={() => togglePin(r.isbn)}
                    style={{
                      border: "1px solid #bbb",
                      background: "#fff",
                      color: "#111",
                      borderRadius: 8,
                      padding: "8px 12px",
                      fontSize: 14,
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    {r.pinned ? "Unpin" : "Pin"}
                  </button>
                  <button
                    onClick={() => removeRecent(r.isbn)}
                    style={{
                      border: "1px solid #bbb",
                      background: "#fff",
                      color: "#111",
                      borderRadius: 8,
                      padding: "8px 12px",
                      fontSize: 14,
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
