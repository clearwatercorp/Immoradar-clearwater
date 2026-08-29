"""Import ponctuel d'une fiche PDF d'annonce (mandat agence, export portail…)
pour en calculer la rentabilité sans passer par le monitoring.

Les fiches PDF n'ont pas de format standard : on extrait le texte, puis on
repère les champs par des motifs robustes et par PROXIMITÉ (chaque montant/
surface est rattaché au bien le plus proche dans le texte). Une même fiche
peut contenir plusieurs biens — on les sépare via les prix de vente détectés.

L'extraction est forcément imparfaite selon l'agence : l'interface laisse
l'utilisateur corriger chaque champ avant le calcul.
"""

import re
import unicodedata


def _fold(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def extract_text(path_or_bytes):
    """Texte concaténé du PDF. Accepte un chemin ou des octets."""
    from pypdf import PdfReader
    import io
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) else path_or_bytes
    reader = PdfReader(src)
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _to_int(txt):
    s = re.sub(r"[^\d]", "", txt or "")
    return int(s) if s else 0


def _to_float(txt):
    s = re.sub(r"[^\d,.]", "", txt or "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


# Prix de vente : un gros montant en euros (≥ 30 000, ≤ 5 M). On EXCLUT ce qui
# suit immédiatement « charges/quote-part » et les montants « /an » ou « /mois ».
_PRIX_RE = re.compile(r"(\d[\d  .]{4,})\s*€", re.I)
_SURFACE_RE = re.compile(r"(\d{2,3}(?:[.,]\d{1,2})?)\s*m²", re.I)
# CP à 5 chiffres ISOLÉ (pas au milieu d'un n° SIRET/CPI), suivi d'une virgule
# et d'une ville commençant par une majuscule.
_CP_VILLE_RE = re.compile(r"(?<!\d)(\d{5})\s*,\s*([A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-\s]{1,26})")
_PIECES_RE = re.compile(r"(\d)\s*pi[eè]ce", re.I)
_CHARGES_RE = re.compile(r"charges?[^\d€]{0,20}(\d[\d  .]{0,7})\s*€\s*/?\s*(mois|an)", re.I)
# DPE : la lettre entre parenthèses après « kWh/m².an (X) », ou « DPE … : X ».
_DPE_RE = re.compile(r"kWh/m²\.?\s*an\s*\(([A-G])\)|DPE[^:()]{0,60}:\s*([A-G])\b", re.I)
_TAXE_RE = re.compile(r"taxe\s+fonci[èe]re[^\d€]{0,12}(\d[\d  .]{0,7})\s*€", re.I)

_SURFACE_CTX_BON = ("habitable", "carrez", "loi carrez")
_SURFACE_CTX_MAUVAIS = ("terrain", "jardin", "terrasse", "sejour", "séjour", "chambre", "salon")


def _positions(regex, text):
    return [(m.start(), m) for m in regex.finditer(text)]


def _nearest(pos, candidates):
    """Renvoie le match de `candidates` (liste de (position, m)) le plus proche
    de `pos`, ou None."""
    best = None
    for cpos, m in candidates:
        d = abs(cpos - pos)
        if best is None or d < best[0]:
            best = (d, m)
    return best[1] if best else None


def parse(text):
    """Retourne une liste de biens {prix, surface, pieces, ville, cp, charges_
    mensuelles, dpe, etat, libre, titre, desc}. Un par prix de vente plausible."""
    prix_matches = []
    for m in _PRIX_RE.finditer(text):
        val = _to_int(m.group(1))
        if 30000 <= val <= 5_000_000:
            # écarte « charges … 170 € » et montants périodiques juste après
            suffixe = text[m.end():m.end() + 6].lower()
            if "/an" in suffixe or "/mois" in suffixe:
                continue
            prix_matches.append((m.start(), val))

    # Dédoublonne les prix identiques proches (répétés d'une page à l'autre) :
    # on garde la 1re occurrence de chaque valeur.
    vus = {}
    prix_uniques = []
    for pos, val in prix_matches:
        if val not in vus:
            vus[val] = pos
            prix_uniques.append((pos, val))

    surfaces = _positions(_SURFACE_RE, text)
    # CP+Ville des BIENS uniquement : on écarte l'adresse de l'AGENCE, qui se
    # répète dans les pieds de page (« 06600, Antibes, France », près de
    # « AVENUE », « SIRET », « caisse de garantie »…) et fausserait tout.
    cpvilles = []
    for cpos, cm in _positions(_CP_VILLE_RE, text):
        suite = text[cm.end(): cm.end() + 9].lower()
        ctx = _fold(text[max(0, cpos - 70): cpos + 40])
        if suite.startswith(", france") or "france" in _fold(suite):
            continue
        if any(t in ctx for t in ("avenue", "siret", "caisse de garantie", "rsac",
                                  "center bay", "centerbay", "cpi ", "@", "assurance")):
            continue
        cpvilles.append((cpos, cm))

    biens = []
    for pos, prix in prix_uniques:
        # Bloc DESCRIPTION (titre + prose) autour du prix.
        bloc_desc = text[max(0, pos - 120): pos + 1400]
        # Bloc INFOS structurées : autour du couple CP+Ville le plus proche
        # (« 06600, Antibes » — c'est là que vivent surface Carrez, charges,
        # état, disponibilité). À défaut, on reste sur le bloc description.
        cvm = _nearest(pos, cpvilles)
        if cvm:
            a = cvm.start()
            bloc_info = text[max(0, a - 500): a + 700]
            cp = cvm.group(1)
            ville = re.split(r"\s{2,}|\n|,", cvm.group(2).strip())[0].strip()
        else:
            bloc_info = bloc_desc
            cp, ville = "", ""

        # Surface : préférer une valeur du bloc infos (Carrez), en écartant les
        # m² « hors sujet » (jardin/terrasse/pièce).
        surface = _surface_bloc(bloc_info) or _surface_bloc(bloc_desc)

        pm = _PIECES_RE.search(bloc_desc) or _PIECES_RE.search(bloc_info)
        pieces = _to_int(pm.group(1)) if pm else None

        cm = _CHARGES_RE.search(bloc_info) or _CHARGES_RE.search(bloc_desc)
        charges = None
        if cm:
            montant = _to_int(cm.group(1))
            charges = round(montant / 12) if cm.group(2).lower() == "an" else montant

        dm = _DPE_RE.search(bloc_info) or _DPE_RE.search(bloc_desc)
        dpe = (dm.group(1) or dm.group(2)).upper() if dm else None

        low_info = _fold(bloc_info)
        libre = ("disponibilite : libre" in low_info or "libre de suite" in low_info
                 or "disponibilite: libre" in low_info)

        etat = ""
        me = re.search(r"[EÉ]tat\s*:?\s*([A-Za-zÀ-ÿ' ]{3,20})", bloc_info)
        if me:
            etat = me.group(1).strip().rstrip(" ·-")

        biens.append({
            "prix": prix,
            "surface": surface,
            "pieces": pieces,
            "ville": ville,
            "cp": cp,
            "charges_mensuelles": charges,
            "taxe_fonciere": _taxe(bloc_info),
            "dpe": dpe,
            "etat": etat,
            "libre": bool(libre),
            "titre": _titre(bloc_desc),
            "desc": _desc(bloc_desc),
        })
    return biens


def _surface_bloc(bloc):
    """Surface habitable la plus plausible d'un bloc : priorité au voisinage
    de « Carrez »/« habitable », en écartant jardin/terrasse/pièces."""
    best = 0
    for m in _SURFACE_RE.finditer(bloc):
        ctx = _fold(bloc[max(0, m.start() - 30): m.start()])
        if any(w in ctx for w in _SURFACE_CTX_MAUVAIS) and not any(w in ctx for w in _SURFACE_CTX_BON):
            continue
        val = round(_to_float(m.group(1)))
        if any(w in ctx for w in _SURFACE_CTX_BON):
            return val  # étiquette explicite : on tranche
        if val > best:
            best = val
    return best


def _titre(bloc):
    for ligne in bloc.splitlines():
        l = ligne.strip()
        if len(l) > 15 and ("vendre" in l.lower() or "pieces" in _fold(l) or "pièces" in l.lower()):
            return l[:120]
    return ""


def _desc(bloc):
    # Plus longue ligne « prose » du bloc.
    lignes = [l.strip() for l in bloc.splitlines() if len(l.strip()) > 60]
    return max(lignes, key=len)[:1500] if lignes else bloc.strip()[:600]


def _taxe(bloc):
    m = _TAXE_RE.search(bloc)
    return _to_int(m.group(1)) if m else None


def _norm_ville(v):
    return _fold(v).replace("-", " ").strip()


def find_duplicate(bien, existing):
    """Un bien du PDF fait-il DOUBLON avec une annonce déjà en base ? On se base
    sur prix + surface (signal fort, quel que soit le libellé de la ville),
    avec tolérance. Retourne l'annonce existante correspondante, ou None."""
    prix = bien.get("prix") or 0
    surf = bien.get("surface") or 0
    if prix <= 0 or surf <= 0:
        return None
    tol_prix = max(2000, prix * 0.02)
    for e in existing:
        ep = e.get("prix") or 0
        es = e.get("surface") or 0
        if ep <= 0 or es <= 0:
            continue
        if abs(prix - ep) <= tol_prix and abs(surf - es) <= 2:
            return e
    return None
