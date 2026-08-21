"""Stockage des annonces.

Deux back-ends, choisis automatiquement selon la configuration :

* **Turso** (libSQL, SQLite hébergé, gratuit et PERSISTANT) dès que
  TURSO_DATABASE_URL et TURSO_AUTH_TOKEN sont définis. Recommandé en
  hébergement : les résultats survivent aux redéploiements et au sommeil du
  service Render (dont le disque est éphémère).
* **SQLite local** sinon (développement, usage sur sa propre machine).

Le SQL est du SQLite standard, identique pour les deux moteurs. On évite toute
dépendance à `sqlite3.Row` ou à `cursor.rowcount` (non garantis côté libSQL) :
les lignes sont converties en dictionnaires à partir de `cursor.description`.
"""

import sqlite3
import time
from contextlib import closing

from config import DB_PATH, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN

_USE_TURSO = bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)


def storage_backend():
    return "turso" if _USE_TURSO else "sqlite-local"


def persistant():
    """Vrai si le stockage survit à un redémarrage de l'hébergeur."""
    return _USE_TURSO


def get_conn():
    """Nouvelle connexion (une par opération : simple et thread-safe). En mode
    Turso, connexion distante directe à la base libSQL."""
    if _USE_TURSO:
        import libsql_experimental as libsql
        return libsql.connect(database=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
    return sqlite3.connect(DB_PATH)


def _fetch_dicts(cur):
    """Transforme le résultat d'un curseur en liste de dicts, sans dépendre de
    row_factory (indisponible côté libSQL)."""
    if cur.description is None:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def init_db():
    with closing(get_conn()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS annonces (
                id           TEXT PRIMARY KEY,
                source       TEXT,
                titre        TEXT,
                desc         TEXT,
                prix         INTEGER,
                ville        TEXT,
                surface      INTEGER,
                pieces       INTEGER,
                type_bien    TEXT,
                charges_mensuelles INTEGER,
                dpe          TEXT,
                cp           TEXT,
                lat          REAL,
                lon          REAL,
                distance_km  REAL,
                date_annonce TEXT,
                link         TEXT,
                image        TEXT,
                note_statut  TEXT DEFAULT '',
                note_texte   TEXT DEFAULT '',
                first_seen   REAL,
                last_seen    REAL
            )
        """)
        # Migration douce pour les bases créées avant ces colonnes. On attrape
        # large : selon le moteur, « colonne déjà présente » lève une erreur de
        # type différent (sqlite3.OperationalError vs erreur libSQL).
        for col, ddl in (("note_statut", "TEXT DEFAULT ''"),
                         ("note_texte", "TEXT DEFAULT ''"),
                         ("charges_mensuelles", "INTEGER"),
                         ("loyer_reel", "INTEGER"),
                         ("favori", "INTEGER DEFAULT 0")):
            try:
                conn.execute(f"ALTER TABLE annonces ADD COLUMN {col} {ddl}")
            except Exception:
                pass  # colonne déjà présente
        conn.commit()


def clear_all():
    """Vide la liste MAIS conserve les biens suivis : mis en favori, ou
    annotés (statut ou note). Ils ne doivent pas disparaître quand on repart
    sur de nouveaux critères."""
    with closing(get_conn()) as conn:
        conn.execute("""
            DELETE FROM annonces
            WHERE COALESCE(favori,0)=0
              AND COALESCE(note_statut,'')=''
              AND COALESCE(note_texte,'')=''
        """)
        conn.commit()


def set_favori(ad_id, favori):
    with closing(get_conn()) as conn:
        conn.execute("UPDATE annonces SET favori=? WHERE id=?", (1 if favori else 0, ad_id))
        conn.commit()
        return True


def set_note(ad_id, statut, texte):
    with closing(get_conn()) as conn:
        conn.execute(
            "UPDATE annonces SET note_statut=?, note_texte=? WHERE id=?",
            (statut or "", texte or "", ad_id),
        )
        conn.commit()
        return True


def upsert_ads(ads):
    """Insère les nouvelles annonces, met à jour last_seen pour les connues.
    Retourne la liste des ids nouvellement vus."""
    now = time.time()
    new_ids = []
    with closing(get_conn()) as conn:
        for ad in ads:
            row = conn.execute("SELECT id FROM annonces WHERE id=?", (ad["id"],)).fetchone()
            if row:
                conn.execute("UPDATE annonces SET last_seen=? WHERE id=?", (now, ad["id"]))
            else:
                new_ids.append(ad["id"])
                conn.execute("""
                    INSERT INTO annonces
                        (id, source, titre, desc, prix, ville, surface, pieces, type_bien,
                         charges_mensuelles, loyer_reel, dpe, cp,
                         lat, lon, distance_km, date_annonce, link, image, first_seen, last_seen)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    ad["id"], ad["source"], ad.get("titre", ""), ad.get("desc", ""),
                    ad.get("prix", 0), ad.get("ville", ""), ad.get("surface", 0), ad.get("pieces"),
                    ad.get("type_bien", ""), ad.get("charges_mensuelles"), ad.get("loyer_reel"),
                    ad.get("dpe"), ad.get("cp", ""),
                    ad.get("lat"), ad.get("lon"), ad.get("distance_km"),
                    ad.get("date", ""), ad.get("link", ""), ad.get("image", ""),
                    now, now,
                ))
        conn.commit()
    return new_ids


def get_all_ads():
    with closing(get_conn()) as conn:
        cur = conn.execute("SELECT * FROM annonces ORDER BY first_seen DESC")
        return _fetch_dicts(cur)


# Colonnes exportées/réimportées (tout sauf les timestamps techniques, qu'on
# régénère à l'import).
_EXPORT_COLS = [
    "id", "source", "titre", "desc", "prix", "ville", "surface", "pieces",
    "type_bien", "charges_mensuelles", "loyer_reel", "dpe", "cp", "lat", "lon",
    "distance_km", "date_annonce", "link", "image",
    "note_statut", "note_texte", "favori",
]


def export_saved():
    """Biens SUIVIS (favori ou annotés) avec toutes leurs données, pour une
    sauvegarde hors-ligne que l'utilisateur peut réimporter plus tard."""
    with closing(get_conn()) as conn:
        cur = conn.execute("""
            SELECT * FROM annonces
            WHERE COALESCE(favori,0)=1
               OR COALESCE(note_statut,'')<>''
               OR COALESCE(note_texte,'')<>''
            ORDER BY first_seen DESC
        """)
        rows = _fetch_dicts(cur)
        return [{k: r.get(k) for k in _EXPORT_COLS} for r in rows]


def import_saved(items):
    """Réinjecte des biens suivis exportés. Insère le bien s'il est absent,
    sinon ne met à jour QUE le favori et la note (on préserve les données de
    marché fraîches déjà présentes). Retourne le nombre traité."""
    now = time.time()
    n = 0
    cols = _EXPORT_COLS + ["first_seen", "last_seen"]
    placeholders = ",".join("?" for _ in cols)
    sql = f"""
        INSERT INTO annonces ({",".join(cols)}) VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET
            favori      = excluded.favori,
            note_statut = excluded.note_statut,
            note_texte  = excluded.note_texte
    """
    with closing(get_conn()) as conn:
        for it in items or []:
            if not isinstance(it, dict) or not it.get("id"):
                continue
            # libSQL exige un tuple (sqlite3 tolérait une liste).
            vals = tuple(it.get(c) for c in _EXPORT_COLS) + (now, now)
            try:
                conn.execute(sql, vals)
                n += 1
            except Exception:
                pass
        conn.commit()
    return n
