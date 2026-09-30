"""Bump the add-on version, rebuild nl2_track_builder.zip and install it into Blender's user extensions.

Usage: python make_package.py [--no-bump] [--no-install] [--public]

--public leaves the game asset pack (assets/nl2_assets.json.gz) out of the zip; use it for anything you
share. The asset pack is built from your own NoLimits 2 install and must stay on your machine.
"""
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "nl2_track_builder")
ZIP = os.path.join(HERE, "nl2_track_builder.zip")
BLENDER_CFG = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")


def rewrite(path, pattern, repl):
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    new, n = re.subn(pattern, repl, text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("version pattern not found in %s" % path)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)


def bump():
    vpath = os.path.join(PKG, "version.py")
    with open(vpath, encoding="utf-8") as fh:
        cur = re.search(r'VERSION = "(\d+)\.(\d+)\.(\d+)"', fh.read())
    major, minor, patch = (int(x) for x in cur.groups())
    ver = "%d.%d.%d" % (major, minor, patch + 1)
    rewrite(vpath, r'^VERSION = "[^"]*"', 'VERSION = "%s"' % ver)
    rewrite(os.path.join(PKG, "blender_manifest.toml"), r'^version = "[^"]*"', 'version = "%s"' % ver)
    rewrite(os.path.join(PKG, "__init__.py"), r'"version": \(.*?\)', '"version": (%d, %d, %d)'
            % (major, minor, patch + 1))
    return ver


def files(public=False):
    for root, dirs, names in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in names:
            if n.endswith(".pyc") or (public and n.endswith(".json.gz")):
                continue
            yield os.path.join(root, n)


def package(public=False):
    if os.path.exists(ZIP):
        os.remove(ZIP)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files(public):
            z.write(f, os.path.relpath(f, HERE).replace(os.sep, "/"))


def install():
    done = []
    if not os.path.isdir(BLENDER_CFG):
        return done
    for ver in os.listdir(BLENDER_CFG):
        dst = os.path.join(BLENDER_CFG, ver, "extensions", "user_default", "nl2_track_builder")
        if not os.path.isdir(os.path.dirname(dst)):
            continue
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        for f in files():
            out = os.path.join(dst, os.path.relpath(f, PKG))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(f, out)
        done.append(dst)
    return done


if __name__ == "__main__":
    if "--no-bump" in sys.argv:
        with open(os.path.join(PKG, "version.py"), encoding="utf-8") as fh:
            ver = re.search(r'VERSION = "(.*)"', fh.read()).group(1)
    else:
        ver = bump()
    package("--public" in sys.argv)
    print("version", ver, "->", ZIP)
    if "--no-install" not in sys.argv:
        for d in install():
            print("installed", d)
