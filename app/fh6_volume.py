"""Règle le volume d'Apple Music selon la conduite dans Forza Horizon 6 (Data Out), avec une interface web locale."""
import ctypes
import json
import math
import socket
import struct
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pystray
from comtypes import COMError
from PIL import Image
from pycaw.pycaw import AudioUtilities

import popup

ICI = Path(__file__).resolve().parent
if sys.stdout is None:  # lancé sans console (pythonw, par AppleMusicLink.exe) : on garde une trace des erreurs
    sys.stdout = sys.stderr = open(ICI / "journal.txt", "a", encoding="utf-8", buffering=1)
VERSION = (ICI / "VERSION").read_text(encoding="utf-8").strip() if (ICI / "VERSION").exists() else "dev"
FICHIER_REGLAGES = ICI / "reglages.json"
PAGE = ICI / "index.html"
APPS = {"applemusic.exe", "amplibraryagent.exe"}  # le son d'Apple Music sort par son agent AMPLibraryAgent
PORT_WEB = 8766  # 8765 est pris par la version pour l'autre lecteur
ADRESSE = f"http://127.0.0.1:{PORT_WEB}"
HOTES = {f"127.0.0.1:{PORT_WEB}", f"localhost:{PORT_WEB}"}
TAILLE_PAQUET = 324  # format FH6 fixe (doc Forza « Data Out »)
ROUES = ("FrontLeft", "FrontRight", "RearLeft", "RearRight")
CHAMPS_FH6 = (  # dans l'ordre de la doc Forza, noms d'origine
    [("IsRaceOn", "i"), ("TimestampMS", "I"), ("EngineMaxRpm", "f"), ("EngineIdleRpm", "f"), ("CurrentEngineRpm", "f")]
    + [(n + a, "f") for n in ("Acceleration", "Velocity", "AngularVelocity") for a in "XYZ"]
    + [("Yaw", "f"), ("Pitch", "f"), ("Roll", "f")]
    + [(n + r, t) for n, t in (("NormalizedSuspensionTravel", "f"), ("TireSlipRatio", "f"), ("WheelRotationSpeed", "f"),
                                ("WheelOnRumbleStrip", "i"), ("WheelInPuddle", "i"), ("SurfaceRumble", "f"),
                                ("TireSlipAngle", "f"), ("TireCombinedSlip", "f"), ("SuspensionTravelMeters", "f"))
       for r in ROUES]
    + [("CarOrdinal", "i"), ("CarClass", "i"), ("CarPerformanceIndex", "i"), ("DrivetrainType", "i"), ("NumCylinders", "i"),
       ("CarGroup", "I"), ("SmashableVelDiff", "f"), ("SmashableMass", "f"), ("PositionX", "f"), ("PositionY", "f"),
       ("PositionZ", "f"), ("Speed", "f"), ("Power", "f"), ("Torque", "f")]
    + [("TireTemp" + r, "f") for r in ROUES]
    + [("Boost", "f"), ("Fuel", "f"), ("DistanceTraveled", "f"), ("BestLap", "f"), ("LastLap", "f"), ("CurrentLap", "f"),
       ("CurrentRaceTime", "f"), ("LapNumber", "H"), ("RacePosition", "B"), ("Accel", "B"), ("Brake", "B"), ("Clutch", "B"),
       ("HandBrake", "B"), ("Gear", "B"), ("Steer", "b"), ("NormalizedDrivingLine", "b"), ("NormalizedAIBrakeDifference", "b")]
)
FORMAT_FH6 = "<" + "".join(t for _, t in CHAMPS_FH6) + "x"  # un octet de bourrage final
assert struct.calcsize(FORMAT_FH6) == TAILLE_PAQUET
SILENCE = 0.5  # FH6 n'envoie rien en menu, pause ou rembobinage

