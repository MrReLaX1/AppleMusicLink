import os
import struct

from fh6_volume import DEFAUTS, PRESETS, lire_paquet, valider, volume_cible
from popup import noms_processus

baisse = {**DEFAUTS, "vol_menu": 100, "vol_arret": 80, "vol_rapide": 35, "vitesse_max": 250,
          "baisse_rupteur": 15, "baisse_gaz": 10, "courbe": 0}


def paquet(course=1, kmh=0.0, rpm=0.0, rpm_max=8000.0, gaz=0):
    p = bytearray(324)
    struct.pack_into("<iIfff", p, 0, course, 0, rpm_max, 800.0, rpm)
    struct.pack_into("<f", p, 256, kmh / 3.6)
    p[315] = gaz
    return bytes(p)


assert lire_paquet(b"\0" * 311) is None
t = lire_paquet(paquet(kmh=250, rpm=7600, gaz=255))
assert abs(t["kmh"] - 250) < 0.01 and t["gaz"] == 1
assert volume_cible(None, baisse) == 1.0
assert volume_cible(lire_paquet(paquet(course=0, kmh=100)), baisse) == 1.0
assert abs(volume_cible(lire_paquet(paquet()), baisse) - 0.80) < 1e-6
assert abs(volume_cible(t, baisse) - 0.15) < 1e-6  # 35 − 10 (rupteur à 95 %) − 10 (plein gaz)
assert abs(volume_cible(lire_paquet(paquet(kmh=125)), baisse) - 0.575) < 1e-6
assert volume_cible(lire_paquet(paquet(kmh=999)), {**baisse, "vol_rapide": 0, "baisse_gaz": 100}) == 0.0
# mode par défaut « vitesse = volume » : 20 % à l'arrêt et hors conduite, 100 % dès 190 km/h, gaz et régime sans effet
assert volume_cible(None, DEFAUTS) == 0.2
assert abs(volume_cible(lire_paquet(paquet()), DEFAUTS) - 0.2) < 1e-6
assert abs(volume_cible(lire_paquet(paquet(kmh=190, rpm=7900, gaz=255)), DEFAUTS) - 1.0) < 1e-6
monte = {**baisse, "vol_arret": 20, "vol_rapide": 100, "vitesse_max": 200, "baisse_rupteur": 0, "baisse_gaz": 0}
assert abs(volume_cible(lire_paquet(paquet(kmh=100)), monte) - 0.60) < 1e-6  # courbe 0 : moitié du chemin en %
assert abs(volume_cible(lire_paquet(paquet(kmh=100)), {**monte, "courbe": 1}) - 0.20 * 5 ** 0.5) < 1e-6  # moitié en dB
assert abs(volume_cible(lire_paquet(paquet(kmh=200)), {**monte, "courbe": 1}) - 1.0) < 1e-6
assert abs(volume_cible(lire_paquet(paquet(kmh=100)), {**monte, "vol_arret": 0, "courbe": 1}) - 0.1) < 1e-6  # plancher 1 %
for mauvais in ({"port": 5250}, {"vol_arret": "nan"}, {"lissage": None}):
    try:
        valider({**DEFAUTS, **mauvais})
    except (ValueError, TypeError):
        pass
    else:
        raise AssertionError(mauvais)
for p in PRESETS:  # chaque profil couvre tous les réglages son et reste dans les bornes
    assert set(p["reglages"]) == set(PRESETS[0]["reglages"]), p["nom"]
    assert valider({**DEFAUTS, **p["reglages"]}) == {**DEFAUTS, **p["reglages"]}, p["nom"]
assert noms_processus().get(os.getpid()) in ("python.exe", "pythonw.exe")  # liste système lue sans ouvrir de processus
print("OK")
