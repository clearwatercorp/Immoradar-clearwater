import sqlite3
import time
from contextlib import closing

from config import DB_PATH


def get_conn():
    return sqlite3.connect(DB_PATH)


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
                lat          REAL,
                lon          REAL,
                distance_km  REAL,
                date_annonce TEXT,
                link         TEXT,
                image        TEXT,
                first_seen   REAL,
                last_seen    REAL
            )
        """)
        conn.commit()


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
                         lat, lon, distance_km, date_annonce, link, image, first_seen, last_seen)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    ad["id"], ad["source"], ad.get("titre", ""), ad.get("desc", ""),
                    ad.get("prix", 0), ad.get("ville", ""), ad.get("surface", 0), ad.get("pieces"),
                    ad.get("type_bien", ""),
                    ad.get("lat"), ad.get("lon"), ad.get("distance_km"),
                    ad.get("date", ""), ad.get("link", ""), ad.get("image", ""),
                    now, now,
                ))
        conn.commit()
    return new_ids


def get_all_ads():
    with closing(get_conn()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM annonces ORDER BY first_seen DESC").fetchall()
        return [dict(r) for r in rows]
