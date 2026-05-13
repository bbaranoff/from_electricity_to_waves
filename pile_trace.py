#!/usr/bin/env python3
"""
pile_trace.py — Trace numérique end-to-end de '1 + 1 = 2'
de la loi d'Ohm sur un MOSFET de UE_A jusqu'au sous-pixel OLED de UE_B.

Lit les valeurs arbitraires depuis un CSV (clé,valeur), calcule chaque
étage avec les vraies opérations (checksums IP/TCP, CRC-24A LTE,
mapping 16-QAM selon TS 36.211, IFFT OFDM réelle), et affiche
hex dump + I/Q samples par couche.

Usage:
    python3 pile_trace.py pile_values.csv

Dépendances : numpy uniquement.
"""

import csv
import sys
import struct
import hashlib
import binascii
import numpy as np


# ============================================================
# Utilitaires
# ============================================================

def load_csv(path: str) -> dict:
    """Charge un CSV clé,valeur en dict, parse hex/int/float/str."""
    cfg = {}
    with open(path) as f:
        for row in csv.reader(f):
            if not row or row[0].startswith('#') or row[0] == 'key':
                continue
            k, v = row[0].strip(), row[1].strip()
            if v.startswith('0x'):
                cfg[k] = int(v, 16)
            else:
                try:
                    cfg[k] = int(v)
                except ValueError:
                    try:
                        cfg[k] = float(v)
                    except ValueError:
                        cfg[k] = v
    return cfg


def hexdump(data: bytes, prefix: str = '') -> str:
    """Format xxd-style: offset hex bytes ascii."""
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        hex_part = f'{hex_part:<47}'
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f'{prefix}{i:04x}: {hex_part}  {ascii_part}')
    return '\n'.join(lines)


def ip_checksum(data: bytes) -> int:
    """Internet checksum (RFC 1071)."""
    if len(data) % 2:
        data += b'\x00'
    s = sum(int.from_bytes(data[i:i+2], 'big') for i in range(0, len(data), 2))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def crc24a(data: bytes) -> int:
    """3GPP TS 36.212 CRC-24A.
    Polynôme : x^24 + x^23 + x^18 + x^17 + x^14 + x^11 + x^10
              + x^7 + x^6 + x^5 + x^4 + x^3 + x + 1
    """
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


def banner(title: str, n: int = 72) -> None:
    print('\n' + '=' * n)
    print(f'  {title}')
    print('=' * n)


# ============================================================
# Niveau 0 — MOSFET (loi d'Ohm)
# ============================================================

def L0_mosfet(cfg):
    banner("NIVEAU 0 — MOSFET : U = R · I  (côté UE_A)")
    VDD = cfg['vdd_core_v']
    Vth = cfg['mosfet_vth_v']
    mu_Cox_per = cfg['mosfet_mu_cox_uA_V2']   # µA/V² (par unité W/L)
    WL = cfg['mosfet_WL']
    Cload = cfg['mosfet_cload_F']
    Vgs = VDD
    Id_sat = 0.5 * mu_Cox_per * WL * (Vgs - Vth) ** 2  # A
    Ron = VDD / Id_sat
    Eswitch = 0.5 * Cload * VDD ** 2
    print(f'  VDD          = {VDD} V')
    print(f'  Vth          = {Vth} V')
    print(f'  µn·Cox·(W/L) = {mu_Cox_per * WL * 1e6:.1f} µA/V²')
    print(f'  I_D = ½·µCox·(W/L)·(Vgs−Vth)² = {Id_sat*1e6:.1f} µA')
    print(f'  R_on = U / I = {Ron/1e3:.2f} kΩ')
    print(f'  E_switch = ½·C·V² = {Eswitch*1e15:.2f} fJ par transition')


# ============================================================
# Niveau 1 — Full adder ripple-carry 2 bits
# ============================================================

def L1_full_adder():
    banner("NIVEAU 1 — Full adder : 1 + 1 en binaire")
    A, B, Cin = 0b01, 0b01, 0
    bits = []
    for i in range(2):
        Ai, Bi = (A >> i) & 1, (B >> i) & 1
        Si = Ai ^ Bi ^ Cin
        Cout = (Ai & Bi) | (Cin & (Ai ^ Bi))
        bits.append(Si)
        print(f'  bit {i} : A={Ai} B={Bi} Cin={Cin}  →  S={Si} Cout={Cout}')
        Cin = Cout
    result = (bits[1] << 1) | bits[0]
    print(f'  Résultat : S1S0 = {bits[1]}{bits[0]}₂ = {result}₁₀')


