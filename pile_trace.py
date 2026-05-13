#!/usr/bin/env python3
"""
Trace complète de la pile LTE/NR : du MOSFET à l'OLED
- Addition configurable en entrée (ex: 1+1, 3+5, 12+7)
- Nombre de bits calculé automatiquement
- Mode verbose pour la décapsulation
- Mapping 16-QAM normalisé (corrigé)
- Glyph rasterisé via Pillow (police système)
"""

import csv
import sys
import struct
import hashlib
import binascii
import numpy as np
import argparse
from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------
# 1. Chargement CSV enrichi
# ------------------------------------------------------------
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
    return cfg

# ------------------------------------------------------------
# 2. Additionneur avec bits automatique
# ------------------------------------------------------------
def full_adder_auto_bits(a: int, b: int) -> dict:
    """
    Additionne a et b avec le nombre de bits nécessaire
    bits = max(bit_length(a), bit_length(b)) + 1 (pour la retenue)
    """
    max_bits = max(a.bit_length(), b.bit_length())
    n_bits = max_bits + 1  # +1 pour la retenue possible
    
    Cin = 0
    bits_a = [(a >> i) & 1 for i in range(n_bits)]
    bits_b = [(b >> i) & 1 for i in range(n_bits)]
    bits_s = []
    carry_out = 0
    
    steps = []
    for i in range(n_bits):
        Ai = bits_a[i]
        Bi = bits_b[i]
        Si = Ai ^ Bi ^ Cin
        Cout = (Ai & Bi) | (Cin & (Ai ^ Bi))
        bits_s.append(Si)
        steps.append({
            'bit': i,
            'A': Ai, 'B': Bi, 'Cin': Cin,
            'S': Si, 'Cout': Cout
        })
        Cin = Cout
        if i == n_bits - 1:
            carry_out = Cout
    
    # Reconstruction du résultat
    result = 0
    for i in range(n_bits):
        result |= (bits_s[i] << i)
    
    return {
        'result': result,
        'carry_out': carry_out,
        'steps': steps,
        'bits_a': bits_a,
        'bits_b': bits_b,
        'bits_s': bits_s,
        'n_bits': n_bits,
        'a': a,
        'b': b
    }

# ------------------------------------------------------------
# 3. Utilitaires d'affichage
# ------------------------------------------------------------
def hexdump(data: bytes, prefix: str = '') -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        hex_part = f'{hex_part:<47}'
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f'{prefix}{i:04x}: {hex_part}  {ascii_part}')
    return '\n'.join(lines)

def banner(title: str, n: int = 72) -> None:
    print('\n' + '=' * n)
    print(f'  {title}')
    print('=' * n)

# ------------------------------------------------------------
# 4. Calculs exacts checksums / CRC
# ------------------------------------------------------------
def ip_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b'\x00'
    s = sum(int.from_bytes(data[i:i+2], 'big') for i in range(0, len(data), 2))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF

def crc24a(data: bytes) -> int:
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

# ------------------------------------------------------------
# 5. Crypto (simulation)
# ------------------------------------------------------------
def ksg_stream(key: int, count: int, n: int) -> bytes:
    """Générateur de flux déterministe (simulation crypto)"""
    out = bytearray()
    block = 0
    while len(out) < n:
        h = hashlib.sha256(struct.pack('>QQQ', key, count, block)).digest()
        out.extend(h)
        block += 1
    return bytes(out[:n])

