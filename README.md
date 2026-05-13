```bash
python3 pile_trace.py pile_values.csv
```

```

Config chargée depuis pile_values.csv : 34 paramètres

========================================================================
  NIVEAU 0 — MOSFET : U = R · I  (côté UE_A)
========================================================================
  VDD          = 0.9 V
  Vth          = 0.4 V
  µn·Cox·(W/L) = 1600.0 µA/V²
  I_D = ½·µCox·(W/L)·(Vgs−Vth)² = 200.0 µA
  R_on = U / I = 4.50 kΩ
  E_switch = ½·C·V² = 4.05 fJ par transition

========================================================================
  NIVEAU 1 — Full adder : 1 + 1 en binaire
========================================================================
  bit 0 : A=1 B=1 Cin=0  →  S=0 Cout=1
  bit 1 : A=0 B=0 Cin=1  →  S=1 Cout=0
  Résultat : S1S0 = 10₂ = 2₁₀

========================================================================
  NIVEAU 2 — Instruction ARMv8 ADD W2, W0, W1
========================================================================
  MOV  W0, #1            ; W0 = 0x0000_0001
  MOV  W1, #1            ; W1 = 0x0000_0001
  ADD  W2, W0, W1        ; W2 = 0x0000_0002
  Encodage 32 bits : 0x0B010002

========================================================================
  NIVEAU 3 — Payload JSON applicatif
========================================================================
  snprintf  →  "{"result":2}"  (12 octets)
  0000: 7b 22 72 65 73 75 6c 74 22 3a 32 7d              {"result":2}
  Offset 10 = 0x32 = '2' (le bit calculé au Niveau 1)

========================================================================
  NIVEAU 4 — Segment TCP
========================================================================
  src port = 49152  dst port = 8080
  seq = 0x12345678  ack = 0x87654321
  flags = 0x18 (PSH+ACK)  window = 8192
  checksum = 0x4613
  Segment TCP (32 octets) :
  0000: c0 00 1f 90 12 34 56 78 87 65 43 21 50 18 20 00  .....4Vx.eC!P. .
  0010: 46 13 00 00 7b 22 72 65 73 75 6c 74 22 3a 32 7d  F...{"result":2}

========================================================================
  NIVEAU 5 — Paquet IPv4
========================================================================
  src = 10.45.0.42  dst = 10.99.0.7
  total length = 52  TTL = 64  proto = TCP(6)
  header checksum = 0x7A36
  Paquet IP (52 octets) :
  0000: 45 00 00 34 ab cd 40 00 40 06 7a 36 0a 2d 00 2a  E..4..@.@.z6.-.*
  0010: 0a 63 00 07 c0 00 1f 90 12 34 56 78 87 65 43 21  .c.......4Vx.eC!
  0020: 50 18 20 00 46 13 00 00 7b 22 72 65 73 75 6c 74  P. .F...{"result
  0030: 22 3a 32 7d                                      ":2}

========================================================================
  NIVEAU 6 — Trame Ethernet (backhaul S1-U / Internet)
========================================================================
  NB : Ethernet apparaît sur le backhaul fibre (eNB↔S-GW↔P-GW)
       et sur l'Internet. PAS sur l'air interface Uu, où PDCP/
       RLC/MAC tiennent le rôle de L2.
  src MAC = 02:00:00:aa:bb:01  dst MAC = 02:00:00:cc:dd:fe
  EtherType = 0x0800 (IPv4)
  FCS (CRC32) = 0xB84FB35B
  Trame Ethernet (70 octets) :
  0000: 02 00 00 cc dd fe 02 00 00 aa bb 01 08 00 45 00  ..............E.
  0010: 00 34 ab cd 40 00 40 06 7a 36 0a 2d 00 2a 0a 63  .4..@.@.z6.-.*.c
  0020: 00 07 c0 00 1f 90 12 34 56 78 87 65 43 21 50 18  .......4Vx.eC!P.
  0030: 20 00 46 13 00 00 7b 22 72 65 73 75 6c 74 22 3a   .F...{"result":
  0040: 32 7d 5b b3 4f b8                                2}[.O.

========================================================================
  NIVEAU 7 — Pile RAN LTE Uu : PDCP / RLC / MAC / CRC
========================================================================
  PDCP SN = 0x123, PDU = 54 octets
    (chiffré via stub SHA-256 ; vraie crypto = AES-CTR / K_UPenc)
    0000: 01 23 de 66 97 73 fc 90 a0 d6 03 ce 88 61 3e 46  .#.f.s.......a>F
    0010: cb f1 ed 29 3a 7b 6c c7 c6 5d ff 20 be 80 95 21  ...):{l..]. ...!
    0020: e8 66 72 11 dd 43 be 21 16 9c 7e 1f 38 7b 39 96  .fr..C.!..~.8{9.
    ... +6 octets
  RLC UM : header=0xC0, PDU=55 octets
  MAC PDU = 57 octets
  CRC-24A = 0xE62911
  Transport Block (TB) = 60 octets = 480 bits

========================================================================
  NIVEAU 8 — Codage canal : turbo 1/3 + rate-match + scramble
========================================================================
  Turbo 1/3 RSC polys : (1, 1+D²+D³, 1+D+D³)
    480 bits  →  1452 bits codés (+ 12 tail)
  Rate-match : 1452 → 1152 bits
    (2 PRB × 144 RE × 4 bits/sym)
  Scramble seed = (RNTI=0x4601, PCI=1, sf=3)
  Premiers 64 bits scramblés :
    1010001100110111010010010000111000111010001011110101011111011001

========================================================================
  NIVEAU 9 — Mapping 16-QAM (TS 36.211 §7.1.3)
========================================================================
  288 symboles 16-QAM produits
  Formule : s = ((1−2b₀)(2−(1−2b₂)) + j(1−2b₁)(2−(1−2b₃))) / √10
  Premiers 8 symboles :
    [0] bits=1010  →  s = -0.9487 + +0.3162j   |s|=1.0000
    [1] bits=0011  →  s = +0.9487 + +0.9487j   |s|=1.3416
    [2] bits=0011  →  s = +0.9487 + +0.9487j   |s|=1.3416
    [3] bits=0111  →  s = +0.9487 + -0.9487j   |s|=1.3416
    [4] bits=0100  →  s = +0.3162 + -0.3162j   |s|=0.4472
    [5] bits=1001  →  s = -0.3162 + +0.9487j   |s|=1.0000
    [6] bits=0000  →  s = +0.3162 + +0.3162j   |s|=0.4472
    [7] bits=1110  →  s = -0.9487 + -0.3162j   |s|=1.0000
  Énergie moyenne E[|s|²] = 0.9694  (cible 1.0)

========================================================================
  NIVEAU 10 — OFDM : mapping RE + IFFT + préfixe cyclique
========================================================================
  IFFT N = 2048, 24 sous-porteuses actives
  CP normal = 144 échantillons
  Durée symbole (avec CP) = 71.35 µs
  fs = 30.72 MS/s,  Ts = 32.552 ns
  Premiers 16 échantillons I/Q après CP :
    n=  0  I=+0.06634  Q=-0.08944  |s|=0.11136
    n=  1  I=+0.02748  Q=+0.10886  |s|=0.11228
    n=  2  I=-0.10246  Q=-0.04800  |s|=0.11315
    n=  3  I=+0.10277  Q=-0.04929  |s|=0.11397
    n=  4  I=-0.02708  Q=+0.11151  |s|=0.11475
    n=  5  I=-0.06962  Q=-0.09214  |s|=0.11548
    n=  6  I=+0.11608  Q=+0.00446  |s|=0.11617
    n=  7  I=-0.07736  Q=+0.08751  |s|=0.11680
    n=  8  I=-0.01887  Q=-0.11586  |s|=0.11738
    n=  9  I=+0.10210  Q=+0.05899  |s|=0.11792
    n= 10  I=-0.11075  Q=+0.04187  |s|=0.11840
    n= 11  I=+0.03781  Q=-0.11265  |s|=0.11883
    n= 12  I=+0.06350  Q=+0.10090  |s|=0.11921
    n= 13  I=-0.11863  Q=-0.01472  |s|=0.11954
    n= 14  I=+0.08667  Q=-0.08274  |s|=0.11982
    n= 15  I=+0.00926  Q=+0.11969  |s|=0.12005
  Puissance moyenne E[|x|²] = 0.0137

========================================================================
  NIVEAU 11 — RF : DAC + mixeur quadrature + PA
========================================================================
  EARFCN UL = 19575  →  f_c = 1747.5 MHz
  P_TX = 23 dBm = 200 mW
  s_RF(t) = I(t)·cos(2π f_c t) − Q(t)·sin(2π f_c t)
  Évaluation analytique sur 8 échantillons :
    n=0 t=  0.00 ns  I=+0.0663 Q=-0.0894  →  s_RF=+0.06634
    n=1 t= 32.55 ns  I=+0.0275 Q=+0.1089  →  s_RF=+0.09270
    n=2 t= 65.10 ns  I=-0.1025 Q=-0.0480  →  s_RF=-0.06019
    n=3 t= 97.66 ns  I=+0.1028 Q=-0.0493  →  s_RF=-0.09878
    n=4 t=130.21 ns  I=-0.0271 Q=+0.1115  →  s_RF=+0.05337
    n=5 t=162.76 ns  I=-0.0696 Q=-0.0921  →  s_RF=+0.10423
    n=6 t=195.31 ns  I=+0.1161 Q=+0.0045  →  s_RF=-0.04594
    n=7 t=227.86 ns  I=-0.0774 Q=+0.0875  →  s_RF=-0.10898

========================================================================
  NIVEAU 12 — Bilan de liaison Friis (UE_A → eNB)
========================================================================
  d = 500 m,  λ = c/fc = 17.17 cm
  L_FS  = (4π·d/λ)² = 1.340e+09  →  91.3 dB
  L_excess (urbain COST-231) = 30 dB
  L_total = 121.3 dB
  P_r = Pt + Gt + Gr − L = 23 + 0 + 17 − 121.3 = -81.3 dBm
  N_thermique(20 MHz) = -101.0 dBm,  NF = 3 dB
  N_sys = -98.0 dBm
  SNR ≈ 16.7 dB

========================================================================
  NIVEAU 13 — Décapsulation symétrique côté UE_B (récap)
========================================================================
   1. Antenne RX → LNA (G≈20 dB, NF≈1.5 dB)
   2. Mixeur down-conversion → I(t), Q(t) baseband
   3. ADC 12 bits @ 30.72 MS/s
   4. Suppression CP, FFT 2048
   5. Démap 16-QAM → LLR par bit
   6. Dé-scramble (même seed Gold)
   7. Turbo decode (Max-Log-MAP, ~8 itérations) → TB
   8. CRC-24A vérification → ACK HARQ
   9. MAC démux LCID → RLC PDU
  10. RLC réassemble → PDCP PDU
  11. PDCP déchiffre AES-CTR → paquet IP
  12. IP : vérif checksum, strip header → segment TCP
  13. TCP : vérif checksum, SN, ACK → 12 B payload
  14. JSON parse → int 2

========================================================================
  NIVEAU 14 — Glyph '2' rastérisé (bitmap 8×8)
========================================================================
  Lookup fonte : code ASCII 0x32 → 8 octets de bitmap
  Représentation visuelle (■ = pixel ON) :
    ··■■■■··   0x3C  00111100
    ·■····■·   0x42  01000010
    ······■·   0x02  00000010
    ····■■··   0x0C  00001100
    ··■■····   0x30  00110000
    ·■······   0x40  01000000
    ·■■■■■■·   0x7E  01111110
    ········   0x00  00000000
  Pixels allumés : 18 sur 64

========================================================================
  NIVEAU 15 — Sous-pixel OLED : U = R · I (boucle bouclée)
========================================================================
  V_OLED = 3.0 V
  R_pixel = 600 kΩ
  I_pixel = U / R = 5.00 µA   ← loi d'Ohm (comme Niveau 0)
  P_pixel = V·I = 15.00 µW par sous-pixel
  18 pixels ON × 3 sous-pixels = 54 sous-pixels
  I_total = 270.00 µA   P_total = 810.00 µW

  ┌──────────────────────────────────────────────────────────────┐
  │  Niveau 0  (TX)  : U=0.9 V   R≈5 kΩ    I≈180 µA    MOSFET    │
  │  Niveau 15 (RX)  : U=3.0 V   R=600 kΩ   I=5.00 µA    OLED      │
  │  Même loi linéaire à 2 paramètres aux deux extrémités.       │
  └──────────────────────────────────────────────────────────────┘

========================================================================
  Trace complète terminée. U=R·I bouclée du transistor au sous-pixel.
========================================================================
``