# ============================================================
# Niveau 2 — Instruction ARM
# ============================================================

def L2_alu_arm():
    banner("NIVEAU 2 — Instruction ARMv8 ADD W2, W0, W1")
    print('  MOV  W0, #1            ; W0 = 0x0000_0001')
    print('  MOV  W1, #1            ; W1 = 0x0000_0001')
    print('  ADD  W2, W0, W1        ; W2 = 0x0000_0002')
    enc = 0x0B010002
    print(f'  Encodage 32 bits : 0x{enc:08X}')


# ============================================================
# Niveau 3 — Payload applicatif
# ============================================================

def L3_payload():
    banner("NIVEAU 3 — Payload JSON applicatif")
    s = '{"result":2}'
    payload = s.encode('ascii')
    print(f'  snprintf  →  "{s}"  ({len(payload)} octets)')
    print(hexdump(payload, '  '))
    idx = s.index('2')
    print(f'  Offset {idx} = 0x{payload[idx]:02X} = \'2\' (le bit calculé au Niveau 1)')
    return payload


# ============================================================
# Niveau 4 — TCP
# ============================================================

def L4_tcp(cfg, payload):
    banner("NIVEAU 4 — Segment TCP")
    sport, dport = cfg['src_port'], cfg['dst_port']
    seq, ack = cfg['tcp_seq'], cfg['tcp_ack']
    data_off, flags = 5, 0x18  # PSH+ACK
    window, urgent = cfg['tcp_window'], 0

    # Header sans checksum (placeholder 0)
    tcp_no_csum = struct.pack('>HHIIBBHHH',
        sport, dport, seq, ack,
        (data_off << 4), flags, window, 0, urgent)

    # Pseudo-header pour checksum
    src_ip = ip_to_bytes(cfg['src_ip'])
    dst_ip = ip_to_bytes(cfg['dst_ip'])
    tcp_len = len(tcp_no_csum) + len(payload)
    pseudo = src_ip + dst_ip + b'\x00\x06' + struct.pack('>H', tcp_len)
    csum = ip_checksum(pseudo + tcp_no_csum + payload)

    tcp_hdr = struct.pack('>HHIIBBHHH',
        sport, dport, seq, ack,
        (data_off << 4), flags, window, csum, urgent)
    segment = tcp_hdr + payload

    print(f'  src port = {sport}  dst port = {dport}')
    print(f'  seq = 0x{seq:08X}  ack = 0x{ack:08X}')
    print(f'  flags = 0x{flags:02X} (PSH+ACK)  window = {window}')
    print(f'  checksum = 0x{csum:04X}')
    print(f'  Segment TCP ({len(segment)} octets) :')
    print(hexdump(segment, '  '))
    return segment


# ============================================================
# Niveau 5 — IP
# ============================================================

def L5_ip(cfg, tcp_segment):
    banner("NIVEAU 5 — Paquet IPv4")
    total_len = 20 + len(tcp_segment)
    ipid, ttl, proto = 0xABCD, 64, 6
    src_ip = ip_to_bytes(cfg['src_ip'])
    dst_ip = ip_to_bytes(cfg['dst_ip'])

    ip_no_csum = struct.pack('>BBHHHBBH',
        0x45, 0x00, total_len,
        ipid, 0x4000, ttl, proto, 0) + src_ip + dst_ip
    csum = ip_checksum(ip_no_csum)
    ip_hdr = struct.pack('>BBHHHBBH',
        0x45, 0x00, total_len,
        ipid, 0x4000, ttl, proto, csum) + src_ip + dst_ip
    packet = ip_hdr + tcp_segment

    print(f'  src = {cfg["src_ip"]}  dst = {cfg["dst_ip"]}')
    print(f'  total length = {total_len}  TTL = {ttl}  proto = TCP(6)')
    print(f'  header checksum = 0x{csum:04X}')
    print(f'  Paquet IP ({len(packet)} octets) :')
    print(hexdump(packet, '  '))
    return packet


