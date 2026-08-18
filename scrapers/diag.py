"""Diagnostic par source : mémorise *pourquoi* une source n'a rien renvoyé.

Sans ça, une source à 0 annonce est indiscernable d'une source bloquée ou
d'une page dont la structure a changé — or la correction n'est pas du tout
la même. Le détail est remonté jusqu'à l'interface.
"""

_last = {}


def set_status(source, detail, bloque=False):
    _last[source] = {"detail": detail, "bloque": bloque}


def clear(source):
    _last.pop(source, None)


def get_status(source):
    return _last.get(source)