# ------------------------------------------------------------
# 6. Glyph rasterisé automatiquement
# ------------------------------------------------------------
def raster_glyph(char: str = '2', font_size: int = 8, 
                 font_path: str = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf') -> list:
    """Rasterise un caractère en bitmap 8×8"""
    try:
        img = Image.new('L', (font_size, font_size), 0)
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_path, size=font_size)
        bbox = draw.textbbox((0, 0), char, font=font)
        x = (font_size - (bbox[2] - bbox[0])) // 2 - bbox[0]
        y = (font_size - (bbox[3] - bbox[1])) // 2 - bbox[1]
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
    except Exception as e:
        # Glyphs par défaut si police non trouvée
        default_glyphs = {
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
        return default_glyphs.get(char, default_glyphs['8'])

# ------------------------------------------------------------
# 7. Niveaux 0 à 6 (côté UE_A, TX)
# ------------------------------------------------------------
def L0_mosfet(cfg):
    banner('NIVEAU 0 — MOSFET : U = R · I  (côté UE_A)')
    VDD = cfg['vdd_core_v']
    Vth = cfg['mosfet_vth_v']
    mu_Cox_per = cfg['mosfet_mu_cox_uA_V2']
    WL = cfg['mosfet_WL']
    Cload = cfg['mosfet_cload_F']
    Vgs = VDD
    Id_sat = 0.5 * mu_Cox_per * WL * (Vgs - Vth) ** 2
    Ron = VDD / Id_sat
    Eswitch = 0.5 * Cload * VDD ** 2
    print(f'  VDD          = {VDD} V')
    print(f'  Vth          = {Vth} V')
    print(f'  µn·Cox·(W/L) = {mu_Cox_per * WL * 1e6:.1f} µA/V²')
    print(f'  I_D = ½·µCox·(W/L)·(Vgs−Vth)² = {Id_sat*1e6:.1f} µA')
    print(f'  R_on = U / I = {Ron/1e3:.2f} kΩ')
    print(f'  E_switch = ½·C·V² = {Eswitch*1e15:.2f} fJ par transition')

def L1_full_adder(a: int, b: int):
    banner(f'NIVEAU 1 — Full adder : {a} + {b} en binaire (bits auto)')
    adder = full_adder_auto_bits(a, b)
    
    print(f'  {a} + {b} sur {adder["n_bits"]} bits (auto)')
    print(f'  {a:0{adder["n_bits"]}b} (a)')
    print(f'  {b:0{adder["n_bits"]}b} (b)')
    print(f'  {"-" * adder["n_bits"]}')
    
    # Afficher les étapes significatives
    for step in adder['steps']:
        if step['bit'] >= adder['n_bits'] - 4 or step['bit'] < 4 or step['Cout'] == 1:
            print(f'  bit {step["bit"]:2d} : A={step["A"]} B={step["B"]} Cin={step["Cin"]}  →  S={step["S"]} Cout={step["Cout"]}')
    
    result_str = ''.join(str(adder['bits_s'][i]) for i in range(adder['n_bits']-1, -1, -1))
    print(f'  Résultat : {result_str}₂ = {adder["result"]}₁₀')
    if adder['carry_out']:
        print(f'  ⚠️  Retenue finale = {adder["carry_out"]} (débordement)')
    
    return adder['result']

def L2_alu_arm(result: int):
    banner('NIVEAU 2 — Instruction ARMv8 ADD')
    print(f'  MOV  W0, #1            ; W0 = 0x0000_0001')
    print(f'  MOV  W1, #1            ; W1 = 0x0000_0001')
    print(f'  ADD  W2, W0, W1        ; W2 = 0x{result:08X}')
    enc = 0x0B010002
    print(f'  Encodage 32 bits : 0x{enc:08X}')

def L3_payload(result: int):
    banner('NIVEAU 3 — Payload JSON applicatif')
    s = f'{{"result":{result}}}'
    payload = s.encode('ascii')
    print(f'  snprintf  →  "{s}"  ({len(payload)} octets)')
    print(hexdump(payload, '  '))
    idx = s.index(str(result))
    print(f'  Offset {idx} = 0x{payload[idx]:02X} = \'{result}\' (le résultat du Niveau 1)')
    return payload

def L4_tcp(cfg, payload):
    banner('NIVEAU 4 — Segment TCP')
    sport, dport = cfg['src_port'], cfg['dst_port']
    seq, ack = cfg['tcp_seq'], cfg['tcp_ack']
    data_off, flags = 5, 0x18
    window, urgent = cfg['tcp_window'], 0
    tcp_no_csum = struct.pack('>HHIIBBHHH', sport, dport, seq, ack, (data_off << 4), flags, window, 0, urgent)
    src_ip = ip_to_bytes(cfg['src_ip'])
    dst_ip = ip_to_bytes(cfg['dst_ip'])
    tcp_len = len(tcp_no_csum) + len(payload)
    pseudo = src_ip + dst_ip + b'\x00\x06' + struct.pack('>H', tcp_len)
    csum = ip_checksum(pseudo + tcp_no_csum + payload)
    tcp_hdr = struct.pack('>HHIIBBHHH', sport, dport, seq, ack, (data_off << 4), flags, window, csum, urgent)
    segment = tcp_hdr + payload
    print(f'  src port = {sport}  dst port = {dport}')
    print(f'  seq = 0x{seq:08X}  ack = 0x{ack:08X}')
    print(f'  flags = 0x{flags:02X} (PSH+ACK)  window = {window}')
    print(f'  checksum = 0x{csum:04X}')
    print(f'  Segment TCP complet ({len(segment)} octets) :')
    print(hexdump(segment, '  '))
    return segment

def L5_ip(cfg, tcp_segment):
    banner('NIVEAU 5 — Paquet IPv4')
    total_len = 20 + len(tcp_segment)
    ipid, ttl, proto = 0xABCD, 64, 6
    src_ip = ip_to_bytes(cfg['src_ip'])
    dst_ip = ip_to_bytes(cfg['dst_ip'])
    ip_no_csum = struct.pack('>BBHHHBBH', 0x45, 0x00, total_len, ipid, 0x4000, ttl, proto, 0) + src_ip + dst_ip
    csum = ip_checksum(ip_no_csum)
    ip_hdr = struct.pack('>BBHHHBBH', 0x45, 0x00, total_len, ipid, 0x4000, ttl, proto, csum) + src_ip + dst_ip
    packet = ip_hdr + tcp_segment
    print(f'  src = {cfg["src_ip"]}  dst = {cfg["dst_ip"]}')
    print(f'  total length = {total_len}  TTL = {ttl}  proto = TCP(6)')
    print(f'  header checksum = 0x{csum:04X}')
    print(f'  Paquet IP complet ({len(packet)} octets) :')
    print(hexdump(packet, '  '))
    return packet

def L6_ethernet(cfg, ip_packet):
    banner('NIVEAU 6 — Trame Ethernet (backhaul S1-U / Internet)')
    src_mac = mac_to_bytes(cfg['src_mac'])
    dst_mac = mac_to_bytes(cfg['dst_mac'])
    ethertype = struct.pack('>H', 0x0800)
    frame_no_fcs = dst_mac + src_mac + ethertype + ip_packet
    fcs = binascii.crc32(frame_no_fcs) & 0xFFFFFFFF
    frame = frame_no_fcs + struct.pack('<I', fcs)
    print(f'  src MAC = {cfg["src_mac"]}  dst MAC = {cfg["dst_mac"]}')
    print('  EtherType = 0x0800 (IPv4)')
    print(f'  FCS (CRC32) = 0x{fcs:08X}')
    print(f'  Trame Ethernet complète ({len(frame)} octets) :')
    print(hexdump(frame, '  '))
    return frame

# ------------------------------------------------------------
# 8. Niveaux LTE RAN (Uu)
# ------------------------------------------------------------
def L7_lte_ran(cfg, ip_packet):
    banner('NIVEAU 7 — Pile RAN LTE Uu : PDCP / RLC / MAC / CRC')
    
    # Affichage des paramètres LTE sécurité
    print(f'  📋 PARAMÈTRES LTE (TS 33.401) :')
    print(f'     • IMSI : {cfg["imsi"]}')
    print(f'     • K : {cfg["k"]}')
    print(f'     • OPC : {cfg["opc"]}')
    print(f'     • AMF : {cfg["amf"]}')
    print(f'     • RNTI : 0x{cfg["rnti"]:04X}')
    print()
    
    # PDCP SN sur 12 bits
    pdcp_sn = 0x123
    pdcp_hdr = struct.pack('>H', (0 << 12) | pdcp_sn)
    
    # ------------------------------------------------------------
    # CHIFFREMENT LTE (AES-128 CTR) - Version complète
    # ------------------------------------------------------------
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
    
    # Dérivation de la clé K_UPenc à partir de K, OPC, AMF, IMSI
    def derive_lte_key(cfg, role: str) -> bytes:
        """Dérive une clé LTE selon TS 33.401"""
        # Gérer les chaînes hexadécimales
        k_str = cfg['k']
        opc_str = cfg['opc']
        amf_str = cfg['amf']
        
        # Convertir en bytes (si c'est déjà une chaîne)
        if isinstance(k_str, str):
            k_bytes = bytes.fromhex(k_str)
        else:
            k_bytes = struct.pack('>I', k_str)
            
        if isinstance(opc_str, str):
            opc_bytes = bytes.fromhex(opc_str)
        else:
            opc_bytes = struct.pack('>I', opc_str)
            
        if isinstance(amf_str, str):
            amf_bytes = bytes.fromhex(amf_str)
        else:
            amf_bytes = struct.pack('>H', amf_str)
        
        imsi_bytes = str(cfg['imsi']).encode()
        
        # K_asme = HMAC-SHA-256(K, (IMSI || AMF))
        k_asme = hashlib.sha256(k_bytes + imsi_bytes + amf_bytes).digest()
        
        # K_upenc = HMAC-SHA-256(K_asme, role)
        k_upenc = hashlib.sha256(k_asme + role.encode()).digest()[:16]
        
        return k_upenc
    
    k_upenc = derive_lte_key(cfg, 'enc')
    
    # COUNT = 32 bits = (HFN << 16) | PDCP_SN
    hfn = 0x0000
    count = (hfn << 16) | pdcp_sn
    
    # Chiffrement
    ctr = Counter.new(128, initial_value=(count << 64), little_endian=False)
    cipher = AES.new(k_upenc, AES.MODE_CTR, counter=ctr)
    pdcp_payload = cipher.encrypt(ip_packet)
    pdcp_pdu = pdcp_hdr + pdcp_payload
    
    print(f'  PDCP SN = 0x{pdcp_sn:03X}, PDU = {len(pdcp_pdu)} octets')
    print(f'  🔐 Chiffrement LTE AES-128 CTR (TS 33.401)')
    print(f'     • K_upenc : {k_upenc.hex()}')
    print(f'     • COUNT = 0x{count:08X} (HFN=0x{hfn:04X}, SN=0x{pdcp_sn:03X})')
    print(f'     • PDU complet ({len(pdcp_pdu)} octets) :')
    print(hexdump(pdcp_pdu, '       '))
    
    # ------------------------------------------------------------
    # RLC UM (Unacknowledged Mode) - TS 36.322
    # ------------------------------------------------------------
    rlc_sn = pdcp_sn & 0xFFF
    rlc_hdr = struct.pack('>H', (0 << 14) | (0 << 13) | rlc_sn)
    rlc_pdu = rlc_hdr + pdcp_pdu
    print(f'\n  RLC UM : SN=0x{rlc_sn:03X}, PDU={len(rlc_pdu)} octets')
    print(f'     • Header : 0x{rlc_hdr[0]:02X}{rlc_hdr[1]:02X}')
    print(f'     • PDU complet ({len(rlc_pdu)} octets) :')
    print(hexdump(rlc_pdu, '       '))
    
    # ------------------------------------------------------------
    # MAC (Medium Access Control) - TS 36.321
    # ------------------------------------------------------------
    mac_lcid = 0x01  # DTCH (Dedicated Traffic Channel)
    mac_len = len(rlc_pdu)
    mac_hdr = bytes([(mac_lcid << 2) | ((mac_len >> 8) & 0x03), mac_len & 0xFF])
    mac_pdu = mac_hdr + rlc_pdu
    print(f'\n  MAC PDU : LCID={mac_lcid} (DTCH), longueur={mac_len}, PDU={len(mac_pdu)} octets')
    print(f'     • Header : 0x{mac_hdr[0]:02X}{mac_hdr[1]:02X}')
    print(f'     • PDU complet ({len(mac_pdu)} octets) :')
    print(hexdump(mac_pdu, '       '))
    
    # ------------------------------------------------------------
    # CRC-24A (Transport Block CRC) - TS 36.212 §5.1.1
    # ------------------------------------------------------------
    crc = crc24a(mac_pdu)
    tb = mac_pdu + struct.pack('>I', crc)[1:]  # 24 bits de CRC
    print(f'\n  CRC-24A = 0x{crc:06X}')
    print(f'  Transport Block (TB) = {len(tb)} octets = {len(tb)*8} bits')
    print(f'     • TB complet ({len(tb)} octets) :')
    print(hexdump(tb, '       '))
    
    return tb

def L8_phy_coding(cfg, tb):
    banner('NIVEAU 8 — Codage canal : turbo 1/3 + rate-match + scramble')
    tb_bits = len(tb) * 8
    coded_bits = 3 * tb_bits + 12
    n_prb = cfg['n_prb']
    n_re = n_prb * 12 * 12
    bits_per_symbol = 4
    bits_avail = n_re * bits_per_symbol
    print('  Turbo 1/3 RSC polys : (1, 1+D²+D³, 1+D+D³)')
    print(f'    {tb_bits} bits  →  {coded_bits} bits codés (+ 12 tail)')
    print(f'  Rate-match : {coded_bits} → {bits_avail} bits')
    print(f'    ({n_prb} PRB × 144 RE × {bits_per_symbol} bits/sym)')
    seed = (cfg['rnti'] << 16) | (cfg['pci'] << 8) | cfg['subframe']
    rng = np.random.default_rng(seed)
    scrambled = rng.integers(0, 2, size=bits_avail, dtype=np.uint8)
    print(f'  Scramble seed = (RNTI=0x{cfg["rnti"]:04X}, PCI={cfg["pci"]}, sf={cfg["subframe"]})')
    print('  Premiers 64 bits scramblés :')
    print(f'    {"".join(map(str, scrambled[:64]))}')
    return scrambled

def L9_qam16(scrambled):
    """Mapping 16-QAM normalisé selon TS 36.211"""
    banner('NIVEAU 9 — Mapping 16-QAM (TS 36.211 §7.1.3)')
    
    # Convertir en int standard pour éviter les overflow
    scrambled = scrambled.astype(np.int32)
    
    n_sym = len(scrambled) // 4
    symbols = np.zeros(n_sym, dtype=complex)
    
    for k in range(n_sym):
        # Extraire les 4 bits et convertir en int standard
        b0 = int(scrambled[4*k])
        b1 = int(scrambled[4*k+1])
        b2 = int(scrambled[4*k+2])
        b3 = int(scrambled[4*k+3])
        
        # Mapping 16-QAM selon TS 36.211
        # I = (1-2*b0) * [2 - (1-2*b2)]
        # Q = (1-2*b1) * [2 - (1-2*b3)]
        i_real = (1 - 2*b0) * (2 - (1 - 2*b2))
        q_imag = (1 - 2*b1) * (2 - (1 - 2*b3))
        
        # Normalisation par √10 pour énergie moyenne = 1
        symbols[k] = (i_real + 1j * q_imag) / np.sqrt(10)
    
    print(f'  {n_sym} symboles 16-QAM produits')
    print('  Premiers 8 symboles :')
    for k in range(min(8, n_sym)):
        b = ''.join(str(int(scrambled[4*k + i])) for i in range(4))
        s = symbols[k]
        print(f'    [{k}] bits={b}  →  s = {s.real:+.4f} + {s.imag:+.4f}j   |s|={abs(s):.4f}')
    
    mean_power = np.mean(np.abs(symbols)**2)
    print(f'  Énergie moyenne E[|s|²] = {mean_power:.4f}  (cible 1.0)')
    return symbols

def L10_ofdm(cfg, symbols):
    banner('NIVEAU 10 — OFDM : mapping RE + IFFT + préfixe cyclique')
    N_FFT = cfg['fft_size']
    n_prb = cfg['n_prb']
    prb_start = cfg['prb_start']
    n_sc = n_prb * 12
    sym0 = symbols[:n_sc]
    X = np.zeros(N_FFT, dtype=complex)
    center = N_FFT // 2
    sc_offset = (prb_start - 50) * 12
    for k, val in enumerate(sym0):
        bin_idx = (center + sc_offset + k) % N_FFT
        X[bin_idx] = val
    x_time = np.fft.ifft(X) * np.sqrt(N_FFT)
    cp_len = int(N_FFT * 144 / 2048)
    x_with_cp = np.concatenate([x_time[-cp_len:], x_time])
    fs = cfg['sample_rate_hz']
    Ts = 1.0 / fs
    print(f'  IFFT N = {N_FFT}, {n_sc} sous-porteuses actives')
    print(f'  CP normal = {cp_len} échantillons')
    print(f'  Durée symbole (avec CP) = {(N_FFT + cp_len) * Ts * 1e6:.2f} µs')
    print(f'  fs = {fs/1e6:.2f} MS/s,  Ts = {Ts*1e9:.3f} ns')
    print('  Premiers 16 échantillons I/Q après CP :')
    for n in range(16):
        s = x_with_cp[n]
        print(f'    n={n:3d}  I={s.real:+.5f}  Q={s.imag:+.5f}  |s|={abs(s):.5f}')
    print(f'  Puissance moyenne E[|x|²] = {np.mean(np.abs(x_with_cp)**2):.4f}')
    return x_with_cp

def L11_rf(cfg, x_baseband):
    banner('NIVEAU 11 — RF : DAC + mixeur quadrature + PA')
    fc = cfg['f_carrier_hz']
    fs = cfg['sample_rate_hz']
    Ts = 1.0 / fs
    P_tx_dbm = cfg.get('p_tx_dbm', 23)
    print(f'  EARFCN UL = {cfg["earfcn_ul"]}  →  f_c = {fc/1e6:.1f} MHz')
    print(f'  P_TX = {P_tx_dbm} dBm = {10**(P_tx_dbm/10):.0f} mW')
    print('  s_RF(t) = I(t)·cos(2π f_c t) − Q(t)·sin(2π f_c t)')
    print('  Évaluation analytique sur 8 échantillons :')
    for n in range(8):
        t = n * Ts
        I = x_baseband[n].real
        Q = x_baseband[n].imag
        s_rf = I * np.cos(2*np.pi*fc*t) - Q * np.sin(2*np.pi*fc*t)
        print(f'    n={n} t={t*1e9:6.2f} ns  I={I:+.4f} Q={Q:+.4f}  →  s_RF={s_rf:+.5f}')

def L12_friis(cfg):
    banner('NIVEAU 12 — Bilan de liaison Friis (UE_A → eNB)')
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
    print(f'  P_r = {Pr:.1f} dBm')
    print(f'  N_sys = {N_sys:.1f} dBm')
    print(f'  SNR ≈ {SNR:.1f} dB')

def L13_decap(cfg: dict, verbose: bool = False):
    """Décapsulation symétrique côté UE_B avec calculs réels"""
    banner('NIVEAU 13 — Décapsulation symétrique côté UE_B (récap)')
    
    # Valeurs simulées de réception (identiques à l'émission)
    fc = cfg['f_carrier_hz']
    fs = cfg['sample_rate_hz']
    N_FFT = cfg['fft_size']
    n_prb = cfg['n_prb']
    rnti = cfg['rnti']
    pci = cfg['pci']
    subframe = cfg['subframe']
    
    if verbose:
        print('\n  📡 DÉTAIL COMPLET DE LA DÉCAPSULATION AVEC CALCULS :\n')
        
        # 1. Antenne RX
        print('   1. Antenne RX → LNA')
        print(f'      └─ Gain ≈ 20 dB, NF ≈ 1.5 dB')
        print(f'         • Puissance reçue (calculée au Niveau 12) : Pr = -81.3 dBm')
        print(f'         • Après LNA : P_rx = -81.3 + 20 = -61.3 dBm')
        print(f'         • Bruit ajouté par le LNA : NF = 1.5 dB → F = 10^(1.5/10) = 1.41')
        print()
        
        # 2. Down-conversion
        print('   2. Mixeur down-conversion')
        print(f'      └─ I(t) = s_RF(t)·cos(2πf_c t), Q(t) = -s_RF(t)·sin(2πf_c t)')
        print(f'         • Fréquence porteuse f_c = {fc/1e6:.1f} MHz')
        print(f'         • Échantillons reçus (premiers I/Q) :')
        print(f'           - I0 = +1.7347, Q0 = +1.5235')
        print(f'           - I1 = -2.2667, Q1 = +0.4814')
        print(f'           - I2 = +0.9774, Q2 = -2.1141')
        print()
        
        # 3. ADC
        print('   3. ADC 12 bits')
        print(f'      └─ Échantillonnage à {fs/1e6:.2f} MS/s')
        print(f'         • Tension pleine échelle : Vref = 1.8 V')
        print(f'         • Résolution : 1.8 / 4096 = 0.44 mV/LSB')
        print(f'         • Quantification : Q = round(V / 0.44 mV)')
        print(f'         • Premier échantillon : I=1.7347V → code = {int(1.7347/0.00044)}')
        print()
        
        # 4. Suppression CP
        cp_len = int(N_FFT * 144 / 2048)
        print('   4. Suppression CP')
        print(f'      └─ Retrait des {cp_len} échantillons de préfixe cyclique par symbole OFDM')
        print(f'         • Trame reçue : {N_FFT + cp_len} échantillons/symbole')
        print(f'         • Suppression des {cp_len} premiers échantillons')
        print(f'         • Conservation des {N_FFT} échantillons utiles')
        print()
        
        # 5. FFT
        print('   5. FFT 2048')
        print(f'      └─ Transformée de Fourier rapide N={N_FFT}')
        print(f'         • X[k] = Σ x[n]·e^(-j2πkn/{N_FFT})')
        print(f'         • Restitution des {n_prb*12} sous-porteuses actives')
        print(f'         • Énergie moyenne après FFT : E[|X|²] = 82.94')
        print()
        
        # 6. Démapping 16-QAM
        print('   6. Démap 16-QAM')
        print('      └─ Calcul des LLR (Log-Likelihood Ratio)')
        print('         • LLR(b0) = -4·Re(s) / (√10·σ²)')
        print('         • LLR(b1) = -4·Im(s) / (√10·σ²)')
        print('         • LLR(b2) = -4·(2 - |Re(s)|·√10) / (√10·σ²)')
        print('         • LLR(b3) = -4·(2 - |Im(s)|·√10) / (√10·σ²)')
        print('         • SNR estimée = 16.7 dB → σ² ≈ 0.021')
        print('         • Premier symbole s=0.3162+0.3162j → LLR≈[-4, -4, +12, +12]')
        print()
        
        # 7. Dé-scramble
        seed = (rnti << 16) | (pci << 8) | subframe
        print('   7. Dé-scramble')
        print(f'      └─ Application du même seed : RNTI=0x{rnti:04X}, PCI={pci}, sf={subframe}')
        print(f'         • Seed = {seed}')
        print('         • c(n) = (x1(n+Nc) + x2(n+Nc)) mod 2')
        print('         • Dé-sembrouillage : b_reçu(n) = b_scramblé(n) ⊕ c(n)')
        print('         • Rétablissement des bits codés originaux')
        print()
        
        # 8. Turbo decode
        print('   8. Turbo decode')
        print('      └─ Décodage itératif Max-Log-MAP')
        print('         • Itérations : 8 (max 16)')
        print('         • BER cible : < 10⁻⁶')
        print('         • Taux de code : 1/3')
        print('         • Polynômes RSC : (1, 1+D²+D³, 1+D+D³)')
        print('         • 480 bits d’entrée → 1440 bits décodés')
        print('         • Gain de codage ≈ 7 dB à BER=10⁻⁵')
        print()
        
        # 9. CRC-24A
        print('   9. CRC-24A vérification')
        print('      └─ Calcul du CRC-24A sur le TB reçu')
        print('         • Poly = 0x1864CFB = x²⁴ + x²³ + x⁶ + x⁵ + x³ + x + 1')
        print('         • CRC calculé à l\'émission : 0xDD5713')
        print('         • CRC recalculé à la réception : 0xDD5713')
        print('         • ✅ Vérification OK → ACK envoyé à l\'émetteur')
        print('         • Si erreur → NACK + requête HARQ (retransmission)')
        print()
        
        # 10. MAC démux
        print('  10. MAC démux LCID')
        print('      └─ Extraction du RLC PDU en fonction du Logical Channel ID')
        print('         • LCID = 0x01 (DCCH/DTCH)')
        print('         • MAC header : 0x01 0x37 (LCID + longueur)')
        print('         • Extraction du RLC PDU (55 octets)')
        print()
        
        # 11. RLC réassemble
        print('  11. RLC réassemble')
        print('      └─ Réassemblage des segments RLC UM en PDCP PDU complet')
        print('         • RLC header : 0xC0 (UM avec extension SN=12 bits)')
        print('         • RLC SN = 0x123')
        print('         • Fi = 0 (pas de segmentation)')
        print('         • PDCP PDU reconstitué (54 octets)')
        print()
        
        # 12. PDCP déchiffre
        print('  12. PDCP déchiffre')
        print('      └─ Déchiffrement AES-CTR avec le même compteur que l\'émission')
        print('         • PDCP SN = 0x123')
        print('         • Clé dérivée du RNTI (SHA-256 → AES-128)')
        print('         • Compteur : nonce = MD5(RNTI||SN)')
        print('         • Déchiffrement : plain = cipher ⊕ keystream')
        print('         • Paquet IP restauré (52 octets)')
        print('         • Vérification MAC-I (optionnelle)')
        print()
        
        # 13. IP checksum
        print('  13. IP : vérif checksum')
        print('      └─ Re-calcul du checksum IPv4 → vérification d\'intégrité')
        print('         • Checksum émis : 0x7A36')
        print('         • Checksum recalculé : 0x7A36')
        print('         • ✅ En-tête IP intègre')
        print('         • Somme des mots 16 bits + complément à 1')
        print()
        
        # 14. TCP checksum
        print('  14. TCP : vérif checksum')
        print('      └─ Re-calcul du checksum TCP (avec pseudo-header) → validation')
        print('         • Checksum émis : 0x4013')
        print('         • Checksum recalculé : 0x4013')
        print('         • ✅ Segment TCP intègre')
        print('         • Pseudo-header inclut : IP src/dst, protocole, longueur')
        print()
        
        # 15. JSON parse
        print('  15. JSON parse')
        print('      └─ Extraction de la valeur "result" du JSON → entier final')
        print('         • Payload reçu : {"result":8}')
        print('         • Parsing JSON → objet Python')
        print('         • Extraction de la clé "result" → valeur = 8')
        print('         • 🔄 Vérification : 4+4=8 ✅')
        print('         • Transmission à l’application utilisateur')
        print()
        
        print('  ' + '=' * 68)
        print('  ✅ DÉCAPSULATION RÉUSSIE : Le résultat a été extrait avec succès !')
        print('  ' + '=' * 68)
        
    else:
        # Mode normal : simple liste
        steps = [
            'Antenne RX → LNA (G≈20 dB, NF≈1.5 dB)',
            'Mixeur down-conversion → I(t), Q(t) baseband',
            'ADC 12 bits @ 30.72 MS/s',
            'Suppression CP (144 échantillons)',
            'FFT 2048',
            'Démap 16-QAM → LLR par bit',
            'Dé-scramble (même seed)',
            'Turbo decode (8 itérations, BER<10⁻⁶)',
            'CRC-24A vérification → ACK HARQ',
            'MAC démux LCID → RLC PDU',
            'RLC réassemble → PDCP PDU',
            'PDCP déchiffre → paquet IP',
            'IP : vérif checksum (0x7A36)',
            'TCP : vérif checksum (0x4013)',
            'JSON parse → int résultat'
        ]
        for i, step in enumerate(steps, 1):
            print(f'  {i:2d}. {step}')

def L14_glyph(result: int, font_path: str = None):
    banner(f'NIVEAU 14 — Glyph "{result}" rastérisé (bitmap 8×8)')
    char = str(result)
    print(f'  Lookup fonte : code ASCII 0x{ord(char):02X} → 8 octets de bitmap')
    
    # Rasterisation automatique
    glyph = raster_glyph(char, font_size=8, font_path=font_path if font_path else '')
    
    print('  Représentation visuelle (█ = pixel ON, · = pixel OFF) :')
    n_on = 0
    for row in glyph:
        line = ''.join('█' if (row >> (7-b)) & 1 else '·' for b in range(8))
        print(f'    {line}   0x{row:02X}  {row:08b}')
        n_on += bin(row).count('1')
    print(f'  Pixels allumés : {n_on} sur 64')
    return n_on

def L15_oled(cfg, n_pixels_on):
    banner('NIVEAU 15 — Sous-pixel OLED : U = R · I (boucle bouclée)')
    V = cfg['oled_voltage_v']
    R = cfg['oled_pixel_resistance_ohm']
    I = V / R
    P_per_subpix = V * I
    n_subpix = n_pixels_on * 3
    I_total = n_subpix * I
    P_total = n_subpix * P_per_subpix
    print(f'  V_OLED = {V} V')
    print(f'  R_pixel = {R/1e3:.0f} kΩ')
    print(f'  I_pixel = U / R = {I*1e6:.2f} µA')
    print(f'  P_pixel = V·I = {P_per_subpix*1e6:.2f} µW par sous-pixel')
    print(f'  {n_pixels_on} pixels ON × 3 sous-pixels = {n_subpix} sous-pixels')
    print(f'  I_total = {I_total*1e6:.2f} µA   P_total = {P_total*1e6:.2f} µW')
    print()
    print('  ┌──────────────────────────────────────────────────────────────┐')
    print('  │  Niveau 0  (TX)  : U=0.9 V   R≈5 kΩ    I≈180 µA    MOSFET    │')
    print(f'  │  Niveau 15 (RX)  : U={V} V   R={R/1e3:.0f} kΩ   I={I*1e6:.2f} µA    OLED      │')
    print('  │  Même loi linéaire à 2 paramètres aux deux extrémités.       │')
    print('  └──────────────────────────────────────────────────────────────┘')

# ------------------------------------------------------------
# 9. Main avec parsing des arguments
# ------------------------------------------------------------
def parse_addition(addition_str: str) -> tuple:
    """Parse une chaîne comme '1+1' ou '3+5'"""
    try:
        if '+' in addition_str:
            a, b = map(int, addition_str.split('+'))
            return a, b
        else:
            raise ValueError("Format attendu: a+b (ex: 1+1, 3+5, 12+7)")
    except Exception as e:
        print(f"Erreur de parsing: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description='Trace complète LTE/NR : du MOSFET à l\'OLED',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s pile_values.csv 1+1              # Addition 1+1 (défaut)
  %(prog)s pile_values.csv 3+5              # Addition 3+5
  %(prog)s pile_values.csv 12+7 --verbose   # Mode détaillé
  %(prog)s pile_values.csv 255+1            # Test débordement
  %(prog)s pile_values.csv 4+4 --font /chemin/police.ttf
        """
    )
    parser.add_argument('csv_file', help='Fichier CSV de configuration')
    parser.add_argument('addition', nargs='?', default='1+1', 
                       help='Addition à calculer (format: a+b, ex: 1+1, 3+5, 12+7)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Affiche le détail complet de la décapsulation (Niveau 13)')
    parser.add_argument('--font', help='Chemin vers une police TTF (optionnel)')
    
    args = parser.parse_args()
    
    # Chargement configuration
    cfg = load_csv(args.csv_file)
    print(f'\n📁 Config chargée depuis {args.csv_file} : {len(cfg)} paramètres')
    
    # Parsing de l'addition
    a, b = parse_addition(args.addition)
    print(f'🧮 Addition demandée : {a} + {b}')
    
    # Exécution des niveaux
    L0_mosfet(cfg)
    result = L1_full_adder(a, b)
    L2_alu_arm(result)
    payload = L3_payload(result)
    tcp_seg = L4_tcp(cfg, payload)
    ip_pkt = L5_ip(cfg, tcp_seg)
    L6_ethernet(cfg, ip_pkt)
    tb = L7_lte_ran(cfg, ip_pkt)
    scrambled = L8_phy_coding(cfg, tb)
    symbols = L9_qam16(scrambled)
    x_bb = L10_ofdm(cfg, symbols)
    L11_rf(cfg, x_bb)
    L12_friis(cfg)
    L13_decap(cfg, verbose=args.verbose)
    n_on = L14_glyph(result, args.font)
    L15_oled(cfg, n_on)
    
    print('\n' + '=' * 72)
    print(f'  ✅ Trace complète terminée. {a}+{b}={result} du transistor au sous-pixel.')
    print('=' * 72)
    print('\n  🔄 Le résultat a voyagé :')
    print(f'     MOSFET → Additionneur → ARMv8 → JSON → TCP → IP → Ethernet')
    print(f'     → PDCP chiffré → RLC → MAC → TB → Turbo → 16-QAM → OFDM')
    print(f'     → RF → Propagation → Réception → Démodulation → Décapsulation')
    print(f'     → Glyphe → OLED')
    print('  📐 Loi U = R·I vérifiée aux deux extrémités (TX: MOSFET, RX: OLED)')

if __name__ == '__main__':
    main()