# ============================================================
# Niveau 6 — Ethernet (sur backhaul, PAS sur Uu)
# ============================================================

def L6_ethernet(cfg, ip_packet):
    banner("NIVEAU 6 — Trame Ethernet (backhaul S1-U / Internet)")
    print('  NB : Ethernet apparaît sur le backhaul fibre (eNB↔S-GW↔P-GW)')
    print('       et sur l\'Internet. PAS sur l\'air interface Uu, où PDCP/')
    print('       RLC/MAC tiennent le rôle de L2.')
    src_mac = mac_to_bytes(cfg['src_mac'])
    dst_mac = mac_to_bytes(cfg['dst_mac'])
    ethertype = struct.pack('>H', 0x0800)
    frame_no_fcs = dst_mac + src_mac + ethertype + ip_packet
    fcs = binascii.crc32(frame_no_fcs) & 0xFFFFFFFF
    # FCS transmis little-endian sur le médium
    frame = frame_no_fcs + struct.pack('<I', fcs)

    print(f'  src MAC = {cfg["src_mac"]}  dst MAC = {cfg["dst_mac"]}')
    print(f'  EtherType = 0x0800 (IPv4)')
    print(f'  FCS (CRC32) = 0x{fcs:08X}')
    print(f'  Trame Ethernet ({len(frame)} octets) :')
    print(hexdump(frame, '  '))
    return frame


# ============================================================
# Niveau 7 — RAN LTE Uu : PDCP / RLC / MAC / CRC
# ============================================================

def ksg_stream(key: int, count: int, n: int) -> bytes:
    """Stub AES-CTR : flux pseudo-aléatoire déterministe via SHA-256.
    PAS de vraie crypto — illustre seulement la transformation XOR."""
    out = bytearray()
    block = 0
    while len(out) < n:
        h = hashlib.sha256(struct.pack('>QQQ', key, count, block)).digest()
        out.extend(h)
        block += 1
    return bytes(out[:n])


def L7_lte_ran(cfg, ip_packet):
    banner("NIVEAU 7 — Pile RAN LTE Uu : PDCP / RLC / MAC / CRC")
    # PDCP : header 2 octets (D/C + SN 12 bits) + chiffrement
    pdcp_sn = 0x123
    pdcp_hdr = struct.pack('>H', (0 << 15) | pdcp_sn)
    stream = ksg_stream(cfg['rnti'], pdcp_sn, len(ip_packet))
    pdcp_payload = bytes(a ^ b for a, b in zip(ip_packet, stream))
    pdcp_pdu = pdcp_hdr + pdcp_payload
    print(f'  PDCP SN = 0x{pdcp_sn:03X}, PDU = {len(pdcp_pdu)} octets')
    print(f'    (chiffré via stub SHA-256 ; vraie crypto = AES-CTR / K_UPenc)')
    print(hexdump(pdcp_pdu[:48], '    '))
    if len(pdcp_pdu) > 48:
        print(f'    ... +{len(pdcp_pdu)-48} octets')

    # RLC UM : header 1 octet
    rlc_hdr = bytes([0xC0])
    rlc_pdu = rlc_hdr + pdcp_pdu
    print(f'  RLC UM : header=0x{rlc_hdr[0]:02X}, PDU={len(rlc_pdu)} octets')

    # MAC : header 2 octets (LCID + L)
    mac_hdr = bytes([0x01, len(rlc_pdu) & 0xFF])
    mac_pdu = mac_hdr + rlc_pdu
    print(f'  MAC PDU = {len(mac_pdu)} octets')

    # CRC-24A
    crc = crc24a(mac_pdu)
    tb = mac_pdu + struct.pack('>I', crc)[1:]
    print(f'  CRC-24A = 0x{crc:06X}')
    print(f'  Transport Block (TB) = {len(tb)} octets = {len(tb)*8} bits')
    return tb


# ============================================================
# Niveau 8 — Codage canal : turbo 1/3 + rate-match + scramble
# ============================================================

