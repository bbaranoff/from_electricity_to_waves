#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pile_trace.py — Trace honnête de la pile LTE/NR du MOSFET à l'OLED.

Version "real libs" : plus de stubs HMAC pour la sécurité, plus de codeur jouet.

Dépendances additionnelles vs version précédente :
    pip install CryptoMobile scikit-commpy
(numpy, Pillow, pycryptodomex déjà requis)

Remplacements "simulé → vrai" :
  • MILENAGE f1-f5 (CryptoMobile.Milenage) : vraie chaîne K/RAND/SQN/OP → CK/IK/AK/RES
    → K_ASME (TS 33.401 A.2) → K_eNB (A.3) → K_UPenc (A.7) — tous via HMAC-SHA-256
    sur des dérivations 3GPP réelles, plus de string "k_asme_sim||".
  • Codeur convolutif rate-1/3 (g=[13,15,17]₈) + Viterbi (commpy) — substitut
    pédagogique au turbo 3GPP (TS 36.212 §5.1.3 : RSC×2 + QPP). Vraie lib,
    vrai treillis, vrai BCJR-like decode. Le turbo réel demande QPP custom.
  • LLR soft-demap 16-QAM (max-log-MAP, vraie formule) : démap dur ET soft.
  • Canal AWGN configurable (--snr-db). Round-trip identité à SNR=∞ (défaut).
  • Shockley OLED en L15 : I = Is·(exp(V/(n·VT)) − 1)
  • PSS (Zadoff-Chu, TS 36.211 §6.11.1) générée en illustration (cell_id_2).

Toujours hors scope (étiqueté) :
  • Turbo 3GPP avec QPP interleaver (commpy a turbo mais sans QPP natif)
  • SSS, CRS, DM-RS, PBCH, windowing OFDM
  • Vrai RF Nyquist (DAC + filtre + mixer + PA + upconv analogique)
  • Multipath, Doppler, shadowing log-normal
  • Couches ≥ PDCP : RRC, NAS, scheduler, HARQ, mesures CQI/RSRP/RSRQ

Usage :
    python3 pile_trace.py pile_values.csv 16+16
    python3 pile_trace.py pile_values.csv 4+4 --verbose
    python3 pile_trace.py pile_values.csv 999+1 --check
    python3 pile_trace.py pile_values.csv 2+2 --snr-db 15  # AWGN actif