DEFAUTS = {
    "auto": True,
    "port": 5555,
    "vol_menu": 20,
    "vol_arret": 20,
    "vol_rapide": 100,
    "vitesse_max": 190,
    "baisse_rupteur": 0,
    "baisse_gaz": 0,
    "lissage": 0.8,
    "courbe": 1.0,
    "popup": True,
}
BORNES = {
    "port": (1024, 65535),
    "vol_menu": (0, 100),
    "vol_arret": (0, 100),
    "vol_rapide": (0, 100),
    "vitesse_max": (50, 500),
    "baisse_rupteur": (0, 100),
    "baisse_gaz": (0, 100),
    "lissage": (0.05, 5),
    "courbe": (0, 1),
}
PRESETS = [
    {"nom": "Équilibré", "aide": "La musique monte avec la vitesse",
     "reglages": {k: v for k, v in DEFAUTS.items() if k not in ("auto", "port", "popup")}},
    {"nom": "Moteur d'abord", "aide": "La musique s'efface vite derrière le moteur",
     "reglages": {"vol_menu": 100, "vol_arret": 60, "vol_rapide": 15, "vitesse_max": 200,
                  "baisse_rupteur": 20, "baisse_gaz": 15, "lissage": 0.4, "courbe": 0}},
    {"nom": "Musique d'abord", "aide": "Le moteur en fond, la musique devant",
     "reglages": {"vol_menu": 100, "vol_arret": 95, "vol_rapide": 70, "vitesse_max": 300,
                  "baisse_rupteur": 5, "baisse_gaz": 5, "lissage": 0.8, "courbe": 0}},
    {"nom": "Course", "aide": "Réactif, musique très basse à fond",
     "reglages": {"vol_menu": 100, "vol_arret": 50, "vol_rapide": 10, "vitesse_max": 180,
                  "baisse_rupteur": 25, "baisse_gaz": 20, "lissage": 0.25, "courbe": 0}},
    {"nom": "Balade", "aide": "Transitions lentes, pour rouler tranquille",
     "reglages": {"vol_menu": 100, "vol_arret": 90, "vol_rapide": 60, "vitesse_max": 250,
                  "baisse_rupteur": 0, "baisse_gaz": 5, "lissage": 1.5, "courbe": 0}},
]


def borner(x, bas=0.0, haut=1.0):
    return min(max(x, bas), haut)


def valider(d):
    """Réglages propres à partir d'un dict venu de la page ou du fichier, sinon ValueError/TypeError."""
    r = {"auto": bool(d["auto"]), "popup": bool(d["popup"])}
    for cle, (bas, haut) in BORNES.items():
        v = float(d[cle])
        if not math.isfinite(v):
            raise ValueError(f"{cle} invalide")
        r[cle] = borner(v, bas, haut)
    r["port"] = int(r["port"])
    if 5200 <= r["port"] <= 5300:
        raise ValueError("Les ports 5200 à 5300 sont pris par FH6 lui-même")
    return r


def charger():
    try:
        return valider({**DEFAUTS, **json.loads(FICHIER_REGLAGES.read_text(encoding="utf-8"))})
    except (OSError, ValueError, TypeError):
        return dict(DEFAUTS)


def lire_paquet(p):
    if len(p) != TAILLE_PAQUET:
        return None
    d = {nom: (v if not isinstance(v, float) or math.isfinite(v) else 0.0)
         for (nom, _), v in zip(CHAMPS_FH6, struct.unpack(FORMAT_FH6, p))}
    return {
        "course": d["IsRaceOn"] == 1,
        "kmh": max(d["Speed"], 0.0) * 3.6,
        "rpm": d["CurrentEngineRpm"],
        "rpm_max": d["EngineMaxRpm"],
        "gaz": d["Accel"] / 255,
        "frein": d["Brake"] / 255,
        "rapport": d["Gear"],
        # télémétrie avancée, affichée seulement si on la déplie dans l'interface
        "ch": round(max(d["Power"], 0) / 735.5),  # W → ch
        "couple": round(max(d["Torque"], 0)),
        "turbo": round(max(d["Boost"], 0) * 0.0689476, 2),  # PSI → bar
        "g_lat": round(d["AccelerationX"] / 9.81, 2),
        "g_long": round(d["AccelerationZ"] / 9.81, 2),
        "pneus_c": [round((d["TireTemp" + r] - 32) / 1.8) for r in ROUES],  # en °F comme dans FH4/FH5
        "glisse": [round(d["TireCombinedSlip" + r], 2) for r in ROUES],
        "suspension": [round(borner(d["NormalizedSuspensionTravel" + r]), 2) for r in ROUES],
        "ip": d["CarPerformanceIndex"],
        "transmission": d["DrivetrainType"],
        "cylindres": d["NumCylinders"],
        "position": d["RacePosition"],
        "tour": d["LapNumber"],
        "tour_actuel": round(d["CurrentLap"], 3),
        "dernier_tour": round(d["LastLap"], 3),
        "meilleur_tour": round(d["BestLap"], 3),
        "distance_km": round(max(d["DistanceTraveled"], 0) / 1000, 2),
        "embrayage": d["Clutch"] / 255,
        "frein_main": d["HandBrake"] / 255,
        "direction": round(d["Steer"] / 127, 2),
    }


