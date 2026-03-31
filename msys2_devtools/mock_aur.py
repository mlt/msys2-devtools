# https://wiki.archlinux.org/title/Aurweb_RPC_interface
from importlib.resources import path
from itertools import chain

from flask import Flask, request, jsonify
import logging
import re
import json
import subprocess
import os, sys
from os.path import dirname, realpath, join
from pathlib import Path
from functools import lru_cache

PACKAGES_DIR = os.environ.get("MINGW_PACKAGES", 'C:/dev/MINGW-packages')
BASH = Path(sys.executable).parents[2] / 'usr' / 'bin' / 'bash.exe'
PKGBUILD2JSON = join(dirname(__file__), "pkgbuild2json.sh")

app = Flask(__name__)
app.json.compact = True
app.logger.setLevel(logging.INFO)

@lru_cache(maxsize=128)
def _lookup_pkgbuild(pkgnames):
    return list(chain.from_iterable(map(_iter_lookup_pkgbuild, pkgnames)))

def _iter_lookup_pkgbuild(pkgname: str):
    match = re.search(r'(?P<prefix>mingw-w64-)(?P<crt>.+-)?(x86_64)-(?P<pkg>.+)', pkgname)
    if not match:
        app.logger.debug(f"Base environment package requested: {pkgname}")
        return
    pkgname = match.group('prefix') + match.group('pkg')
    prefixes = ['pkgname', 'pkgver', 'pkgbase', "depends", "makedepends"]
    pkgbuild_path = join(PACKAGES_DIR, pkgname, 'PKGBUILD')
    app.logger.info(f"*** pkgbuild_path: {pkgbuild_path}")
    try:
        out = subprocess.check_output(
            [BASH, PKGBUILD2JSON, pkgbuild_path] + prefixes,
            text=True, encoding="utf-8")
        data = json.loads(out)
        if not data:
            app.logger.warning(f"No output from pkgbuild2json for {pkgname}")
            return
        names = data.get('pkgname', [])
        if isinstance(names, str):
            names = [names]

        base = {
            'PackageBase': data['pkgbase'],
            'Version': data['pkgver'],
            'Depends': data.get('depends', []),
            'MakeDepends': data.get('makedepends', []),
        }

        for name in names:
            yield {'Name': name, **base}

    except (OSError, subprocess.CalledProcessError, KeyError) as e:
        app.logger.error(f"{type(e).__name__}: {e} while processing pkgbuild: {pkgname}")
        return

@app.route('/rpc/v5/info', methods=['POST'])
def rpc_info():
    data = request.form.getlist('arg[]')

    log_data = {
        "method": request.method,
        "query_args": request.args.to_dict(),
        "headers": dict(request.headers),
    }
    log_data["body"] = data
    app.logger.info(f"Request received: {log_data}")

    res = _lookup_pkgbuild(tuple(data))
    app.logger.info(f"*** Fetched data: {res}")

    return jsonify({
        "version": "5",
        # "type": "multiinfo", #search/info",
        "resultCount": len(res),
        "results": res,
        # "error": None
    })

if __name__ == '__main__':
    app.run(debug=True)