"""

import argparse
import binascii
import csv
import hashlib
import hmac
import json
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---- Vraies libs (dépendances externes) ------------------------------------
try:
    from CryptoMobile.Milenage import Milenage, make_OPc
except ImportError:
    print("ERREUR: pip install CryptoMobile", file=sys.stderr); sys.exit(2)

try:
    from commpy.channelcoding import Trellis, conv_encode, viterbi_decode
except ImportError:
    print("ERREUR: pip install scikit-commpy", file=sys.stderr); sys.exit(2)

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ImportError:
    print("ERREUR: pip install pycryptodomex", file=sys.stderr); sys.exit(2)


# ============================================================================
# UTILITAIRES
# ============================================================================

def banner(title: str, n: int = 72) -> None:
    print('\n' + '=' * n)
    print(f'  {title}')
    print('=' * n)


def hexdump(data: bytes, prefix: str = '') -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        hex_part = f'{hex_part:<47}'
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f'{prefix}{i:04x}: {hex_part}  {ascii_part}')
    return '\n'.join(lines)


def ip_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b'\x00'
    s = sum(int.from_bytes(data[i:i + 2], 'big') for i in range(0, len(data), 2))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def crc24a(data: bytes) -> int:
    """CRC-24A LTE (TS 36.212 §5.1.1), poly 0x1864CFB."""
    poly = 0x1864CFB
    crc = 0
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= poly
    return crc & 0xFFFFFF


def mac_to_bytes(mac: str) -> bytes:
    return bytes(int(x, 16) for x in mac.split(':'))


def ip_to_bytes(ip: str) -> bytes:
    return bytes(int(x) for x in ip.split('.'))


# ----- PLMN encoding (TS 24.008 §10.5.1.3) ---------------------------------

def encode_plmn(mcc: str, mnc: str) -> bytes:
    """Encode PLMN ID en 3 octets BCD swap-nibble.
    Ex: MCC=208, MNC=01 → b'\\x02\\xf8\\x10' (MNC sur 2 digits, padding F)."""
    m1, m2, m3 = int(mcc[0]), int(mcc[1]), int(mcc[2])
    if len(mnc) == 2:
        n1, n2 = int(mnc[0]), int(mnc[1])
        n3 = 0xF
    elif len(mnc) == 3:
        n1, n2, n3 = int(mnc[0]), int(mnc[1]), int(mnc[2])
    else:
        raise ValueError(f"MNC longueur invalide: {mnc}")
    octet1 = (m2 << 4) | m1
    octet2 = (n3 << 4) | m3
    octet3 = (n2 << 4) | n1
    return bytes([octet1, octet2, octet3])


# ----- LTE KDF (TS 33.220 §B.2.0, TS 33.401 Annexe A) ----------------------

def kdf_hmac_sha256(key: bytes, fc: int, params: list) -> bytes:
    """KDF générique TS 33.220 §B.2.0. S = FC || P0 || L0 || P1 || L1 || ...
    Retourne HMAC-SHA-256(key, S) (32 octets)."""
    s = bytes([fc])
    for p in params:
        if isinstance(p, int):
            p = p.to_bytes((p.bit_length() + 7) // 8 or 1, 'big')
        s += p + len(p).to_bytes(2, 'big')
    return hmac.new(key, s, hashlib.sha256).digest()


def derive_k_asme(ck: bytes, ik: bytes, plmn_id: bytes, sqn_xor_ak: bytes) -> bytes:
    """TS 33.401 A.2 : K_ASME = HMAC-SHA-256(CK||IK, 0x10 || PLMN || L || (SQN⊕AK) || L)
    Retourne 32 octets (le keystream complet est K_ASME)."""
    assert len(plmn_id) == 3 and len(sqn_xor_ak) == 6
    return kdf_hmac_sha256(ck + ik, 0x10, [plmn_id, sqn_xor_ak])


def derive_k_enb(k_asme: bytes, nas_ul_count: int) -> bytes:
    """TS 33.401 A.3 : K_eNB = HMAC-SHA-256(K_ASME, 0x11 || NAS_UL_COUNT || L)
    NAS_UL_COUNT sur 4 octets big-endian."""
    return kdf_hmac_sha256(k_asme, 0x11, [struct.pack('>I', nas_ul_count)])


def derive_k_upenc(k_enb: bytes, eea_id: int = 1) -> bytes:
    """TS 33.401 A.7 : algorithm key derivation.
    FC=0x15, P0=algo type (0x05 = UP-enc), P1=algo identity (EEA1=1, EEA2=2).
    Sortie tronquée aux 128 LSB."""
    full = kdf_hmac_sha256(k_enb, 0x15, [bytes([0x05]), bytes([eea_id])])
    return full[16:]  # 128 LSB


def lte_aka_full_chain(K: bytes, OP: bytes, RAND: bytes, SQN: bytes,
                       AMF: bytes, plmn_id: bytes, nas_ul_count: int,
                       eea_id: int = 1) -> dict:
    """Chaîne AKA + key derivation complète, retourne tous les intermédiaires.
    
    Étapes :
      1. Milenage f1..f5  → MAC-A, RES, CK, IK, AK     [CryptoMobile]
      2. AUTN = (SQN⊕AK) || AMF || MAC-A
      3. K_ASME ← KDF(CK||IK, PLMN, SQN⊕AK)            [TS 33.401 A.2]
      4. K_eNB  ← KDF(K_ASME, NAS_UL_COUNT)            [TS 33.401 A.3]
      5. K_UPenc ← KDF(K_eNB, UP-enc, EEA_id)[128 LSB] [TS 33.401 A.7]
    """
    mil = Milenage(OP)
    mac_a = mil.f1(K, RAND, SQN, AMF)
    RES, CK, IK, AK = mil.f2345(K, RAND)
    sqn_xor_ak = bytes(a ^ b for a, b in zip(SQN, AK))
    autn = sqn_xor_ak + AMF + mac_a
    k_asme = derive_k_asme(CK, IK, plmn_id, sqn_xor_ak)
    k_enb = derive_k_enb(k_asme, nas_ul_count)
    k_upenc = derive_k_upenc(k_enb, eea_id)
    return {
        'mac_a': mac_a, 'RES': RES, 'CK': CK, 'IK': IK, 'AK': AK,
        'autn': autn, 'sqn_xor_ak': sqn_xor_ak,
        'k_asme': k_asme, 'k_enb': k_enb, 'k_upenc': k_upenc,
    }


# ----- Séquence de Gold LTE (TS 36.211 §7.2) -------------------------------

def lte_gold_sequence(cinit: int, length: int) -> np.ndarray:
    """Séquence de Gold LTE longueur-31 (TS 36.211 §7.2), Nc=1600."""
    Nc = 1600
    L = length + Nc + 31
    x1 = np.zeros(L, dtype=np.uint8)
    x2 = np.zeros(L, dtype=np.uint8)
    x1[0] = 1
    for i in range(31):
        x2[i] = (cinit >> i) & 1
    for n in range(L - 31):
        x1[n + 31] = x1[n + 3] ^ x1[n]
        x2[n + 31] = x2[n + 3] ^ x2[n + 2] ^ x2[n + 1] ^ x2[n]
    c = np.zeros(length, dtype=np.uint8)
    for n in range(length):
        c[n] = x1[n + Nc] ^ x2[n + Nc]
    return c


# ----- PSS Zadoff-Chu (TS 36.211 §6.11.1) ----------------------------------

def pss_zadoff_chu(n_id_2: int) -> np.ndarray:
    """Génère le PSS (Primary Synchronization Signal) LTE.
    Longueur 63 (62 utiles + DC), Zadoff-Chu avec u ∈ {25, 29, 34} selon n_id_2."""
    u_map = {0: 25, 1: 29, 2: 34}
    if n_id_2 not in u_map:
        raise ValueError("n_id_2 doit être 0, 1 ou 2")
    u = u_map[n_id_2]
    d = np.zeros(62, dtype=complex)
    for n in range(31):
        d[n] = np.exp(-1j * np.pi * u * n * (n + 1) / 63)
    for n in range(31, 62):
        d[n] = np.exp(-1j * np.pi * u * (n + 1) * (n + 2) / 63)
    return d


# ----- Codeur convolutif (substitut pédagogique au turbo) ------------------

# Rate 1/3, K=4 (memory=3), G=(13,15,17)₈
_CONV_TRELLIS = Trellis(np.array([3]), np.array([[0o13, 0o15, 0o17]]))
_CONV_RATE_DENOM = 3
_CONV_TAIL = 3  # memory bits flushed


def conv_encode_lte_like(tb_bits: np.ndarray) -> np.ndarray:
    """Encode TB en rate-1/3 convolutif. Retourne array binaire."""
    return conv_encode(tb_bits.astype(int), _CONV_TRELLIS).astype(np.uint8)


def conv_decode_lte_like(coded: np.ndarray, tb_bit_len: int,
                          decoding_type: str = 'hard') -> np.ndarray:
    """Viterbi decode. coded en hard bits ou LLRs (selon decoding_type).
    Retourne les premiers tb_bit_len bits (tronque le tail de Viterbi)."""
    if decoding_type == 'hard':
        decoded = viterbi_decode(coded.astype(float), _CONV_TRELLIS,
                                  tb_depth=15, decoding_type='hard')
    else:
        decoded = viterbi_decode(coded.astype(float), _CONV_TRELLIS,
                                  tb_depth=15, decoding_type='unquantized')
    return decoded[:tb_bit_len].astype(np.uint8)


# ----- 16-QAM (TS 36.211 §7.1.3) -------------------------------------------

SQRT10 = np.sqrt(10)


def qam16_map(bits: np.ndarray) -> np.ndarray:
    """Mapping Gray 3GPP normalisé √10. 4 bits → 1 symbole."""
    bits = bits.astype(np.int32)
    n_sym = len(bits) // 4
    sym = np.zeros(n_sym, dtype=complex)
    for k in range(n_sym):
        b0, b1, b2, b3 = (int(bits[4 * k + i]) for i in range(4))
        i_real = (1 - 2 * b0) * (2 - (1 - 2 * b2))
        q_imag = (1 - 2 * b1) * (2 - (1 - 2 * b3))
        sym[k] = (i_real + 1j * q_imag) / SQRT10
    return sym


def qam16_demap_hard(symbols: np.ndarray) -> np.ndarray:
    """Démap dur (4 bits par symbole). Mapping inverse de qam16_map."""
    bits = np.zeros(len(symbols) * 4, dtype=np.uint8)
    for k, s in enumerate(symbols):
        re = s.real * SQRT10
        im = s.imag * SQRT10
        bits[4 * k + 0] = 1 if re < 0 else 0          # b0 (sign I)
        bits[4 * k + 1] = 1 if im < 0 else 0          # b1 (sign Q)
        bits[4 * k + 2] = 1 if abs(re) > 2 else 0     # b2 (|I| loin)
        bits[4 * k + 3] = 1 if abs(im) > 2 else 0     # b3 (|Q| loin)
    return bits


def qam16_demap_soft(symbols: np.ndarray, noise_var: float = 1.0) -> np.ndarray:
    """Démap soft max-log-MAP : LLR par bit. Convention : LLR>0 ⇔ bit=0.
    
    Pour Gray 16-QAM normalisé √10 avec {±1, ±3} en composante :
      LLR(b0) ≈ (4·I/√10) / σ²              (sign de I)
      LLR(b1) ≈ (4·Q/√10) / σ²              (sign de Q)
      LLR(b2) ≈ (4·(2−|I|·√10)) / (√10·σ²)  (proximité de l'axe en I)
      LLR(b3) ≈ (4·(2−|Q|·√10)) / (√10·σ²)
    """
    n = len(symbols)
    llr = np.zeros(n * 4)
    inv_sigma2 = 1.0 / max(noise_var, 1e-12)
    for k, s in enumerate(symbols):
        I = s.real * SQRT10  # dé-normalisé : composantes attendues {±1, ±3}
        Q = s.imag * SQRT10
        llr[4 * k + 0] = 4 * I * inv_sigma2 / SQRT10
        llr[4 * k + 1] = 4 * Q * inv_sigma2 / SQRT10
        llr[4 * k + 2] = 4 * (2 - abs(I)) * inv_sigma2 / SQRT10
        llr[4 * k + 3] = 4 * (2 - abs(Q)) * inv_sigma2 / SQRT10
    return llr


# ----- Canal AWGN ----------------------------------------------------------

def awgn_channel(signal: np.ndarray, snr_db: float,
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
    return signal + n, noise_var


# ----- Diode Shockley + résistance série (OLED réaliste) -------------------

def shockley_iv_with_rs(V: float, Is: float = 1e-12, n_diode: float = 2.0,
                         VT: float = 0.02585, Rs: float = 1e4,
                         max_iter: int = 100, tol: float = 1e-15) -> tuple:
    """Résoud le système transcendant :
        I = Is·(exp(V_diode/(n·VT)) − 1)
        V = V_diode + I·Rs
    par bisection sur V_diode ∈ [0, V]. Retourne (I, V_diode).
    
    Sans Rs, Shockley nu explose dès que V > ~0.7 V (exp diverge).
    Avec Rs (typique 1-100 kΩ pour un sous-pixel OLED), l'auto-limitation
    par chute IR maintient I dans une plage physique."""
    if V <= 0:
        return 0.0, 0.0

    def residual(Vd):
        arg = Vd / (n_diode * VT)
        if arg > 200:  # protection overflow exp
            return float('inf')
        return Is * (np.exp(arg) - 1) - (V - Vd) / Rs

    lo, hi = 0.0, V
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        fm = residual(mid)
        if abs(fm) < tol or (hi - lo) < tol:
            break
        if fm > 0:
            hi = mid
        else:
            lo = mid
    Vd = 0.5 * (lo + hi)
    I = (V - Vd) / Rs
    return I, Vd


# ============================================================================
# CONFIG CSV
# ============================================================================

def load_csv(path: str) -> dict:
    cfg = {}
    with open(path, newline='') as f:
        for row in csv.reader(f):
            if not row or row[0].strip().startswith('#') or row[0].strip() == 'key':
                continue
            if len(row) < 2:
                continue
            k, v = row[0].strip(), row[1].strip()
            if v.startswith(('0x', '0X')):
                cfg[k] = int(v, 16)
            else:
                try:
                    cfg[k] = int(v)
                except ValueError:
                    try:
                        cfg[k] = float(v)
                    except ValueError:
                        cfg[k] = v
    # Défauts pour les nouvelles clés (test vectors TS 35.207 §4.3.1 set 1)
    cfg.setdefault('rand', '23553CBE9637A89D218AE64DAE47BF35')
    cfg.setdefault('sqn', 'FF9BB4D0B607')
    cfg.setdefault('op', 'CDC202D5123E20F62B6D676AC72CB318')
    cfg.setdefault('nas_ul_count', 0)
    cfg.setdefault('eea_id', 1)
    cfg.setdefault('oled_rs_ohm', 10e3)  # série Rs pour Shockley OLED réaliste
    return cfg


# ============================================================================
# NIVEAU 0 — Saisie clavier → registres (deux opérandes)
# ============================================================================

def L0_mosfet_eq(cfg: dict, label: str) -> dict:
    VDD = cfg['vdd_core_v']
    Vth = cfg['mosfet_vth_v']
    mu_Cox = cfg['mosfet_mu_cox_uA_V2']
    WL = cfg['mosfet_WL']
    Cload = cfg['mosfet_cload_F']
    Vgs = 3.3
    Id_sat = 0.5 * mu_Cox * WL * (Vgs - Vth) ** 2
    Ron = VDD / Id_sat
    Eswitch = 0.5 * Cload * VDD ** 2
    print(f'  ▶ MOSFET ({label}) : V_GS={Vgs} V, V_th={Vth} V')
    print(f'     I_D = ½·µCox·(W/L)·(V_GS−V_th)² = {Id_sat * 1e6:.1f} µA')
    print(f'     R_on = V/I = {Ron / 1e3:.2f} kΩ ; E_switch = ½·C·V² = {Eswitch * 1e15:.2f} fJ')
    return {'vdd': VDD, 'ron': Ron, 'id': Id_sat}


def L0_inverter_eq(cfg: dict, mosfet: dict, label: str) -> None:
    Cload = cfg['mosfet_cload_F']
    Ron_n = mosfet['ron']
    Ron_p = Ron_n * 2.5
    t_rise = 2.2 * Ron_p * Cload
    t_fall = 2.2 * Ron_n * Cload
    print(f'  ▶ Inverseur CMOS ({label}) : VDD={mosfet["vdd"]} V')
    print(f'     t_rise = {t_rise * 1e12:.2f} ps, t_fall = {t_fall * 1e12:.2f} ps')


def L0_nand_reference() -> None:
    print('\n  ── Référence : porte NAND (primitive universelle) ──')
    print('     A B │ Y=NAND(A,B)')
    print('     ────┼────────────')
    for a in (0, 1):
        for b in (0, 1):
            y = int(not (a and b))
            print(f'      {a} {b} │     {y}')
    print('     (toutes les portes — INV, AND, OR, XOR, FF — se construisent par cascade de NAND)')


def L0_keypress(cfg: dict, value: int, label: str, full_chain: bool) -> dict:
    char_repr = str(value)
    last_digit = char_repr[-1]
    ascii_code = ord(last_digit)
    n_bits = max(value.bit_length(), 1)
    bits = [(value >> i) & 1 for i in range(n_bits - 1, -1, -1)]
    bits_str = ''.join(map(str, bits))

    print(f'\n  ┌── Saisie opérande {label} = {value}₁₀ ({bits_str}₂, {n_bits} bits) ──')
    print(f'  │  Touche "{char_repr}" (poids faible "{last_digit}", ASCII 0x{ascii_code:02X})')
    print(f'  │  Matrice : ligne {ascii_code % 8}, col {ascii_code // 8}')
    print(f'  │  Anti-rebond 10 ms ; Vcc=3.3 V ; R_pullup=10 kΩ')

    if full_chain:
        print('  │')
        mosfet = L0_mosfet_eq(cfg, label)
        L0_inverter_eq(cfg, mosfet, label)
    else:
        I = 0.5 * cfg['mosfet_mu_cox_uA_V2'] * cfg['mosfet_WL'] * (3.3 - cfg['mosfet_vth_v']) ** 2
        print(f'  │  MOSFET passant (I_D ≈ {I * 1e6:.0f} µA) → inverseur (t_d ≈ ps) → idem')

    print(f'  │  Registre {n_bits}× bascule D master-slave (front montant 1 GHz) :')
    print(f'  │     Q[{n_bits - 1}..0] = {bits_str}  (valeur stockée : {value})')
    f_clk = 1e9
    C_gate = 10e-15
    P_dyn = 0.5 * C_gate * cfg['vdd_core_v'] ** 2 * f_clk * 4 * n_bits
    print(f'  │  P_dyn ≈ {P_dyn * 1e6:.2f} µW (4 portes/bascule × {n_bits} bascules)')
    print(f'  └── R_{label} = {value}')

    return {'value': value, 'n_bits': n_bits, 'bits': bits}


def L0_unified(cfg: dict, a: int, b: int) -> tuple:
    banner('NIVEAU 0 — Saisie clavier → deux registres (chaîne physique)')
    print('  Architecture (par opérande) :')
    print('    Touche → Debounce → MOSFET → Inverseur CMOS → Bascule D × N → Registre')
    print('  NAND : primitive universelle montrée en référence.')
    print('  Chaque opérande a son propre registre. L1 (adder) lit R_A et R_B.')

    reg_a = L0_keypress(cfg, a, 'A', full_chain=True)
    L0_nand_reference()
    reg_b = L0_keypress(cfg, b, 'B', full_chain=False)

    print('\n  🔗 Liaison L0 → L1 :')
    print(f'     R_A = {a}  ({"".join(map(str, reg_a["bits"]))}₂)')
    print(f'     R_B = {b}  ({"".join(map(str, reg_b["bits"]))}₂)')
    print('     → entrées A et B du full adder (Niveau 1)')

    return reg_a, reg_b


# ============================================================================
# NIVEAU 1 — Additionneur full
# ============================================================================

def L1_full_adder(reg_a: dict, reg_b: dict) -> int:
    a, b = reg_a['value'], reg_b['value']
    n_bits = max(a.bit_length(), b.bit_length(), 1) + 1

    banner(f'NIVEAU 1 — Full adder : R_A + R_B = {a} + {b}')
    print(f'  Opérandes lues depuis L0 : R_A={a}, R_B={b}')
    print(f'  Largeur calculée : {n_bits} bits (= max(bit_length) + 1)\n')

    bits_a = [(a >> i) & 1 for i in range(n_bits)]
    bits_b = [(b >> i) & 1 for i in range(n_bits)]
    bits_s = []
    Cin = 0
    for i in range(n_bits):
        Ai, Bi = bits_a[i], bits_b[i]
        Si = Ai ^ Bi ^ Cin
        Cout = (Ai & Bi) | (Cin & (Ai ^ Bi))
        bits_s.append(Si)
        if i < 6 or Cout:
            print(f'  bit {i:2d}: A={Ai} B={Bi} Cin={Cin} → S={Si} Cout={Cout}')
        Cin = Cout

    result = sum(bits_s[i] << i for i in range(n_bits))
    result_str = ''.join(str(bits_s[i]) for i in range(n_bits - 1, -1, -1))
    print(f'\n  Résultat : {result_str}₂ = {result}₁₀')
    print(f'  Envoyé à L2 (ARMv8 ALU)')
    return result


# ============================================================================
# NIVEAU 2 — Instruction ARMv8
# ============================================================================

def L2_alu_arm(a: int, b: int, result: int) -> None:
    banner('NIVEAU 2 — Instruction ARMv8 ADD')
    print(f'  MOV  W0, #{a:<10d} ; W0 = 0x{a & 0xFFFFFFFF:08X}')
    print(f'  MOV  W1, #{b:<10d} ; W1 = 0x{b & 0xFFFFFFFF:08X}')
    print(f'  ADD  W2, W0, W1        ; W2 = 0x{result & 0xFFFFFFFF:08X}')
    enc = (0 << 31) | (0 << 30) | (0 << 29) | (0b01011 << 24) | (0 << 22) | \
          (0 << 21) | (1 << 16) | (0 << 10) | (0 << 5) | 2
    print(f'  Encodage 32 bits : 0x{enc:08X}')


# ============================================================================
# NIVEAU 3 — JSON payload
# ============================================================================

def L3_payload(result: int) -> bytes:
    banner('NIVEAU 3 — Payload JSON applicatif')
    s = json.dumps({'result': result}, separators=(',', ':'))
    payload = s.encode('ascii')
    print(f'  json.dumps → "{s}" ({len(payload)} octets)')
    print(hexdump(payload, '  '))
    return payload


# ============================================================================
# NIVEAU 4 — TCP
# ============================================================================

def L4_tcp(cfg: dict, payload: bytes) -> bytes:
    banner('NIVEAU 4 — Segment TCP')
    sport, dport = cfg['src_port'], cfg['dst_port']
    seq, ack = cfg['tcp_seq'], cfg['tcp_ack']
    data_off, flags = 5, 0x18
    window = cfg['tcp_window']
    tcp_no_csum = struct.pack('>HHIIBBHHH', sport, dport, seq, ack,
                              data_off << 4, flags, window, 0, 0)
    src_ip = ip_to_bytes(cfg['src_ip'])
    dst_ip = ip_to_bytes(cfg['dst_ip'])
    tcp_len = len(tcp_no_csum) + len(payload)
    pseudo = src_ip + dst_ip + b'\x00\x06' + struct.pack('>H', tcp_len)
    csum = ip_checksum(pseudo + tcp_no_csum + payload)
    tcp_hdr = struct.pack('>HHIIBBHHH', sport, dport, seq, ack,
                          data_off << 4, flags, window, csum, 0)
    segment = tcp_hdr + payload
    print(f'  {sport} → {dport} ; seq=0x{seq:08X} ack=0x{ack:08X}')
    print(f'  flags=0x{flags:02X} (PSH+ACK) window={window} csum=0x{csum:04X}')
    print(f'  Segment ({len(segment)} octets) :')
    print(hexdump(segment, '  '))
    return segment


# ============================================================================
# NIVEAU 5 — IPv4
# ============================================================================

def L5_ip(cfg: dict, tcp_segment: bytes) -> bytes:
    banner('NIVEAU 5 — Paquet IPv4')
    total_len = 20 + len(tcp_segment)
    ipid, ttl, proto = 0xABCD, 64, 6
    src_ip = ip_to_bytes(cfg['src_ip'])
    dst_ip = ip_to_bytes(cfg['dst_ip'])
    ip_no_csum = struct.pack('>BBHHHBBH', 0x45, 0x00, total_len, ipid, 0x4000,
                             ttl, proto, 0) + src_ip + dst_ip
    csum = ip_checksum(ip_no_csum)
    ip_hdr = struct.pack('>BBHHHBBH', 0x45, 0x00, total_len, ipid, 0x4000,
                        ttl, proto, csum) + src_ip + dst_ip
    packet = ip_hdr + tcp_segment
    print(f'  {cfg["src_ip"]} → {cfg["dst_ip"]} ; len={total_len} ttl={ttl} proto=TCP(6)')
    print(f'  header csum = 0x{csum:04X}')
    print(f'  Paquet ({len(packet)} octets) :')
    print(hexdump(packet, '  '))
    return packet


# ============================================================================
# NIVEAU 6 — Ethernet
# ============================================================================

def L6_ethernet(cfg: dict, ip_packet: bytes) -> bytes:
    banner('NIVEAU 6 — Trame Ethernet')
    src_mac = mac_to_bytes(cfg['src_mac'])
    dst_mac = mac_to_bytes(cfg['dst_mac'])
    ethertype = struct.pack('>H', 0x0800)
    frame_no_fcs = dst_mac + src_mac + ethertype + ip_packet
    fcs = binascii.crc32(frame_no_fcs) & 0xFFFFFFFF
    frame = frame_no_fcs + struct.pack('<I', fcs)
    print(f'  {cfg["src_mac"]} → {cfg["dst_mac"]} ; EtherType=0x0800 (IPv4)')
    print(f'  FCS (CRC32) = 0x{fcs:08X}')
    print(f'  Trame ({len(frame)} octets) :')
    print(hexdump(frame, '  '))
    return frame


# ============================================================================
# NIVEAU 7 — LTE RAN avec vraie chaîne Milenage
# ============================================================================

def L7_lte_ran(cfg: dict, ip_packet: bytes) -> bytes:
    """Retourne uniquement le transport_block (le "fil" qui descend vers la PHY).
    K_UPenc et COUNT ne sont PAS retournés — L13 les re-dérive depuis cfg
    et lit la SN depuis le PDCP header (pas de gruge TX→RX)."""
    banner('NIVEAU 7 — Pile RAN LTE Uu : Milenage AKA + PDCP / RLC / MAC / CRC')

    # --- Paramètres AKA ----------------------------------------------------
    K = bytes.fromhex(cfg['k'])
    OP = bytes.fromhex(cfg['op'])
    RAND = bytes.fromhex(cfg['rand'])
    SQN = bytes.fromhex(cfg['sqn'])
    AMF = int(str(cfg['amf']), 16).to_bytes(2, 'big')

    imsi_str = str(cfg['imsi'])
    mcc, mnc = imsi_str[:3], imsi_str[3:5]
    plmn_id = encode_plmn(mcc, mnc)

    print(f'  Paramètres sécurité (TS 33.401, vraie chaîne Milenage) :')
    print(f'    IMSI = {imsi_str}  (MCC={mcc}, MNC={mnc} → PLMN={plmn_id.hex()})')
    print(f'    K    = {K.hex()}')
    print(f'    OP   = {OP.hex()}')
    print(f'    OPC  = {make_OPc(K, OP).hex()}  ← AES_K(OP) ⊕ OP')
    print(f'    RAND = {RAND.hex()}')
    print(f'    SQN  = {SQN.hex()}    AMF = {AMF.hex()}')
    print(f'    RNTI = 0x{cfg["rnti"]:04X}\n')

    # --- Vraie chaîne complète ---------------------------------------------
    aka = lte_aka_full_chain(K, OP, RAND, SQN, AMF, plmn_id,
                              cfg['nas_ul_count'], cfg['eea_id'])

    print(f'  Étape 1 — Milenage (CryptoMobile) :')
    print(f'    MAC-A = {aka["mac_a"].hex()}  ← f1(K, RAND, SQN, AMF)')
    print(f'    RES   = {aka["RES"].hex()}              ← f2')
    print(f'    CK    = {aka["CK"].hex()}  ← f3')
    print(f'    IK    = {aka["IK"].hex()}  ← f4')
    print(f'    AK    = {aka["AK"].hex()}                       ← f5')
    print(f'  Étape 2 — AUTN = (SQN⊕AK) || AMF || MAC-A :')
    print(f'    SQN⊕AK = {aka["sqn_xor_ak"].hex()}')
    print(f'    AUTN   = {aka["autn"].hex()}')
    print(f'  Étape 3 — K_ASME (TS 33.401 A.2, FC=0x10) :')
    print(f'    {aka["k_asme"].hex()}')
    print(f'  Étape 4 — K_eNB (A.3, FC=0x11, NAS_UL_COUNT={cfg["nas_ul_count"]}) :')
    print(f'    {aka["k_enb"].hex()}')
    print(f'  Étape 5 — K_UPenc (A.7, FC=0x15, P0=0x05, P1=EEA{cfg["eea_id"]}) [128 LSB] :')
    print(f'    {aka["k_upenc"].hex()}\n')

    k_upenc = aka['k_upenc']

    # --- PDCP : header 2 octets + AES-128 CTR ------------------------------
    pdcp_sn = 0x123
    pdcp_hdr = struct.pack('>H', pdcp_sn & 0x0FFF)
    hfn = 0x0000
    count = (hfn << 12) | pdcp_sn

    ctr = Counter.new(128, initial_value=count << 96, little_endian=False)
    cipher = AES.new(k_upenc, AES.MODE_CTR, counter=ctr)
    pdcp_payload = cipher.encrypt(ip_packet)
    pdcp_pdu = pdcp_hdr + pdcp_payload

    print(f'  PDCP SN=0x{pdcp_sn:03X}, COUNT=0x{count:08X} (HFN=0x{hfn:04X})')
    print(f'  AES-128-CTR chiffrement → PDU {len(pdcp_pdu)} octets :')
    print(hexdump(pdcp_pdu, '    '))

    # --- RLC UM ------------------------------------------------------------
    rlc_sn = pdcp_sn & 0x3FF
    rlc_hdr = struct.pack('>H', rlc_sn & 0x03FF)
    rlc_pdu = rlc_hdr + pdcp_pdu
    print(f'\n  RLC UM : SN=0x{rlc_sn:03X}, PDU {len(rlc_pdu)} octets')

    # --- MAC subheader TS 36.321 §6.1.2 ------------------------------------
    lcid = 0x01
    L = len(rlc_pdu)
    e = 0
    if L < 128:
        mac_hdr = bytes([(0 << 7) | (0 << 6) | (e << 5) | (lcid & 0x1F),
                         (0 << 7) | (L & 0x7F)])
    else:
        mac_hdr = bytes([(0 << 7) | (0 << 6) | (e << 5) | (lcid & 0x1F),
                         (1 << 7) | ((L >> 8) & 0x7F),
                         L & 0xFF])
    mac_pdu = mac_hdr + rlc_pdu
    print(f'  MAC subheader (TS 36.321 §6.1.2) : LCID={lcid}, L={L}')
    print(f'    octets header = {mac_hdr.hex()}  (R=0 F={"1" if L>=128 else "0"} E={e} LCID=0x{lcid:02X})')
    print(f'    PDU {len(mac_pdu)} octets')

    # --- CRC-24A et TB -----------------------------------------------------
    crc = crc24a(mac_pdu)
    tb = mac_pdu + crc.to_bytes(3, 'big')
    print(f'\n  CRC-24A = 0x{crc:06X}')
    print(f'  Transport Block ({len(tb)} octets = {len(tb) * 8} bits) :')
    print(hexdump(tb, '    '))

    return tb


# ============================================================================
# NIVEAU 8 — Codage canal CONVOLUTIF (commpy) + scrambling LTE
# ============================================================================

def L8_phy_coding(cfg: dict, tb: bytes) -> tuple:
    """Encodage convolutif rate-1/3 + scrambling Gold LTE.
    Retourne (scrambled_bits, scrambling_seq, tb_bit_len, coded_len, n_prb_used)."""
    banner('NIVEAU 8 — Codage convolutif rate-1/3 (commpy) + scrambling Gold (TS 36.211 §7.2)')

    tb_bits = np.unpackbits(np.frombuffer(tb, dtype=np.uint8))
    tb_bit_len = len(tb_bits)

    # --- Encodage convolutif (vraie lib) -----------------------------------
    coded = conv_encode_lte_like(tb_bits)
    coded_len = len(coded)
    rate = tb_bit_len / coded_len
    print(f'  Codeur convolutif : g=(13,15,17)₈, K=4, rate=1/3')
    print(f'  TB = {tb_bit_len} bits → coded = {coded_len} bits (rate effectif {rate:.3f})')
    print(f'  ⚠️  Substitut pédagogique au turbo 3GPP (TS 36.212 §5.1.3, RSC×2 + QPP).')
    print(f'      Même principe à treillis ; vraie lib (commpy) ; Viterbi en RX.\n')

    # --- Dimensionnement dynamique du grid PRB -----------------------------
    # On choisit n_prb pour que bits_avail = n_prb * 144 * 4 ≥ coded_len, puis on pad.
    bits_per_prb = 144 * 4  # 144 REs × 4 bits/symbole (16-QAM)
    n_prb = max(1, (coded_len + bits_per_prb - 1) // bits_per_prb)
    bits_avail = n_prb * bits_per_prb
    n_pad = bits_avail - coded_len
    padded = np.concatenate([coded, np.zeros(n_pad, dtype=np.uint8)])
    print(f'  Dimensionnement grid : n_prb={n_prb} (forcé par coded_len), '
          f'bits_avail={bits_avail}, padding={n_pad}')

    # --- Scrambling Gold ---------------------------------------------------
    cinit = (cfg['rnti'] << 14) | (0 << 13) | (cfg['subframe'] << 9) | cfg['pci']
    scrambling = lte_gold_sequence(cinit, bits_avail)
    scrambled = padded ^ scrambling

    print(f'  Scrambling LTE Gold (Nc=1600) :')
    print(f'    c_init = 0x{cinit:08X}  (RNTI=0x{cfg["rnti"]:04X}, subframe={cfg["subframe"]}, PCI={cfg["pci"]})')
    print(f'    Premiers 32 bits scramblés : {"".join(map(str, scrambled[:32]))}')

    return scrambled, scrambling, tb_bit_len, coded_len, n_prb


# ============================================================================
# NIVEAU 9 — Mapping 16-QAM
# ============================================================================

def L9_qam16(scrambled: np.ndarray) -> np.ndarray:
    banner('NIVEAU 9 — Mapping 16-QAM (TS 36.211 §7.1.3, Gray normalisé √10)')
    symbols = qam16_map(scrambled)
    print(f'  {len(symbols)} symboles 16-QAM')
    print('  Premiers 8 symboles :')
    for k in range(min(8, len(symbols))):
        b = ''.join(str(int(scrambled[4 * k + i])) for i in range(4))
        s = symbols[k]
        print(f'    [{k}] bits={b} → s = {s.real:+.4f} {s.imag:+.4f}j  |s|={abs(s):.4f}')
    mean_power = np.mean(np.abs(symbols) ** 2)
    print(f'  E[|s|²] = {mean_power:.4f}  (cible 1.0)')

    # Démo LLR sur les premiers symboles (soft demap réel)
    print('\n  Démo soft demap (max-log-MAP, σ²=1) — LLRs des 4 premiers symboles :')
    llrs_demo = qam16_demap_soft(symbols[:4], noise_var=1.0)
    for k in range(4):
        l = llrs_demo[4 * k:4 * k + 4]
        print(f'    [{k}] LLR(b0..b3) = [{l[0]:+7.3f}, {l[1]:+7.3f}, {l[2]:+7.3f}, {l[3]:+7.3f}]'
              f'  → bits durs = {[int(x < 0) for x in l]}')
    return symbols


# ============================================================================
# NIVEAU 9.5 — PSS (illustration, non injecté dans l'OFDM)
# ============================================================================

def L9p5_pss_demo(cfg: dict) -> None:
    banner('NIVEAU 9.5 — PSS Zadoff-Chu (TS 36.211 §6.11.1) — illustration')
    n_id_2 = cfg.get('n_id_2', cfg['pci'] % 3)
    pss = pss_zadoff_chu(n_id_2)
    print(f'  N_ID_2 = {n_id_2}  (PCI={cfg["pci"]} mod 3) → u = {{25,29,34}}[{n_id_2}]')
    print(f'  Séquence Zadoff-Chu longueur 62 (E[|d|²] = {np.mean(np.abs(pss)**2):.4f})')
    print(f'  Auto-corrélation circulaire (peak/sidelobe) :')
    ac = np.abs(np.fft.ifft(np.abs(np.fft.fft(pss))**2))
    peak = ac[0]
    sidelobe = np.max(ac[1:])
    print(f'    peak = {peak:.3f}, max sidelobe = {sidelobe:.3f}, ratio = {peak/sidelobe:.2f}')
    print(f'  Premiers 4 échantillons : {pss[:4]}')
    print(f'  ⚠️  Non injecté dans l\'OFDM ici (placement réel : SC 0..30, 32..62 du slot 0/10).')


# ============================================================================
# NIVEAU 10 — OFDM
# ============================================================================

def L10_ofdm(cfg: dict, symbols: np.ndarray, n_prb_used: int) -> tuple:
    """Génère N symboles OFDM pour transporter tous les symboles 16-QAM.
    Retourne (x_full, sc_offset, n_sc, n_ofdm) pour L13."""
    banner('NIVEAU 10 — OFDM : IFFT + préfixe cyclique (multi-symboles)')
    N_FFT = cfg['fft_size']
    prb_start = cfg['prb_start']
    n_sc = n_prb_used * 12
    cp_len = int(N_FFT * 144 / 2048)
    center = N_FFT // 2
    sc_offset = (prb_start - 50) * 12

    n_total = len(symbols)
    n_ofdm = (n_total + n_sc - 1) // n_sc  # ceil
    # Pad pour que n_ofdm * n_sc == len(symbols_padded)
    if n_total < n_ofdm * n_sc:
        symbols = np.concatenate([symbols, np.zeros(n_ofdm * n_sc - n_total, dtype=complex)])

    x_chunks = []
    for i in range(n_ofdm):
        X = np.zeros(N_FFT, dtype=complex)
        sym_chunk = symbols[i * n_sc:(i + 1) * n_sc]
        for k, val in enumerate(sym_chunk):
            X[(center + sc_offset + k) % N_FFT] = val
        x_time = np.fft.ifft(X) * np.sqrt(N_FFT)
        x_chunks.append(np.concatenate([x_time[-cp_len:], x_time]))
    x_full = np.concatenate(x_chunks)

    fs = cfg['sample_rate_hz']
    Ts = 1.0 / fs
    T_sym = (N_FFT + cp_len) * Ts
    print(f'  N_FFT={N_FFT}, n_sc actives={n_sc} (n_prb={n_prb_used}), CP={cp_len}')
    print(f'  fs={fs / 1e6:.2f} MS/s, Ts={Ts * 1e9:.3f} ns, T_sym(+CP)={T_sym * 1e6:.2f} µs')
    print(f'  Symboles 16-QAM à transporter : {n_total} → {n_ofdm} symboles OFDM '
          f'(durée totale = {n_ofdm * T_sym * 1e6:.2f} µs)')
    print('  Premiers 8 échantillons I/Q du 1er symbole OFDM (après CP) :')
    for n in range(8):
        s = x_full[n]
        print(f'    n={n}  I={s.real:+.5f}  Q={s.imag:+.5f}  |s|={abs(s):.5f}')
    return x_full, sc_offset, n_sc, n_ofdm


# ============================================================================
# NIVEAU 11 — RF (démo math)
# ============================================================================

def L11_rf(cfg: dict, x_baseband: np.ndarray) -> None:
    banner('NIVEAU 11 — RF : DAC + mixeur quadrature (démo math)')
    fc = cfg['f_carrier_hz']
    fs = cfg['sample_rate_hz']
    Ts = 1.0 / fs
    P_tx = cfg.get('p_tx_dbm', 23)
    print(f'  f_c = {fc / 1e6:.1f} MHz (EARFCN UL {cfg["earfcn_ul"]}), P_TX = {P_tx} dBm')
    print(f'  s_RF(t) = I(t)·cos(2π f_c t) − Q(t)·sin(2π f_c t)')
    print(f'  ⚠️  fs={fs / 1e6:.2f} MS/s < 2·f_c : démo mathématique uniquement.')
    print(f'      Vrai pipeline : interpolation DAC + filtre reconstruction + upconv analogique.\n')
    print('  Évaluation analytique sur 4 échantillons :')
    for n in range(4):
        t = n * Ts
        I, Q = x_baseband[n].real, x_baseband[n].imag
        s_rf = I * np.cos(2 * np.pi * fc * t) - Q * np.sin(2 * np.pi * fc * t)
        print(f'    n={n} t={t * 1e9:6.2f} ns  I={I:+.4f} Q={Q:+.4f}  s_RF={s_rf:+.5f}')


# ============================================================================
# NIVEAU 12 — Friis
# ============================================================================

def L12_friis(cfg: dict) -> None:
    banner('NIVEAU 12 — Bilan de liaison Friis (UE → eNB)')
    fc = cfg['f_carrier_hz']
    d = cfg['distance_m']
    Pt = cfg['p_tx_dbm']
    Gt = cfg['g_tx_dbi']
    Gr = cfg['g_rx_dbi']
    L_excess = cfg['path_loss_excess_db']
    bw = cfg['bandwidth_hz']
    NF = cfg['nf_db']
    lam = 3e8 / fc
    L_fs_db = 10 * np.log10((4 * np.pi * d / lam) ** 2)
    L_total = L_fs_db + L_excess
    Pr = Pt + Gt + Gr - L_total
    N_sys = -174 + 10 * np.log10(bw) + NF
    SNR = Pr - N_sys
    print(f'  d={d} m, λ={lam * 100:.2f} cm')
    print(f'  L_FS={L_fs_db:.1f} dB + L_excess={L_excess} dB → L_total={L_total:.1f} dB')
    print(f'  P_r = {Pt}+{Gt}+{Gr}−{L_total:.1f} = {Pr:.1f} dBm')
    print(f'  N_sys = {N_sys:.1f} dBm → SNR ≈ {SNR:.1f} dB')


# ============================================================================
# NIVEAU 13 — Décapsulation avec asserts (channel AWGN optionnel)
# ============================================================================

def L13_decap(cfg: dict, *,
              x_rx: np.ndarray,
              dci: dict,
              expected_result: int,
              snr_db: float = 1000.0,
              use_soft_demap: bool = False,
              verbose: bool = False) -> dict:
    """Décapsulation indépendante de l'état TX.
    
    Entrées légitimes (aucun état "venu de TX" via Python) :
      x_rx : signal time-domain — les seuls bits qui passent "sur le fil"
      dci  : info de scheduling (tb_byte_len, n_prb, n_ofdm, sc_offset, n_sc)
             — en vrai LTE, l'eNB envoie ça via PDCCH/DCI
      cfg  : paramètres partagés (PHY config + K/OP/RAND/SQN/AMF/IMSI)
             — en vrai, l'eNB obtient K_ASME via S1AP depuis le MME,
               qui l'obtient depuis le HSS qui détient K
      expected_result : valeur d'origine, SEULE référence pour l'assertion finale
    
    L13 re-dérive K_UPenc indépendamment et lit la PDCP SN depuis le header
    pour reconstruire COUNT. Aucun bypass possible.
    """
    banner(f'NIVEAU 13 — Décap RX indépendante (SNR={snr_db if snr_db<300 else "∞"} dB, '
           f'demap={"soft" if use_soft_demap else "hard"})')
    results = {}

    # --- Canal AWGN ---------------------------------------------------------
    x_rx_noisy, noise_var = awgn_channel(x_rx, snr_db)
    if snr_db < 300:
        print(f'  Canal AWGN : σ² = {noise_var:.6f}')
    else:
        print('  Canal AWGN désactivé (SNR ≥ 300 dB)')

    # --- L10 inverse : multi-symboles OFDM ---------------------------------
    N_FFT = cfg['fft_size']
    cp_len = int(N_FFT * 144 / 2048)
    samples_per_sym = N_FFT + cp_len
    center = N_FFT // 2
    n_sc = dci['n_sc']
    n_ofdm = dci['n_ofdm']
    sc_offset = dci['sc_offset']

    symbols_rx_chunks = []
    for i in range(n_ofdm):
        chunk = x_rx_noisy[i * samples_per_sym:(i + 1) * samples_per_sym]
        x_no_cp = chunk[cp_len:]
        X_rx = np.fft.fft(x_no_cp) / np.sqrt(N_FFT)
        sc_rx = np.array([X_rx[(center + sc_offset + k) % N_FFT] for k in range(n_sc)])
        symbols_rx_chunks.append(sc_rx)
    symbols_rx = np.concatenate(symbols_rx_chunks)
    print(f'  L10 inverse : {n_ofdm} FFT → {len(symbols_rx)} symboles 16-QAM')

    # --- L9 inverse : demap ------------------------------------------------
    if use_soft_demap:
        llrs = qam16_demap_soft(symbols_rx, noise_var=max(noise_var, 1e-9))
        bits_rx = (llrs < 0).astype(np.uint8)
        print(f'  L9  inverse : démap soft (LLR) → {len(bits_rx)} bits')
    else:
        bits_rx = qam16_demap_hard(symbols_rx)
        print(f'  L9  inverse : démap hard → {len(bits_rx)} bits')

    # --- L8 inverse : descramble (regénérée depuis cfg) + Viterbi ----------
    cinit = (cfg['rnti'] << 14) | (0 << 13) | (cfg['subframe'] << 9) | cfg['pci']
    scrambling_rx = lte_gold_sequence(cinit, len(bits_rx))
    descrambled = bits_rx ^ scrambling_rx
    print(f'  L8  inverse : descramble (c_init=0x{cinit:08X} regénérée depuis cfg)')

    tb_bit_len = dci['tb_byte_len'] * 8
    coded_len = 3 * (tb_bit_len + 3)  # rate 1/3 + 3 tail bits (memory=3)
    if coded_len > len(descrambled):
        print(f'  ❌ coded_len={coded_len} > bits disponibles={len(descrambled)}')
        results['decode'] = False
        results['final'] = False
        return results
    coded_rx = descrambled[:coded_len]
    tb_bits_recovered = conv_decode_lte_like(coded_rx, tb_bit_len, decoding_type='hard')
    print(f'  L8          : Viterbi rate-1/3 → {tb_bit_len} TB bits '
          f'(coded_len déduit de DCI.tb_byte_len={dci["tb_byte_len"]})')

    # --- L7 inverse : CRC + parsing MAC/RLC/PDCP indépendant ---------------
    tb_recovered = np.packbits(tb_bits_recovered).tobytes()
    crc_rx = int.from_bytes(tb_recovered[-3:], 'big')
    crc_calc = crc24a(tb_recovered[:-3])
    crc_ok = (crc_rx == crc_calc)
    print(f'  L7  CRC-24A : 0x{crc_rx:06X} vs 0x{crc_calc:06X}  [{"OK" if crc_ok else "FAIL"}]')
    results['crc'] = crc_ok
    if not crc_ok:
        print('  ❌ CRC fail → abort, pas de tentative crypto')
        results['final'] = False
        return results

    # MAC subheader parsing
    mac_pdu = tb_recovered[:-3]
    b0 = mac_pdu[0]
    lcid = b0 & 0x1F
    b1 = mac_pdu[1]
    if b1 & 0x80:
        L = ((b1 & 0x7F) << 8) | mac_pdu[2]
        rlc_pdu = mac_pdu[3:3 + L]
    else:
        L = b1 & 0x7F
        rlc_pdu = mac_pdu[2:2 + L]
    print(f'  L7  MAC parsed : LCID={lcid}, L={L}')

    # RLC UM strip
    pdcp_pdu = rlc_pdu[2:]

    # PDCP header parsing → lecture SN
    pdcp_sn = struct.unpack('>H', pdcp_pdu[:2])[0] & 0x0FFF
    print(f'  L7  PDCP header : SN=0x{pdcp_sn:03X} (lue depuis octets reçus)')

    # --- Re-dérivation K_UPenc INDÉPENDANTE (le point central) -------------
    K = bytes.fromhex(cfg['k'])
    OP = bytes.fromhex(cfg['op'])
    RAND = bytes.fromhex(cfg['rand'])
    SQN = bytes.fromhex(cfg['sqn'])
    AMF = int(str(cfg['amf']), 16).to_bytes(2, 'big')
    imsi_str = str(cfg['imsi'])
    plmn_id = encode_plmn(imsi_str[:3], imsi_str[3:5])
    aka_rx = lte_aka_full_chain(K, OP, RAND, SQN, AMF, plmn_id,
                                 cfg['nas_ul_count'], cfg['eea_id'])
    k_upenc_rx = aka_rx['k_upenc']
    print(f'  L7  K_UPenc (re-dérivée côté RX, AKA complète) :')
    print(f'        {k_upenc_rx.hex()}')
    print(f'        ↑ HSS détient K, MME reçoit K_ASME, eNB reçoit K_eNB via S1AP,')
    print(f'          puis dérive K_UPenc. Ici on simule en re-faisant la chaîne complète.')

    # Reconstruct COUNT depuis SN lue + HFN (état RRC, init à 0)
    HFN_state = 0
    count_rx = (HFN_state << 12) | pdcp_sn
    print(f'  L7  COUNT reconstruit : (HFN=0x{HFN_state:04X} << 12) | SN=0x{pdcp_sn:03X} = 0x{count_rx:08X}')

    # AES-CTR decrypt avec K_UPenc re-dérivée
    ciphertext = pdcp_pdu[2:]
    ctr = Counter.new(128, initial_value=count_rx << 96, little_endian=False)
    cipher = AES.new(k_upenc_rx, AES.MODE_CTR, counter=ctr)
    ip_packet_rx = cipher.decrypt(ciphertext)
    print(f'  L7  AES-128-CTR déchiffrement → IP {len(ip_packet_rx)} octets')

    # --- L5/L4/L3 inverse --------------------------------------------------
    # Validation IPv4 header
    if len(ip_packet_rx) < 20 or (ip_packet_rx[0] >> 4) != 4:
        print(f'  ❌ Pas un paquet IPv4 valide (version={ip_packet_rx[0] >> 4 if ip_packet_rx else "?"})')
        results['ip_parse'] = False
        results['final'] = False
        return results
    print(f'  L5  IPv4 parsed : version=4, IHL={ip_packet_rx[0] & 0xF}')

    tcp_segment = ip_packet_rx[20:]
    data_off = (tcp_segment[12] >> 4) & 0x0F
    tcp_hdr_len = data_off * 4
    payload = tcp_segment[tcp_hdr_len:]
    print(f'  L4  TCP parsed : data_offset={data_off}, payload {len(payload)} octets')

    try:
        obj = json.loads(payload.decode('ascii'))
        result_rx = obj.get('result')
        json_ok = True
    except Exception as e:
        result_rx = None
        json_ok = False
        print(f'  ❌ json.loads échoué : {e}')

    results['json'] = json_ok

    # --- VERDICT FINAL : seule comparaison légitime ------------------------
    print()
    print('  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓')
    print(f'  ┃  Payload JSON décodé du flux RX : {payload!r:<29}┃')
    print(f'  ┃  result_rx = {str(result_rx):<10}   (attendu : {expected_result})                  ┃')
    final_ok = (result_rx == expected_result)
    verdict = '✅ MATCH : le « 2 » a réellement traversé la pile' if final_ok \
              else f'❌ MISMATCH : {result_rx} ≠ {expected_result}'
    print(f'  ┃  {verdict:<63}┃')
    print('  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛')

    results['final'] = final_ok
    results['result_rx'] = result_rx
    return results


# ============================================================================
# NIVEAU 14 — Glyph rastérisé (multi-digit)
# ============================================================================

DEFAULT_GLYPHS = {
    '0': [0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    '1': [0x18, 0x1C, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    '2': [0x3C, 0x66, 0x06, 0x0C, 0x18, 0x30, 0x7E, 0x00],
    '3': [0x3C, 0x66, 0x06, 0x1C, 0x06, 0x66, 0x3C, 0x00],
    '4': [0x0C, 0x1C, 0x2C, 0x4C, 0x7E, 0x0C, 0x0C, 0x00],
    '5': [0x7E, 0x60, 0x7C, 0x06, 0x06, 0x66, 0x3C, 0x00],
    '6': [0x3C, 0x60, 0x7C, 0x66, 0x66, 0x66, 0x3C, 0x00],
    '7': [0x7E, 0x06, 0x0C, 0x18, 0x30, 0x30, 0x30, 0x00],
    '8': [0x3C, 0x66, 0x66, 0x3C, 0x66, 0x66, 0x3C, 0x00],
    '9': [0x3C, 0x66, 0x66, 0x3E, 0x06, 0x66, 0x3C, 0x00],
}


def raster_one_glyph(char: str, font_path: str = None, size: int = 8) -> list:
    try:
        if font_path is None:
            font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
        img = Image.new('L', (size, size), 0)
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_path, size=size)
        bbox = draw.textbbox((0, 0), char, font=font)
        x = (size - (bbox[2] - bbox[0])) // 2 - bbox[0]
        y = (size - (bbox[3] - bbox[1])) // 2 - bbox[1]
        draw.text((x, y), char, fill=255, font=font)
        arr = np.array(img)
        bits = (arr > 127).astype(np.uint8)
        rows = []
        for r in bits:
            byte = 0
            for b in r[:8]:
                byte = (byte << 1) | int(b)
            rows.append(byte)
        return rows
    except Exception:
        return DEFAULT_GLYPHS.get(char, [0] * 8)


def L14_glyph(result: int, font_path: str = None) -> int:
    text = str(result)
    banner(f'NIVEAU 14 — Glyph "{text}" rastérisé ({len(text)} × bitmap 8×8)')
    glyphs = [raster_one_glyph(c, font_path) for c in text]

    print('  Représentation visuelle (█ = pixel ON, · = pixel OFF) :')
    for row_idx in range(8):
        line = '    '
        for g in glyphs:
            line += ''.join('█' if (g[row_idx] >> (7 - b)) & 1 else '·' for b in range(8))
            line += ' '
        print(line)

    n_on = sum(bin(b).count('1') for g in glyphs for b in g)
    print(f'\n  Total pixels allumés : {n_on} sur {64 * len(glyphs)}')
    return n_on


# ============================================================================
# NIVEAU 15 — OLED (Shockley diode, vraie I-V)
# ============================================================================

def L15_oled(cfg: dict, n_pixels_on: int) -> None:
    banner('NIVEAU 15 — Sous-pixel OLED : diode Shockley + Rs (boucle bouclée)')
    V = cfg['oled_voltage_v']
    Is = cfg.get('oled_is_a', 1e-12)
    n_diode = cfg.get('oled_ideality_n', 2.0)
    T_K = cfg.get('oled_temp_k', 300.0)
    Rs = cfg['oled_rs_ohm']
    VT = 1.380649e-23 * T_K / 1.602176634e-19  # kT/q

    I_per, Vd = shockley_iv_with_rs(V, Is, n_diode, VT, Rs)
    P_per = V * I_per
    n_sub = n_pixels_on * 3

    print(f'  Modèle : I = Is·(exp(V_d/(n·VT)) − 1)  ;  V = V_d + I·Rs')
    print(f'    V = {V} V  ;  Is = {Is:.2e} A  ;  n = {n_diode}  ;  '
          f'VT = {VT * 1000:.2f} mV (T={T_K} K)  ;  Rs = {Rs/1e3:.1f} kΩ')
    print(f'  Résolution bisection :')
    print(f'    V_diode  = {Vd*1e3:.2f} mV')
    print(f'    V_Rs     = {(V-Vd)*1e3:.2f} mV  (chute IR sur Rs)')
    print(f'    I_pixel  = {I_per * 1e6:.3f} µA')
    print(f'    P_pixel  = V·I = {P_per * 1e6:.3f} µW')
    print(f'  {n_pixels_on} pixels ON × 3 sous-pixels = {n_sub} sous-pixels')
    print(f'    I_total = {n_sub * I_per * 1e3:.3f} mA   P_total = {n_sub * P_per * 1e3:.3f} mW')
    print()
    print('  ┌──────────────────────────────────────────────────────────────────┐')
    print(f'  │  TX (L0)  : MOSFET en saturation, I_D ≈ µA (modèle quadratique)  │')
    print(f'  │  RX (L15) : Shockley + Rs, I_pixel = {I_per*1e6:7.2f} µA               │')
    print('  │  Deux régimes physiques distincts, deux équations distinctes.    │')
    print('  │  Sans Rs, Shockley nu diverge à V > V_th ; Rs auto-limite.       │')
    print('  └──────────────────────────────────────────────────────────────────┘')


# ============================================================================
# MAIN
# ============================================================================

def parse_addition(s: str) -> tuple:
    if '+' not in s:
        raise ValueError("Format attendu : a+b (ex: 1+1, 999+1)")
    a, b = s.split('+', 1)
    return int(a), int(b)


def parse_override(s: str) -> tuple:
    """Parse 'key=value' avec même heuristique que load_csv (hex, int, float, str)."""
    if '=' not in s:
        raise ValueError(f"Override invalide '{s}' — format attendu : key=value")
    k, v = s.split('=', 1)
    k, v = k.strip(), v.strip()
    if v.startswith(('0x', '0X')):
        return k, int(v, 16)
    try:
        return k, int(v)
    except ValueError:
        try:
            return k, float(v)
        except ValueError:
            return k, v  # string (typiquement hex sans préfixe pour K, OP, etc.)


def main():
    ap = argparse.ArgumentParser(
        description='Trace LTE/NR honnête (real libs) : MOSFET → OLED',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('csv_file', help='Fichier CSV de config')
    ap.add_argument('addition', nargs='?', default='1+1', help='Addition (ex: 16+16)')
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='Détail round-trip par niveau')
    ap.add_argument('--check', action='store_true',
                    help='Mode silencieux : exit 0 si round-trip OK, 1 sinon')
    ap.add_argument('--font', help='Chemin vers une TTF (sinon DejaVuSansMono)')
    ap.add_argument('--snr-db', type=float, default=1000.0,
                    help='SNR du canal AWGN en dB (défaut: ∞, pas de bruit)')
    ap.add_argument('--soft-demap', action='store_true',
                    help='Utiliser la démap soft (LLR max-log-MAP) au lieu de hard')
    ap.add_argument('--rx-override', action='append', default=[], metavar='KEY=VAL',
                    help='Override une clé cfg côté RX uniquement (entre L7 et L13). '
                         'Répétable. Ex: --rx-override k=ff...ff --rx-override rand=00...00 . '
                         'Permet de tester que L13 utilise vraiment son propre cfg '
                         '(et pas un état hérité de TX).')
    args = ap.parse_args()

    cfg = load_csv(args.csv_file)
    a, b = parse_addition(args.addition)

    import io, contextlib
    sink = io.StringIO() if args.check else None
    cm = contextlib.redirect_stdout(sink) if sink else contextlib.nullcontext()

    with cm:
        print(f'\n📁 Config : {len(cfg)} clés ; addition : {a} + {b}')
        if args.snr_db < 300:
            print(f'🌀 Canal AWGN actif : SNR = {args.snr_db} dB')
        if args.soft_demap:
            print(f'🎯 Démap soft (LLR max-log-MAP)')

        reg_a, reg_b = L0_unified(cfg, a, b)
        result = L1_full_adder(reg_a, reg_b)
        assert result == a + b, f"L1 incohérent : {result} != {a + b}"

        L2_alu_arm(a, b, result)
        payload = L3_payload(result)
        tcp_seg = L4_tcp(cfg, payload)
        ip_pkt = L5_ip(cfg, tcp_seg)
        L6_ethernet(cfg, ip_pkt)

        tb = L7_lte_ran(cfg, ip_pkt)
        scrambled, scrambling, tb_bit_len, coded_len, n_prb_used = L8_phy_coding(cfg, tb)
        symbols = L9_qam16(scrambled)
        L9p5_pss_demo(cfg)
        x_with_cp, sc_offset, n_sc, n_ofdm = L10_ofdm(cfg, symbols, n_prb_used)
        L11_rf(cfg, x_with_cp)
        L12_friis(cfg)

        # DCI : info que l'eNB enverrait via PDCCH au RX (taille TB, allocation)
        # En LTE réel : DCI format 0/1A signale RB allocation + MCS → TB size table
        dci = {
            'tb_byte_len': len(tb),
            'n_prb': n_prb_used,
            'n_ofdm': n_ofdm,
            'sc_offset': sc_offset,
            'n_sc': n_sc,
        }

        # ---- Override RX : test de non-gruge ------------------------------
        # On copie cfg, on applique les overrides, et on passe cfg_rx à L13.
        # TX a déjà tourné avec cfg original ; RX voit cfg_rx. Si la chaîne
        # est réellement indépendante, override d'une clé crypto doit casser
        # le décodage.
        cfg_rx = dict(cfg)
        if args.rx_override:
            print('\n  🔧 Application des overrides RX (avant L13) :')
            for ov_str in args.rx_override:
                k, v = parse_override(ov_str)
                old = cfg_rx.get(k, '<absent>')
                cfg_rx[k] = v
                print(f'     cfg_rx["{k}"] : {old!r}  →  {v!r}')

        rt = L13_decap(cfg_rx,
                       x_rx=x_with_cp,
                       dci=dci,
                       expected_result=result,
                       snr_db=args.snr_db,
                       use_soft_demap=args.soft_demap,
                       verbose=args.verbose)

        n_on = L14_glyph(result, args.font)
        L15_oled(cfg, n_on)

        all_ok = rt.get('final', False)
        print('\n' + '=' * 72)
        print(f'  ✅ Trace complète : {a} + {b} = {result}')
        if all_ok:
            print(f'  🔍 Décodage RX indépendant : result_rx = {rt["result_rx"]} ≡ attendu ({result})')
        else:
            failed = [k for k, v in rt.items() if v is False]
            print(f'  ❌ Décodage RX a échoué : {failed}')
        print('=' * 72)

    if args.check:
        all_ok = rt.get('final', False)
        if all_ok:
            print(f'OK {a}+{b}={result} (result_rx={rt["result_rx"]} decoded independently)')
            sys.exit(0)
        else:
            failed = [k for k, v in rt.items() if v is False]
            print(f'FAIL {a}+{b}={result} layers={failed}')
            sys.exit(1)


if __name__ == '__main__':
    main()