def volume_cible(t, s):
    """Volume voulu (0 à 1) ; t = dernière télémétrie, None hors conduite."""
    if not s["auto"] or t is None or not t["course"]:
        return s["vol_menu"] / 100
    a, b, x = s["vol_arret"], s["vol_rapide"], borner(t["kmh"] / s["vitesse_max"])
    v = a + (b - a) * x
    a1, b1 = max(a, 1), max(b, 1)  # en décibels 0 % n'existe pas : plancher à 1 % (−40 dB)
    v += s["courbe"] * (a1 * (b1 / a1) ** x - v)  # courbe 1 = montée régulière en décibels, chaque km/h s'entend autant
    if t["rpm_max"] > 0:
        v -= s["baisse_rupteur"] * borner((t["rpm"] / t["rpm_max"] - 0.85) / 0.15)
    v -= s["baisse_gaz"] * t["gaz"]
    return borner(v / 100)


class Lecteur:
    """Volume d'Apple Music dans le mélangeur Windows ; sa session audio change quand il redémarre."""

    def __init__(self):
        self.sessions, self.recherche, self.applique = [], -99.0, None

    def regler(self, v):
        if time.monotonic() - self.recherche > 3:
            self.recherche = time.monotonic()
            try:
                noms = popup.noms_processus()
                self.sessions = [s.SimpleAudioVolume for s in AudioUtilities.GetAllSessions()
                                 if noms.get(s.ProcessId) in APPS]
            except (COMError, OSError):
                self.sessions = []
            self.applique = None
        if self.sessions and (self.applique is None or abs(v - self.applique) >= 0.005):
            try:
                for s in self.sessions:
                    s.SetMasterVolume(v, None)
                self.applique = v
            except COMError:
                self.sessions = []
        return bool(self.sessions)


