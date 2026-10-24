"""Pop-up « en cours » par-dessus le jeu : titre, artiste et jaquette lus dans les contrôles multimédias de Windows."""
import asyncio
import ctypes
import io
import queue
import threading
import time
import tkinter as tk
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

SOURCE = "applemusic"  # identifiant Windows d'Apple Music : AppleInc.AppleMusicWin_…!App
JEU = "forzahorizon6.exe"
DUREE = 6.0
POLICES = "C:/Windows/Fonts/"

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
user32.GetParent.restype = user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [ctypes.c_uint]
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
GWL_EXSTYLE = -20
WS_EX = 0x80000 | 0x20 | 0x8000000 | 0x80  # calque, transparente aux clics, jamais activée, hors barre des tâches
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
LWA_ALPHA = 0x2
OPAQUE = 242


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def noms_processus():
    """{pid: nom de l'exécutable} lu dans la liste système : aucun processus n'est ouvert, le jeu compris (anti-triche)."""
    cliche = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if cliche in (None, wintypes.HANDLE(-1).value):
        return {}
    e, noms = PROCESSENTRY32W(dwSize=ctypes.sizeof(PROCESSENTRY32W)), {}
    try:
        ok = kernel32.Process32FirstW(cliche, ctypes.byref(e))
        while ok:
            noms[e.th32ProcessID] = e.szExeFile.lower()
            ok = kernel32.Process32NextW(cliche, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(cliche)
    return noms


def premier_plan():
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return noms_processus().get(pid.value, "")


def police(nom, taille):
    try:
        return ImageFont.truetype(POLICES + nom, taille)
    except OSError:
        return ImageFont.load_default(taille)


def couper(d, texte, f, largeur):
    if d.textlength(texte, font=f) <= largeur:
        return texte
    while texte and d.textlength(texte + "…", font=f) > largeur:
        texte = texte[:-1]
    return texte.rstrip() + "…"


def carte(titre, artiste, album, jaquette, e=1.0):
    """Image de la carte ; e = échelle de l'écran (1 = 96 ppp)."""
    px = lambda v: round(v * e)
    L, H, bande, cote, marge = px(460), px(112), px(6), px(88), px(12)
    img = Image.new("RGB", (L, H), (17, 17, 26))
    d = ImageDraw.Draw(img)
    for y in range(H):  # bande dégradée cyan → rose, comme l'interface
        k = y / max(H - 1, 1)
        d.line([(0, y), (bande - 1, y)], fill=(round(42 + 213 * k), round(212 - 167 * k), round(255 - 120 * k)))
    try:
        image = ImageOps.fit(Image.open(io.BytesIO(jaquette)).convert("RGB"), (cote, cote), Image.LANCZOS)
    except (OSError, ValueError):  # pas de jaquette ou format illisible
        image = Image.new("RGB", (cote, cote), (40, 40, 56))
    img.paste(image, (bande + marge, (H - cote) // 2))
    x = bande + marge * 2 + cote
    place = L - x - marge
    lignes = [("EN COURS · APPLE MUSIC", "seguisb.ttf", 11, 14, (255, 45, 135)),
              (titre, "segoeuib.ttf", 19, 31, (243, 242, 248)),
              (artiste, "segoeui.ttf", 14, 59, (201, 199, 217)),
              (album, "segoeui.ttf", 12, 81, (141, 139, 163))]
    for texte, nom, taille, y, couleur in lignes:
        if texte:
            f = police(nom, px(taille))
            d.text((x, px(y)), couper(d, texte, f, place), font=f, fill=couleur)
    d.rectangle([0, 0, L - 1, H - 1], outline=(46, 46, 64))
    return img


class Popup:
    """Fenêtre toujours présente mais invisible et hors écran ; elle ne prend jamais le focus du jeu."""

    def __init__(self, actif):
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # sinon Windows étire la carte et le texte devient flou
        self.actif, self.file, self.fin, self.alpha = actif, queue.Queue(), 0.0, 0
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry("1x1+-32000+-32000")
        self.etiquette = tk.Label(self.root, bd=0)
        self.etiquette.pack()
        self.root.update()
        self.hwnd = user32.GetParent(self.root.winfo_id())
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE) | WS_EX)
        user32.SetLayeredWindowAttributes(self.hwnd, 0, 0, LWA_ALPHA)
        self.echelle = self.root.winfo_fpixels("1i") / 96
        self.root.after(200, self.tic)

    def montrer(self, titre, artiste, album, jaquette):
        img = carte(titre, artiste, album, jaquette, self.echelle)
        self.photo = ImageTk.PhotoImage(img)
        self.etiquette.configure(image=self.photo)
        marge = round(32 * self.echelle)
        self.root.geometry(f"{img.width}x{img.height}+{marge}+{marge}")  # en haut à gauche, coin libre du HUD de FH6
        self.root.update_idletasks()
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        self.fin = time.monotonic() + DUREE

    def tic(self):
        while not self.file.empty():
            morceau = self.file.get()
            if self.actif() and premier_plan() == JEU:
                self.montrer(*morceau)
        cible = OPAQUE if time.monotonic() < self.fin else 0
        if self.alpha != cible:
            self.alpha = min(self.alpha + 40, cible) if cible > self.alpha else max(self.alpha - 20, cible)
            user32.SetLayeredWindowAttributes(self.hwnd, 0, self.alpha, LWA_ALPHA)
            if self.alpha == 0:
                self.root.geometry("+-32000+-32000")  # rangée hors écran : plus rien au-dessus du jeu
        self.root.after(16 if self.alpha != cible else 200, self.tic)


async def surveiller(file):
    # winrt s'initialise dans le fil qui l'importe ; le fil principal appartient déjà à comtypes
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Gestion
    from winrt.windows.storage.streams import Buffer, InputStreamOptions

    gestion = await Gestion.request_async()
    dernier = None
    while True:
        try:
            session = next((s for s in gestion.get_sessions() if SOURCE in s.source_app_user_model_id.lower()), None)
            p = session and await session.try_get_media_properties_async()
            if p and p.title and (p.title, p.artist) != dernier:
                dernier = (p.title, p.artist)
                artiste, album = p.artist, p.album_title
                if not album and " — " in artiste:  # Apple Music range « artiste — album » dans le champ artiste
                    artiste, album = artiste.split(" — ", 1)
                jaquette = b""
                if p.thumbnail:
                    flux = await p.thumbnail.open_read_async()
                    tampon = Buffer(flux.size)
                    await flux.read_async(tampon, flux.size, InputStreamOptions.READ_AHEAD)
                    jaquette = bytes(tampon)
                file.put((p.title, artiste, album, jaquette))
        except OSError:  # session fermée entre deux lectures
            pass
        await asyncio.sleep(1)


def lancer(actif):
    """Fil du pop-up ; une panne ici ne doit pas arrêter le réglage du volume."""
    try:
        popup = Popup(actif)
        threading.Thread(target=asyncio.run, args=(surveiller(popup.file),), daemon=True).start()
        popup.root.mainloop()
    except Exception as e:
        print(f"Pop-up désactivé : {e}")
