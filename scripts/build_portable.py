"""Construit une version PORTABLE d'A.C.Lib Viewer (dossier copiable + zip).

- PyInstaller en mode onedir (recommandé pour QtWebEngine).
- Icône ACL générée à la volée.
- Données de démo pré-chargées dans dist/AClibViewer/data (8 volumes de la DA).
- Produit dist/AClibViewer/  +  dist/AClibViewer_portable.zip

Lancement Windows :  .venv\\Scripts\\python.exe scripts\\build_portable.py
Lancement macOS   :  .venv/bin/python scripts/build_portable.py
Option            :  --manager pour aussi construire A.C.Lib Manager.

IMPORTANT : PyInstaller NE cross-compile PAS. La version macOS (.app) doit être
construite SUR un Mac (ou un runner CI macOS), pas depuis Windows. Le script
s'adapte à l'OS courant (icône .icns, binaire FBX2glTF sans .exe, bundle .app).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PY = sys.executable  # python du venv qui lance ce script

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")


def exe_suffix() -> str:
    """Suffixe du livrable selon l'OS : .exe (Win), .app (Mac), '' (Linux)."""
    if IS_WIN:
        return ".exe"
    if IS_MAC:
        return ".app"
    return ""


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installation de PyInstaller…")
        subprocess.run([PY, "-m", "pip", "install", "pyinstaller"], check=True)


def make_icon() -> Path | None:
    """Icône ACL (carré blanc, texte noir). .ico sous Windows, .icns sous macOS.

    Renvoie None si le format n'est pas supporté (build sans icône, non bloquant).
    """
    from PIL import Image, ImageDraw, ImageFont

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=48, fill=(245, 245, 242, 255))
    try:
        font = ImageFont.truetype("arialbd.ttf", 96)
    except OSError:
        font = ImageFont.load_default()
    d.text((size // 2, size // 2), "ACL", anchor="mm", fill=(11, 12, 14, 255), font=font)

    out = ROOT / "aclib" / "ui" / ("aclib.icns" if IS_MAC else "aclib.ico")
    try:
        if IS_MAC:
            img.save(out, format="ICNS")
        else:
            img.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except (OSError, ValueError) as exc:  # format ICNS indispo selon Pillow
        print(f"(icône ignorée : {exc})")
        return None
    return out


def build_app(entry: str, name: str, icon: Path | None) -> Path:
    # dossier web COMPLET (viewer3d.html + vendor/three vendorisé = 3D offline)
    web_dir = ROOT / "aclib" / "viewer" / "web"
    args = [
        PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", name,
        "--add-data", f"{web_dir}{os.pathsep}aclib/viewer/web",
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    if icon is not None:
        args += ["--icon", str(icon)]
    # worker c4dpy embarqué (export C4D->FBX/OBJ) ; résolu via sys._MEIPASS/scripts
    worker = ROOT / "scripts" / "c4d_worker.py"
    if worker.exists():
        args += ["--add-data", f"{worker}{os.pathsep}scripts"]
    # convertisseur FBX bundlé s'il est présent (nom selon l'OS)
    fbx_name = "FBX2glTF.exe" if IS_WIN else "FBX2glTF"
    fbx2gltf = ROOT / "tools" / fbx_name
    if fbx2gltf.exists():
        args += ["--add-binary", f"{fbx2gltf}{os.pathsep}tools"]
    args.append(str(ROOT / entry))

    print(f"\n=== PyInstaller : {name} ===")
    subprocess.run(args, check=True, cwd=ROOT)
    return DIST / name


def seed_demo(app_dir: Path) -> None:
    data = app_dir / "data"
    env = dict(os.environ, ACLIB_DATA_DIR=str(data))
    print(f"\n=== Données de démo -> {data} ===")
    subprocess.run([PY, str(ROOT / "scripts" / "screenshot_test.py"), "--seed-only"],
                   check=True, cwd=ROOT, env=env)


def write_readme(app_dir: Path, exe: str, name: str) -> None:
    is_manager = "Manager" in name
    title = "A.C.Lib Manager" if is_manager else "A.C.Lib Viewer"
    if is_manager:
        notes = (
            "Notes :\n"
            " - Import : glissez des fichiers/dossiers 3D (.c4d .fbx .obj .step) dans\n"
            "   la fenêtre, ou utilisez 'Indexer un dossier…'.\n"
            " - Conversion C4D/STEP -> aperçu : nécessite Cinema 4D (c4dpy) /\n"
            "   pythonocc installés. Sans eux, FBX/OBJ s'indexent quand même.\n"
            " - Base + aperçus dans le dossier 'data' à côté de l'exe.\n"
        )
    else:
        notes = (
            "Notes :\n"
            " - Aperçu 3D (glTF) : fonctionne hors-ligne (three.js embarqué).\n"
            " - 'Ouvrir le fichier source' suppose le NAS monté ; sinon avertissement.\n"
        )
    (app_dir / "LISEZ-MOI.txt").write_text(
        f"{title} — version portable\n"
        f"{'=' * (len(title) + 18)}\n\n"
        f"Lancer : double-cliquer {exe}\n\n"
        "Au 1er lancement, la bibliothèque est VIDE. Utilisez le bouton\n"
        "« Bibliothèque » pour choisir le dossier partagé (idéalement sur le NAS)\n"
        "où le Manager écrit la base + les aperçus. Pointez Manager ET Viewer\n"
        "sur le MÊME dossier pour qu'ils partagent les mêmes volumes.\n"
        "Tout est portable : copiez le dossier entier où vous voulez.\n\n"
        + notes,
        encoding="utf-8",
    )


def main() -> int:
    ensure_pyinstaller()
    icon = make_icon()

    # Sélection des cibles : --manager et/ou --viewer ; défaut = viewer.
    targets = []
    if "--manager" in sys.argv:
        targets.append(("run_manager.py", "AClibManager"))
    if "--viewer" in sys.argv:
        targets.append(("run_viewer.py", "AClibViewer"))
    if not targets:
        targets = [("run_viewer.py", "AClibViewer")]

    demo = "--demo" in sys.argv  # données d'exemple seulement si demandé
    suffix = exe_suffix()
    for entry, name in targets:
        app_dir = build_app(entry, name, icon)
        if demo:
            seed_demo(app_dir)
        write_readme(app_dir, f"{name}{suffix}", name)
        zip_path = DIST / f"{name}_portable.zip"
        mac_app = DIST / f"{name}.app"
        if IS_MAC and mac_app.exists():
            # IMPORTANT : un .app contient des symlinks + bits exécutables.
            # shutil/zipfile les PERD -> bundle cassé (Terminal/crash au lancement).
            # ditto préserve la structure du bundle.
            print(f"=== ditto -> {zip_path} ===")
            if zip_path.exists():
                zip_path.unlink()
            subprocess.run(
                ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                 str(mac_app), str(zip_path)],
                check=True,
            )
            print(f"OK : {mac_app}")
        else:
            print(f"=== Zip -> {zip_path} ===")
            shutil.make_archive(str(DIST / f'{name}_portable'), "zip", str(app_dir))
            print(f"OK : {app_dir}")

    print("\nBUILD PORTABLE TERMINÉ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
