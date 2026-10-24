# AppleMusicLink

Le volume d'Apple Music suit ta conduite dans **Forza Horizon 6** : la musique monte quand tu prends de la vitesse et redescend quand tu ralentis. À chaque nouveau morceau, une carte avec le titre et la jaquette s'affiche quelques secondes en haut à gauche de l'écran.

## Installation

1. Télécharge **AppleMusicLink.exe** dans les [Releases](https://github.com/MrReLaX1/AppleMusicLink/releases).
2. Lance-le. Au premier lancement, il installe tout seul, dans ton compte Windows et sans droits administrateur :
   - **Python 3.14**, s'il n'est pas déjà installé (installeur officiel python.org, vérifié par son empreinte avant d'être lancé) ;
   - les composants nécessaires ;
   - l'appli, dans `%LOCALAPPDATA%\AppleMusicLink`.
3. L'interface s'ouvre dans ton navigateur : <http://127.0.0.1:8766>.

> Windows peut afficher « Windows a protégé votre ordinateur », car l'exe n'est pas signé. Clique sur **Informations complémentaires**, puis sur **Exécuter quand même**.

## Dans Forza Horizon 6

Paramètres → **HUD et gameplay** :

| Réglage | Valeur |
|---|---|
| Data Out | Activé |
| Data Out IP Address | `127.0.0.1` |
| Data Out IP Port | `5555` |

Pour voir la carte du morceau par-dessus le jeu, mets FH6 en **plein écran fenêtré** (sans bordure).

## Utilisation

- Mode par défaut (« Équilibré ») : 20 % à l'arrêt, 100 % à 190 km/h, courbe « Marquée » (la montée s'entend de façon régulière), 20 % dans les menus et en pause.
- Tous les réglages se changent dans l'interface et sont gardés d'un lancement à l'autre.
- Tant que l'appli tourne, son **icône** est près de l'horloge (dans la flèche ^ si Windows la range). Un clic ouvre l'interface ; un clic droit donne **Ouvrir** et **Quitter**.
- Fermer la page du navigateur n'arrête pas l'appli : elle doit tourner pendant que tu joues. Pour l'arrêter, utilise **Quitter**, depuis l'icône ou en bas de l'interface. Apple Music revient alors au volume « hors conduite ».

## Mises à jour automatiques

À chaque lancement, AppleMusicLink.exe compare la version installée avec `app/VERSION` sur la branche `main`. Si GitHub a une version plus récente, il la télécharge et l'installe. Tes réglages sont conservés. Sans internet, la version déjà installée se lance normalement.

## Anti-triche

AppleMusicLink ne touche jamais au jeu :

- il **ne s'injecte pas** dans FH6 (aucune DLL, aucun fichier modifié dans le dossier du jeu) ;
- il **n'ouvre jamais le processus du jeu** et ne lit pas sa mémoire. Les noms des programmes viennent de la liste système de Windows ;
- il ne simule aucune touche ni aucune manette.

Il utilise uniquement :

- le **Data Out** officiel de Forza : les données de vitesse que le jeu envoie de lui-même en UDP, comme pour les simulateurs de mouvement ou SimHub ;
- le **mélangeur de volume de Windows**, pour Apple Music seulement ;
- une **fenêtre séparée**, transparente aux clics et qui ne prend jamais le focus, pour la carte du morceau.

## Désinstallation

Supprime le dossier `%LOCALAPPDATA%\AppleMusicLink`. Si Python a été installé par AppleMusicLink, tu peux le retirer depuis Paramètres → Applications.

## Développement

- `app/` : l'appli (Python), installée telle quelle chez les utilisateurs.
- `launcher/` : le lanceur en C#. `build.bat` le compile avec le compilateur fourni par Windows, rien à installer.
- Tests : `py -3 app/test_fh6_volume.py`.
- **Publier une version** : augmente le numéro dans `app/VERSION`, puis pousse sur `main`. Les utilisateurs l'auront à leur prochain lancement.

Par MrReLaX.