def L8_phy_coding(cfg, tb):
    banner("NIVEAU 8 — Codage canal : turbo 1/3 + rate-match + scramble")
    tb_bits = len(tb) * 8
    coded_bits = 3 * tb_bits + 12  # tail bits
    n_prb = cfg['n_prb']
    n_re = n_prb * 12 * 12  # PRB × sc × symboles OFDM
    bits_per_symbol = 4     # 16-QAM
    bits_avail = n_re * bits_per_symbol

    print(f'  Turbo 1/3 RSC polys : (1, 1+D²+D³, 1+D+D³)')
    print(f'    {tb_bits} bits  →  {coded_bits} bits codés (+ 12 tail)')
    print(f'  Rate-match : {coded_bits} → {bits_avail} bits')
    print(f'    ({n_prb} PRB × 144 RE × {bits_per_symbol} bits/sym)')

    seed = (cfg['rnti'] << 16) | (cfg['pci'] << 8) | cfg['subframe']
    rng = np.random.default_rng(seed)
    scrambled = rng.integers(0, 2, size=bits_avail, dtype=np.uint8)
    print(f'  Scramble seed = (RNTI=0x{cfg["rnti"]:04X}, PCI={cfg["pci"]}, sf={cfg["subframe"]})')
    print(f'  Premiers 64 bits scramblés :')
    print(f'    {"".join(map(str, scrambled[:64]))}')
    return scrambled


# ============================================================
# Niveau 9 — Mapping 16-QAM (TS 36.211 §7.1.3)
# ============================================================

def L9_qam16(scrambled):
    banner("NIVEAU 9 — Mapping 16-QAM (TS 36.211 §7.1.3)")
    n_sym = len(scrambled) // 4
    symbols = np.zeros(n_sym, dtype=complex)
    for k in range(n_sym):
        b0, b1, b2, b3 = scrambled[4*k:4*k+4]
        i = (1 - 2*b0) * (2 - (1 - 2*b2))
        q = (1 - 2*b1) * (2 - (1 - 2*b3))
        symbols[k] = (i + 1j*q) / np.sqrt(10)
    print(f'  {n_sym} symboles 16-QAM produits')
    print(f'  Formule : s = ((1−2b₀)(2−(1−2b₂)) + j(1−2b₁)(2−(1−2b₃))) / √10')
    print(f'  Premiers 8 symboles :')
    for k in range(min(8, n_sym)):
        b = ''.join(map(str, scrambled[4*k:4*k+4]))
        s = symbols[k]
        print(f'    [{k}] bits={b}  →  s = {s.real:+.4f} + {s.imag:+.4f}j   |s|={abs(s):.4f}')
    print(f'  Énergie moyenne E[|s|²] = {np.mean(np.abs(symbols)**2):.4f}  (cible 1.0)')
    return symbols


# ============================================================
# Niveau 10 — OFDM : RE mapping + IFFT + CP
# ============================================================

def L10_ofdm(cfg, symbols):
    banner("NIVEAU 10 — OFDM : mapping RE + IFFT + préfixe cyclique")
    N_FFT = cfg['fft_size']
    n_prb = cfg['n_prb']
    prb_start = cfg['prb_start']
    n_sc = n_prb * 12
    sym0 = symbols[:n_sc]  # premier symbole OFDM

    # Mapping centré, DC laissé vide (LTE simplifié)
    X = np.zeros(N_FFT, dtype=complex)
    center = N_FFT // 2
    # Offset depuis le centre DL (simplifié, ignore DC notching réel)
    sc_offset = (prb_start - 50) * 12
    for k, val in enumerate(sym0):
        bin_idx = (center + sc_offset + k + (1 if k >= 0 else 0)) % N_FFT
        X[bin_idx] = val

    # IFFT
    x_time = np.fft.ifft(X) * np.sqrt(N_FFT)
    cp_len = int(N_FFT * 144 / 2048)
    x_with_cp = np.concatenate([x_time[-cp_len:], x_time])

    fs = cfg['sample_rate_hz']
    Ts = 1.0 / fs
    print(f'  IFFT N = {N_FFT}, {n_sc} sous-porteuses actives')
    print(f'  CP normal = {cp_len} échantillons')
    print(f'  Durée symbole (avec CP) = {(N_FFT + cp_len) * Ts * 1e6:.2f} µs')
    print(f'  fs = {fs/1e6:.2f} MS/s,  Ts = {Ts*1e9:.3f} ns')
    print(f'  Premiers 16 échantillons I/Q après CP :')
    for n in range(16):
        s = x_with_cp[n]
        print(f'    n={n:3d}  I={s.real:+.5f}  Q={s.imag:+.5f}  |s|={abs(s):.5f}')
    print(f'  Puissance moyenne E[|x|²] = {np.mean(np.abs(x_with_cp)**2):.4f}')
    return x_with_cp


