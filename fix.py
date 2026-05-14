#!/usr/bin/env python3
"""
fix_snr_symmetry.py — symétrise le canal AWGN et l'affichage SNR.

Avant :
  --snr-db  500  → "Canal AWGN désactivé (SNR ≥ 300 dB)", SNR=∞ dans le banner
  --snr-db -500  → "Canal AWGN : σ² = X", SNR=-500.0 dB littéral

Après :
  --snr-db  500  → "Canal AWGN désactivé (signal pur)",    SNR=+∞
  --snr-db -500  → "Canal AWGN saturé (signal mort)",      SNR=−∞

Idempotent : peut être relancé sans casser.

Usage :  python3 fix_snr_symmetry.py [chemin/vers/pile_trace.py]
"""

import shutil
import subprocess
import sys
from pathlib import Path

EDITS = [
    # ─── EDIT 1 : awgn_channel symétrique ───────────────────────────────────
    (
        "1. awgn_channel : ajouter seuil bas -300 dB symétrique",
        '''def awgn_channel(signal: np.ndarray, snr_db: float,
                  signal_power: float = None, seed: int = 42) -> tuple:
    """AWGN sur signal complexe. Retourne (signal_noisy, noise_var)."""
    if snr_db >= 300:  # SNR ~ infini
        return signal.copy(), 0.0
    if signal_power is None:
        signal_power = np.mean(np.abs(signal) ** 2)
    snr_lin = 10 ** (snr_db / 10)
    noise_var = signal_power / snr_lin
    rng = np.random.default_rng(seed)
    if np.iscomplexobj(signal):
        n = (rng.standard_normal(len(signal)) +
             1j * rng.standard_normal(len(signal))) * np.sqrt(noise_var / 2)
    else:
        n = rng.standard_normal(len(signal)) * np.sqrt(noise_var)
    return signal + n, noise_var''',
        '''def awgn_channel(signal: np.ndarray, snr_db: float,
                  signal_power: float = None, seed: int = 42) -> tuple:
    """AWGN sur signal complexe. Retourne (signal_noisy, noise_var).

    Régimes asymptotiques symétriques :
      snr_db >= +300 → ∞, retourne signal sans bruit
      snr_db <= -300 → -∞, retourne bruit pur (signal noyé)
    """
    if snr_db >= 300:  # SNR ~ +∞ : signal pur
        return signal.copy(), 0.0
    if signal_power is None:
        signal_power = np.mean(np.abs(signal) ** 2)
    if snr_db <= -300:  # SNR ~ -∞ : signal mort, bruit pur
        rng = np.random.default_rng(seed)
        huge = signal_power * 1e30
        if np.iscomplexobj(signal):
            n = (rng.standard_normal(len(signal)) +
                 1j * rng.standard_normal(len(signal))) * np.sqrt(huge / 2)
        else:
            n = rng.standard_normal(len(signal)) * np.sqrt(huge)
        return n, huge   # le signal n'est PAS dans la sortie
    snr_lin = 10 ** (snr_db / 10)
    noise_var = signal_power / snr_lin
    rng = np.random.default_rng(seed)
    if np.iscomplexobj(signal):
        n = (rng.standard_normal(len(signal)) +
             1j * rng.standard_normal(len(signal))) * np.sqrt(noise_var / 2)
    else:
        n = rng.standard_normal(len(signal)) * np.sqrt(noise_var)
    return signal + n, noise_var''',
    ),

    # ─── EDIT 2 : banner L13 — affichage SNR symétrique ─────────────────────
    (
        "2. Banner L13 : affichage SNR symétrique ±∞",
        '''    banner(f'NIVEAU 13 — Décap RX indépendante (SNR={snr_db if snr_db<300 else "∞"} dB, '
           f'demap={"soft" if use_soft_demap else "hard"})')''',
        '''    if snr_db >= 300:
        _snr_disp = "+∞"
    elif snr_db <= -300:
        _snr_disp = "−∞"
    else:
        _snr_disp = f"{snr_db:.1f}"
    banner(f'NIVEAU 13 — Décap RX indépendante (SNR={_snr_disp} dB, '
           f'demap={"soft" if use_soft_demap else "hard"})')''',
    ),

    # ─── EDIT 3 : message canal symétrique ──────────────────────────────────
    (
        "3. Affichage canal AWGN : message symétrique haut/bas",
        '''    if snr_db < 300:
        print(f'  Canal AWGN : σ² = {noise_var:.6f}')
    else:
        print('  Canal AWGN désactivé (SNR ≥ 300 dB)')''',
        '''    if snr_db >= 300:
        print('  Canal AWGN désactivé (SNR ≥ +300 dB, signal pur)')
    elif snr_db <= -300:
        print('  Canal AWGN saturé (SNR ≤ −300 dB, signal mort dans le bruit)')
    else:
        print(f'  Canal AWGN : σ² = {noise_var:.6f}')''',
    ),
]


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "pile_trace.py")
    if not path.exists():
        sys.exit(f"❌ {path} introuvable")

    src = path.read_text(encoding="utf-8")
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    print(f"💾 backup → {backup}")

    new_src = src
    n_applied = 0
    n_skipped = 0

    for label, old, new in EDITS:
        if old in new_src:
            new_src = new_src.replace(old, new, 1)
            print(f"  ✅ {label}")
            n_applied += 1
        elif new in new_src:
            print(f"  ⏭️  {label}  (déjà appliqué)")
            n_skipped += 1
        else:
            print(f"  ❌ {label} : bloc d'origine introuvable")
            print(f"     Le code a peut-être été modifié à la main entre temps.")
            print(f"     Backup à {backup}, à toi de voir.")
            sys.exit(1)

    path.write_text(new_src, encoding="utf-8")
    print(f"\n✅ {n_applied} edit(s) appliqué(s), {n_skipped} déjà en place.")
    print(f"📝 fichier modifié : {path}\n")

    # ─── Tests rapides ──────────────────────────────────────────────────────
    print("─" * 60)
    print("Tests :")
    print("─" * 60)
    for snr in ("500", "-500"):
        cmd = ["python3", str(path), "pile_values.csv", "4+6", "--snr-db", snr]
        print(f"\n$ {' '.join(cmd)}  | grep -E 'SNR|AWGN'")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            for line in result.stdout.splitlines():
                if any(k in line for k in ("SNR", "AWGN", "Friis", "Override", "Chaînage")):
                    print(f"  {line}")
        except FileNotFoundError:
            print("  (pile_values.csv pas dans le cwd — saute le test)")
            break
        except subprocess.TimeoutExpired:
            print("  ⏱️  timeout")


if __name__ == "__main__":
    main()
