#!/usr/bin/env bash
# install-grgsm.sh — gr-gsm + modules Python sur Ubuntu/Debian (GNU Radio 3.10+)
# Fork bkerler, le mainline de Krysik n'est plus maintenu pour GR 3.10+

set -euo pipefail

GRGSM_REPO="${GRGSM_REPO:-https://github.com/bkerler/gr-gsm.git}"
SRC_DIR="${SRC_DIR:-$HOME/src}"
JOBS="$(nproc)"

# ─── 1. Dépendances système ──────────────────────────────────────────────
echo "[*] Dépendances système"
sudo apt-get update
sudo apt-get install -y \
    git cmake build-essential pkg-config \
    gnuradio gnuradio-dev gr-osmosdr \
    libosmocore-dev liborc-0.4-dev \
    libboost-all-dev libcppunit-dev \
    swig python3-dev python3-numpy python3-scipy \
    python3-matplotlib python3-setuptools python3-pip \
    python3-venv python3-wheel \
    wireshark tshark \
    doxygen

# Modules Python via apt quand dispo (intégration propre avec le Python système
# utilisé par GNU Radio — évite les conflits PEP 668)
echo "[*] Modules Python via apt"
sudo apt-get install -y \
    python3-scapy \
    python3-pyshark \
    python3-construct \
    python3-bitstring \
    python3-crypto \
    python3-cryptography \
    python3-serial \
    python3-requests \
    python3-yaml \
    python3-tqdm \
    python3-pyqt5 || true   # certains paquets peuvent manquer selon la version

# ─── 2. Modules Python via pip (ce que apt ne fournit pas) ───────────────
echo "[*] Modules Python via pip"

# Ne PAS upgrader pip/setuptools/wheel : gérés par apt sur Python 3.11+,
# pip ne peut pas les désinstaller (pas de RECORD) et ça plante.

PIP_ARGS=(--break-system-packages --ignore-installed)

sudo python3 -m pip install "${PIP_ARGS[@]}" \
    pycryptodome \
    pyrtlsdr \
    libscrc \
    smpplib \
    pycrate \
    pysctp

# Optionnels — pas sur PyPI selon la version, isolés pour ne pas planter le lot
for opt in pyhackrf pyrx pylab-sdk; do
    sudo python3 -m pip install "${PIP_ARGS[@]}" "$opt" || \
        echo "  [!] $opt indispo, skip"
done
# ─── 3. Clone + build gr-gsm ─────────────────────────────────────────────
mkdir -p "$SRC_DIR"
cd "$SRC_DIR"

if [ -d gr-gsm ]; then
    echo "[*] gr-gsm déjà cloné, pull"
    cd gr-gsm && git pull && cd ..
else
    echo "[*] Clone $GRGSM_REPO"
    git clone "$GRGSM_REPO"
fi

cd gr-gsm
rm -rf build
mkdir build && cd build

echo "[*] CMake"
cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local

echo "[*] Build (-j$JOBS)"
make -j"$JOBS"

echo "[*] Install"
sudo make install
sudo ldconfig

# ─── 4. PYTHONPATH si module non importable ──────────────────────────────
if ! python3 -c "import grgsm" 2>/dev/null; then
    echo "[!] Module grgsm non importable, recherche du chemin"
    GR_PY="$(find /usr/local/lib -maxdepth 4 -name 'grgsm' -type d 2>/dev/null | head -1)"
    if [ -n "$GR_PY" ]; then
        GR_PY_PARENT="$(dirname "$GR_PY")"
        echo "[*] Trouvé dans $GR_PY_PARENT, ajout PYTHONPATH au .bashrc"
        if ! grep -q "$GR_PY_PARENT" "$HOME/.bashrc" 2>/dev/null; then
            echo "export PYTHONPATH=\"$GR_PY_PARENT:\$PYTHONPATH\"" >> "$HOME/.bashrc"
        fi
        export PYTHONPATH="$GR_PY_PARENT:${PYTHONPATH:-}"
    fi
fi

# ─── 5. Vérifications ────────────────────────────────────────────────────
echo "[*] Vérification gr-gsm"
python3 -c "import grgsm; print('  grgsm OK')" || echo "  [!] import grgsm KO"

echo "[*] Vérification modules Python"
for mod in scapy pyshark pycryptodome Crypto construct bitstring pycrate; do
    python3 -c "import $mod" 2>/dev/null && echo "  $mod OK" || echo "  $mod KO"
done

echo "[*] Binaires gr-gsm"
for bin in grgsm_livemon grgsm_livemon_headless grgsm_capture grgsm_decode grgsm_scanner; do
    command -v "$bin" >/dev/null && echo "  $bin OK" || echo "  $bin manquant"
done

echo "[✓] Terminé — relance ton shell ou: source ~/.bashrc"