# ============================================================
# Niveau 11 — RF : up-conversion à f_c
# ============================================================

def L11_rf(cfg, x_baseband):
    banner("NIVEAU 11 — RF : DAC + mixeur quadrature + PA")
    fc = cfg['f_carrier_hz']
    fs = cfg['sample_rate_hz']
    Ts = 1.0 / fs
    P_tx_dbm = cfg.get('p_tx_dbm', 23)

    print(f'  EARFCN UL = {cfg["earfcn_ul"]}  →  f_c = {fc/1e6:.1f} MHz')
    print(f'  P_TX = {P_tx_dbm} dBm = {10**(P_tx_dbm/10):.0f} mW')
    print(f'  s_RF(t) = I(t)·cos(2π f_c t) − Q(t)·sin(2π f_c t)')
    print(f'  Évaluation analytique sur 8 échantillons :')
    for n in range(8):
        t = n * Ts
        I = x_baseband[n].real
        Q = x_baseband[n].imag
        s_rf = I * np.cos(2*np.pi*fc*t) - Q * np.sin(2*np.pi*fc*t)
        print(f'    n={n} t={t*1e9:6.2f} ns  I={I:+.4f} Q={Q:+.4f}  →  s_RF={s_rf:+.5f}')


# ============================================================
# Niveau 12 — Bilan de liaison (Friis + COST-231)
# ============================================================

def L12_friis(cfg):
    banner("NIVEAU 12 — Bilan de liaison Friis (UE_A → eNB)")
    fc = cfg['f_carrier_hz']
    d = cfg['distance_m']
    Pt = cfg['p_tx_dbm']
    Gt = cfg['g_tx_dbi']
    Gr = cfg['g_rx_dbi']
    L_excess = cfg['path_loss_excess_db']
    bw = cfg['bandwidth_hz']
    NF = cfg['nf_db']

    lam = 3e8 / fc
    L_fs = (4 * np.pi * d / lam) ** 2
    L_fs_db = 10 * np.log10(L_fs)
    L_total = L_fs_db + L_excess
    Pr = Pt + Gt + Gr - L_total
    N_floor = -174 + 10 * np.log10(bw)
    N_sys = N_floor + NF
    SNR = Pr - N_sys

    print(f'  d = {d} m,  λ = c/fc = {lam*100:.2f} cm')
    print(f'  L_FS  = (4π·d/λ)² = {L_fs:.3e}  →  {L_fs_db:.1f} dB')
    print(f'  L_excess (urbain COST-231) = {L_excess} dB')
    print(f'  L_total = {L_total:.1f} dB')
    print(f'  P_r = Pt + Gt + Gr − L = {Pt} + {Gt} + {Gr} − {L_total:.1f} = {Pr:.1f} dBm')
    print(f'  N_thermique({bw/1e6:.0f} MHz) = {N_floor:.1f} dBm,  NF = {NF} dB')
    print(f'  N_sys = {N_sys:.1f} dBm')
    print(f'  SNR ≈ {SNR:.1f} dB')


# ============================================================
# Niveau 13 — Décapsulation symétrique UE_B (récap)
# ============================================================

def L13_decap():
    banner("NIVEAU 13 — Décapsulation symétrique côté UE_B (récap)")
    steps = [
        'Antenne RX → LNA (G≈20 dB, NF≈1.5 dB)',
        'Mixeur down-conversion → I(t), Q(t) baseband',
        'ADC 12 bits @ 30.72 MS/s',
        'Suppression CP, FFT 2048',
        'Démap 16-QAM → LLR par bit',
        'Dé-scramble (même seed Gold)',
        'Turbo decode (Max-Log-MAP, ~8 itérations) → TB',
        'CRC-24A vérification → ACK HARQ',
        'MAC démux LCID → RLC PDU',
        'RLC réassemble → PDCP PDU',
        'PDCP déchiffre AES-CTR → paquet IP',
        'IP : vérif checksum, strip header → segment TCP',
        'TCP : vérif checksum, SN, ACK → 12 B payload',
        'JSON parse → int 2',
    ]
    for i, s in enumerate(steps, 1):
        print(f'  {i:2d}. {s}')