def ouvrir(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        return None, f"Le port {port} est déjà utilisé par un autre programme"
    sock.settimeout(0.05)
    return sock, None


reglages, etat = charger(), {}
arret, fini = threading.Event(), threading.Event()


def boucle():
    global etat
    lecteur = Lecteur()
    sock = port = erreur = telem = None
    essai = recu = 0.0
    volume = reglages["vol_menu"] / 100
    avant = time.monotonic()
    while not arret.is_set():
        s = reglages
        if s["port"] != port or (sock is None and time.monotonic() - essai > 2):
            if sock:
                sock.close()
            port, essai = s["port"], time.monotonic()
            sock, erreur = ouvrir(port)
        if sock:
            try:
                t = lire_paquet(sock.recv(2048))
                if t:
                    telem, recu = t, time.monotonic()
            except TimeoutError:
                pass
        else:
            arret.wait(0.05)
        maintenant = time.monotonic()
        dt, avant = maintenant - avant, maintenant
        actif = telem if maintenant - recu < SILENCE else None
        cible = volume_cible(actif, s)
        volume += (cible - volume) * (1 - math.exp(-dt / s["lissage"]))
        trouve = lecteur.regler(volume)
        t = actif or {**lire_paquet(bytes(TAILLE_PAQUET)), "rapport": None}
        etat = {**t, "recoit": actif is not None, "volume": round(volume * 100, 1),
                "cible": round(cible * 100, 1), "lecteur": trouve, "erreur": erreur, "port": port}
    lecteur.applique = None
    lecteur.regler(reglages["vol_menu"] / 100)
    if sock:
        sock.close()


class Page(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get("Host") not in HOTES:  # bloque le DNS rebinding
            return self.send_error(403)
        if self.path == "/":
            self.envoyer(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/etat":
            self.envoyer_json(etat)
        elif self.path == "/reglages":
            self.envoyer_json(reglages)
        elif self.path == "/presets":  # le reset garde le port, réglé aussi dans le jeu
            self.envoyer_json({"defauts": {k: v for k, v in DEFAUTS.items() if k != "port"}, "presets": PRESETS,
                               "version": VERSION})
        else:
            self.send_error(404)

    def do_POST(self):
        global reglages
        # le type JSON impose une pré-vérification CORS : un autre site ne peut pas poster ici
        if (self.headers.get("Host") not in HOTES or self.path not in ("/reglages", "/quitter")
                or self.headers.get("Content-Type") != "application/json"):
            return self.send_error(403)
        if self.path == "/quitter":  # sans console, c'est la seule façon d'arrêter proprement
            self.envoyer_json({"ok": True})
            return arret.set()
        try:
            recu = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4096)))
            if not isinstance(recu, dict):
                raise ValueError("format invalide")
            nouveaux = valider({**reglages, **recu})
        except (ValueError, TypeError) as e:
            return self.envoyer_json({"erreur": str(e)}, 400)
        reglages = nouveaux
        FICHIER_REGLAGES.write_text(json.dumps(reglages, indent=2), encoding="utf-8")
        self.envoyer_json(reglages)

    def envoyer_json(self, obj, code=200):
        self.envoyer(json.dumps(obj).encode(), "application/json", code)

    def envoyer(self, corps, type_contenu, code=200):
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *args):
        pass


def creer_icone():
    """Icône près de l'horloge, présente tant que l'appli tourne : clic = Ouvrir, clic droit = Ouvrir / Quitter."""
    menu = pystray.Menu(pystray.MenuItem("Ouvrir", lambda: webbrowser.open(ADRESSE), default=True),
                        pystray.MenuItem("Quitter", arret.set))
    return pystray.Icon("AppleMusicLink", Image.open(ICI / "icone.png"), f"AppleMusicLink {VERSION} : en marche", menu)


@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
def fermeture(_evenement):
    """Ctrl+C ou fenêtre fermée : on laisse la boucle remettre Apple Music au volume hors conduite."""
    arret.set()
    fini.wait(3)  # Windows tue la console environ 5 s après la fermeture
    return True


if __name__ == "__main__":
    ThreadingHTTPServer.allow_reuse_address = False  # sous Windows, SO_REUSEADDR laisse une 2e instance partager le port
    try:
        serveur = ThreadingHTTPServer(("127.0.0.1", PORT_WEB), Page)
    except OSError:
        webbrowser.open(ADRESSE)
        raise SystemExit("Déjà lancé : interface ouverte dans le navigateur.")
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    threading.Thread(target=popup.lancer, args=(lambda: reglages["popup"],), daemon=True).start()
    icone = creer_icone()
    fil_icone = threading.Thread(target=icone.run, daemon=True)
    fil_icone.start()
    ctypes.windll.kernel32.SetConsoleCtrlHandler(fermeture, True)
    print(f"Interface : {ADRESSE}")
    print(f"Dans FH6 : Data Out = Activé, IP 127.0.0.1, port {reglages['port']}")
    print("Pour arrêter : bouton Quitter de l'interface ou de l'icône près de l'horloge.")
    webbrowser.open(ADRESSE)
    try:
        boucle()
    finally:
        icone.stop()
        fil_icone.join(2)  # laisse l'icône se retirer, sinon une icône fantôme reste près de l'horloge
        fini.set()