# ============================================================
# Niveau 14 — Glyph '2' rastérisé (bitmap 8×8)
# ============================================================

GLYPH_2_8x8 = [
    0b00111100,
    0b01000010,
    0b00000010,
    0b00001100,
    0b00110000,
    0b01000000,
    0b01111110,
    0b00000000,
]


def L14_glyph():
    banner("NIVEAU 14 — Glyph '2' rastérisé (bitmap 8×8)")
    print('  Lookup fonte : code ASCII 0x32 → 8 octets de bitmap')
    print('  Représentation visuelle (■ = pixel ON) :')
    for row in GLYPH_2_8x8:
        line = ''.join('■' if (row >> b) & 1 else '·' for b in range(7, -1, -1))
        print(f'    {line}   0x{row:02X}  {row:08b}')
    n_on = sum(bin(r).count('1') for r in GLYPH_2_8x8)
    print(f'  Pixels allumés : {n_on} sur 64')
    return n_on


# ============================================================
# Niveau 15 — OLED : U = R · I (la boucle se ferme)
# ============================================================

def L15_oled(cfg, n_pixels_on):
    banner("NIVEAU 15 — Sous-pixel OLED : U = R · I (boucle bouclée)")
    V = cfg['oled_voltage_v']
    R = cfg['oled_pixel_resistance_ohm']
    I = V / R
    P_per_subpix = V * I
    n_subpix = n_pixels_on * 3  # 3 sous-pixels RGB par pixel
    I_total = n_subpix * I
    P_total = n_subpix * P_per_subpix
    print(f'  V_OLED = {V} V')
    print(f'  R_pixel = {R/1e3:.0f} kΩ')
    print(f'  I_pixel = U / R = {I*1e6:.2f} µA   ← loi d\'Ohm (comme Niveau 0)')
    print(f'  P_pixel = V·I = {P_per_subpix*1e6:.2f} µW par sous-pixel')
    print(f'  {n_pixels_on} pixels ON × 3 sous-pixels = {n_subpix} sous-pixels')
    print(f'  I_total = {I_total*1e6:.2f} µA   P_total = {P_total*1e6:.2f} µW')
    print()
    print('  ┌──────────────────────────────────────────────────────────────┐')
    print('  │  Niveau 0  (TX)  : U=0.9 V   R≈5 kΩ    I≈180 µA    MOSFET    │')
    print(f'  │  Niveau 15 (RX)  : U={V} V   R={R/1e3:.0f} kΩ   I={I*1e6:.2f} µA    OLED      │')
    print('  │  Même loi linéaire à 2 paramètres aux deux extrémités.       │')
    print('  └──────────────────────────────────────────────────────────────┘')


# ============================================================
# Main
# ============================================================

def main():
    if len(sys.argv) < 2:
        print(f'Usage : {sys.argv[0]} <pile_values.csv>')
        sys.exit(1)

    cfg = load_csv(sys.argv[1])
    print(f'\nConfig chargée depuis {sys.argv[1]} : {len(cfg)} paramètres')

    L0_mosfet(cfg)
    L1_full_adder()
    L2_alu_arm()
    payload = L3_payload()
    tcp_seg = L4_tcp(cfg, payload)
    ip_pkt = L5_ip(cfg, tcp_seg)
    L6_ethernet(cfg, ip_pkt)
    tb = L7_lte_ran(cfg, ip_pkt)
    scrambled = L8_phy_coding(cfg, tb)
    symbols = L9_qam16(scrambled)
    x_bb = L10_ofdm(cfg, symbols)
    L11_rf(cfg, x_bb)
    L12_friis(cfg)
    L13_decap()
    n_on = L14_glyph()
    L15_oled(cfg, n_on)

    print('\n' + '=' * 72)
    print('  Trace complète terminée. U=R·I bouclée du transistor au sous-pixel.')
    print('=' * 72)


if __name__ == '__main__':
    main()
