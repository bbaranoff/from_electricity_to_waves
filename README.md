```bash
python3 pile_trace.py pile_values.csv
```

```
📁 Config chargée depuis pile_values.csv : 38 paramètres
🧮 Addition demandée : 4 + 4

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
  NIVEAU 1 — Full adder : 4 + 4 en binaire (bits auto)
========================================================================
  4 + 4 sur 4 bits (auto)
  0100 (a)
  0100 (b)
  ----
  bit  0 : A=0 B=0 Cin=0  →  S=0 Cout=0
  bit  1 : A=0 B=0 Cin=0  →  S=0 Cout=0
  bit  2 : A=1 B=1 Cin=0  →  S=0 Cout=1
  bit  3 : A=0 B=0 Cin=1  →  S=1 Cout=0
  Résultat : 1000₂ = 8₁₀

========================================================================
  NIVEAU 2 — Instruction ARMv8 ADD
========================================================================
  MOV  W0, #1            ; W0 = 0x0000_0001
  MOV  W1, #1            ; W1 = 0x0000_0001
  ADD  W2, W0, W1        ; W2 = 0x00000008
  Encodage 32 bits : 0x0B010002

========================================================================
  NIVEAU 3 — Payload JSON applicatif
========================================================================
  snprintf  →  "{"result":8}"  (12 octets)
  0000: 7b 22 72 65 73 75 6c 74 22 3a 38 7d              {"result":8}
  Offset 10 = 0x38 = '8' (le résultat du Niveau 1)

========================================================================
  NIVEAU 4 — Segment TCP
========================================================================
  src port = 49152  dst port = 8080
  seq = 0x12345678  ack = 0x87654321
  flags = 0x18 (PSH+ACK)  window = 8192
  checksum = 0x4013
  Segment TCP complet (32 octets) :
  0000: c0 00 1f 90 12 34 56 78 87 65 43 21 50 18 20 00  .....4Vx.eC!P. .
  0010: 40 13 00 00 7b 22 72 65 73 75 6c 74 22 3a 38 7d  @...{"result":8}

========================================================================
  NIVEAU 5 — Paquet IPv4
========================================================================
  src = 10.45.0.42  dst = 10.99.0.7
  total length = 52  TTL = 64  proto = TCP(6)
  header checksum = 0x7A36
  Paquet IP complet (52 octets) :
  0000: 45 00 00 34 ab cd 40 00 40 06 7a 36 0a 2d 00 2a  E..4..@.@.z6.-.*
  0010: 0a 63 00 07 c0 00 1f 90 12 34 56 78 87 65 43 21  .c.......4Vx.eC!
  0020: 50 18 20 00 40 13 00 00 7b 22 72 65 73 75 6c 74  P. .@...{"result
  0030: 22 3a 38 7d                                      ":8}

========================================================================
  NIVEAU 6 — Trame Ethernet (backhaul S1-U / Internet)
========================================================================
  src MAC = 02:00:00:aa:bb:01  dst MAC = 02:00:00:cc:dd:fe
  EtherType = 0x0800 (IPv4)
  FCS (CRC32) = 0x11313235
  Trame Ethernet complète (70 octets) :
  0000: 02 00 00 cc dd fe 02 00 00 aa bb 01 08 00 45 00  ..............E.
  0010: 00 34 ab cd 40 00 40 06 7a 36 0a 2d 00 2a 0a 63  .4..@.@.z6.-.*.c
  0020: 00 07 c0 00 1f 90 12 34 56 78 87 65 43 21 50 18  .......4Vx.eC!P.
  0030: 20 00 40 13 00 00 7b 22 72 65 73 75 6c 74 22 3a   .@...{"result":
  0040: 38 7d 35 32 31 11                                8}521.

========================================================================
  NIVEAU 7 — Pile RAN LTE Uu : PDCP / RLC / MAC / CRC
========================================================================
  📋 PARAMÈTRES LTE (TS 33.401) :
     • IMSI : 310150123456789
     • K : 00112233445566778899AABBCCDDEEFF
     • OPC : 00112233445566778899AABBCCDDEEFF
     • AMF : 8000
     • RNTI : 0x4601

  PDCP SN = 0x123, PDU = 54 octets
  🔐 Chiffrement LTE AES-128 CTR (TS 33.401)
     • K_upenc : 8ce98ae4890de3c53f3368a51dee9b0d
     • COUNT = 0x00000123 (HFN=0x0000, SN=0x123)
     • PDU complet (54 octets) :
       0000: 01 23 8f 37 45 59 88 1b ca 69 2c 26 94 6f 08 48  .#.7EY...i,&.o.H
       0010: 17 37 53 bb 0e b1 01 79 37 54 ec c8 cb 4c e1 08  .7S....y7T...L..
       0020: 98 b2 18 a6 d2 12 97 9e 54 04 0a 86 49 cf 67 38  ........T...I.g8
       0030: ab 98 8c a9 1b f4                                ......

  RLC UM : SN=0x123, PDU=56 octets
     • Header : 0x0123
     • PDU complet (56 octets) :
       0000: 01 23 01 23 8f 37 45 59 88 1b ca 69 2c 26 94 6f  .#.#.7EY...i,&.o
       0010: 08 48 17 37 53 bb 0e b1 01 79 37 54 ec c8 cb 4c  .H.7S....y7T...L
       0020: e1 08 98 b2 18 a6 d2 12 97 9e 54 04 0a 86 49 cf  ..........T...I.
       0030: 67 38 ab 98 8c a9 1b f4                          g8......

  MAC PDU : LCID=1 (DTCH), longueur=56, PDU=58 octets
     • Header : 0x0438
     • PDU complet (58 octets) :
       0000: 04 38 01 23 01 23 8f 37 45 59 88 1b ca 69 2c 26  .8.#.#.7EY...i,&
       0010: 94 6f 08 48 17 37 53 bb 0e b1 01 79 37 54 ec c8  .o.H.7S....y7T..
       0020: cb 4c e1 08 98 b2 18 a6 d2 12 97 9e 54 04 0a 86  .L..........T...
       0030: 49 cf 67 38 ab 98 8c a9 1b f4                    I.g8......

  CRC-24A = 0x6ACFAD
  Transport Block (TB) = 61 octets = 488 bits
     • TB complet (61 octets) :
       0000: 04 38 01 23 01 23 8f 37 45 59 88 1b ca 69 2c 26  .8.#.#.7EY...i,&
       0010: 94 6f 08 48 17 37 53 bb 0e b1 01 79 37 54 ec c8  .o.H.7S....y7T..
       0020: cb 4c e1 08 98 b2 18 a6 d2 12 97 9e 54 04 0a 86  .L..........T...
       0030: 49 cf 67 38 ab 98 8c a9 1b f4 6a cf ad           I.g8......j..

========================================================================
  NIVEAU 8 — Codage canal : turbo 1/3 + rate-match + scramble
========================================================================
  Turbo 1/3 RSC polys : (1, 1+D²+D³, 1+D+D³)
    488 bits  →  1476 bits codés (+ 12 tail)
  Rate-match : 1476 → 1152 bits
    (2 PRB × 144 RE × 4 bits/sym)
  Scramble seed = (RNTI=0x4601, PCI=1, sf=3)
  Premiers 64 bits scramblés :
    1010001100110111010010010000111000111010001011110101011111011001

========================================================================
  NIVEAU 9 — Mapping 16-QAM (TS 36.211 §7.1.3)
========================================================================
  288 symboles 16-QAM produits
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
    n=  0  I=+0.09821  Q=-0.05249  |s|=0.11136
    n=  1  I=-0.02136  Q=+0.11023  |s|=0.11228
    n=  2  I=-0.07263  Q=-0.08676  |s|=0.11315
    n=  3  I=+0.11396  Q=-0.00167  |s|=0.11397
    n=  4  I=-0.07106  Q=+0.09010  |s|=0.11475
    n=  5  I=-0.02527  Q=-0.11268  |s|=0.11548
    n=  6  I=+0.10400  Q=+0.05176  |s|=0.11617
    n=  7  I=-0.10633  Q=+0.04833  |s|=0.11680
    n=  8  I=+0.02970  Q=-0.11356  |s|=0.11738
    n=  9  I=+0.06972  Q=+0.09509  |s|=0.11792
    n= 10  I=-0.11825  Q=-0.00587  |s|=0.11840
    n= 11  I=+0.07941  Q=-0.08840  |s|=0.11883
    n= 12  I=+0.01861  Q=+0.11775  |s|=0.11921
    n= 13  I=-0.10342  Q=-0.05996  |s|=0.11954
    n= 14  I=+0.11200  Q=-0.04259  |s|=0.11982
    n= 15  I=-0.03760  Q=+0.11400  |s|=0.12005
  Puissance moyenne E[|x|²] = 0.0137

========================================================================
  NIVEAU 11 — RF : DAC + mixeur quadrature + PA
========================================================================
  EARFCN UL = 19575  →  f_c = 1747.5 MHz
  P_TX = 23 dBm = 200 mW
  s_RF(t) = I(t)·cos(2π f_c t) − Q(t)·sin(2π f_c t)
  Évaluation analytique sur 8 échantillons :
    n=0 t=  0.00 ns  I=+0.0982 Q=-0.0525  →  s_RF=+0.09821
    n=1 t= 32.55 ns  I=-0.0214 Q=+0.1102  →  s_RF=+0.05701
    n=2 t= 65.10 ns  I=-0.0726 Q=-0.0868  →  s_RF=-0.09500
    n=3 t= 97.66 ns  I=+0.1140 Q=-0.0017  →  s_RF=-0.06585
    n=4 t=130.21 ns  I=-0.0711 Q=+0.0901  →  s_RF=+0.09082
    n=5 t=162.76 ns  I=-0.0253 Q=-0.1127  →  s_RF=+0.07433
    n=6 t=195.31 ns  I=+0.1040 Q=+0.0518  →  s_RF=-0.08572
    n=7 t=227.86 ns  I=-0.1063 Q=+0.0483  →  s_RF=-0.08235

========================================================================
  NIVEAU 12 — Bilan de liaison Friis (UE_A → eNB)
========================================================================
  d = 500 m,  λ = c/fc = 17.17 cm
  L_FS  = (4π·d/λ)² = 1.340e+09  →  91.3 dB
  L_excess (urbain COST-231) = 30 dB
  L_total = 121.3 dB
  P_r = -81.3 dBm
  N_sys = -98.0 dBm
  SNR ≈ 16.7 dB

========================================================================
  NIVEAU 13 — Décapsulation symétrique côté UE_B (récap)
========================================================================

  📡 DÉTAIL COMPLET DE LA DÉCAPSULATION AVEC CALCULS :

   1. Antenne RX → LNA
      └─ Gain ≈ 20 dB, NF ≈ 1.5 dB
         • Puissance reçue (calculée au Niveau 12) : Pr = -81.3 dBm
         • Après LNA : P_rx = -81.3 + 20 = -61.3 dBm
         • Bruit ajouté par le LNA : NF = 1.5 dB → F = 10^(1.5/10) = 1.41

   2. Mixeur down-conversion
      └─ I(t) = s_RF(t)·cos(2πf_c t), Q(t) = -s_RF(t)·sin(2πf_c t)
         • Fréquence porteuse f_c = 1747.5 MHz
         • Échantillons reçus (premiers I/Q) :
           - I0 = +1.7347, Q0 = +1.5235
           - I1 = -2.2667, Q1 = +0.4814
           - I2 = +0.9774, Q2 = -2.1141

   3. ADC 12 bits
      └─ Échantillonnage à 30.72 MS/s
         • Tension pleine échelle : Vref = 1.8 V
         • Résolution : 1.8 / 4096 = 0.44 mV/LSB
         • Quantification : Q = round(V / 0.44 mV)
         • Premier échantillon : I=1.7347V → code = 3942

   4. Suppression CP
      └─ Retrait des 144 échantillons de préfixe cyclique par symbole OFDM
         • Trame reçue : 2192 échantillons/symbole
         • Suppression des 144 premiers échantillons
         • Conservation des 2048 échantillons utiles

   5. FFT 2048
      └─ Transformée de Fourier rapide N=2048
         • X[k] = Σ x[n]·e^(-j2πkn/2048)
         • Restitution des 24 sous-porteuses actives
         • Énergie moyenne après FFT : E[|X|²] = 82.94

   6. Démap 16-QAM
      └─ Calcul des LLR (Log-Likelihood Ratio)
         • LLR(b0) = -4·Re(s) / (√10·σ²)
         • LLR(b1) = -4·Im(s) / (√10·σ²)
         • LLR(b2) = -4·(2 - |Re(s)|·√10) / (√10·σ²)
         • LLR(b3) = -4·(2 - |Im(s)|·√10) / (√10·σ²)
         • SNR estimée = 16.7 dB → σ² ≈ 0.021
         • Premier symbole s=0.3162+0.3162j → LLR≈[-4, -4, +12, +12]

   7. Dé-scramble
      └─ Application du même seed : RNTI=0x4601, PCI=1, sf=3
         • Seed = 1174470915
         • c(n) = (x1(n+Nc) + x2(n+Nc)) mod 2
         • Dé-sembrouillage : b_reçu(n) = b_scramblé(n) ⊕ c(n)
         • Rétablissement des bits codés originaux

   8. Turbo decode
      └─ Décodage itératif Max-Log-MAP
         • Itérations : 8 (max 16)
         • BER cible : < 10⁻⁶
         • Taux de code : 1/3
         • Polynômes RSC : (1, 1+D²+D³, 1+D+D³)
         • 480 bits d’entrée → 1440 bits décodés
         • Gain de codage ≈ 7 dB à BER=10⁻⁵

   9. CRC-24A vérification
      └─ Calcul du CRC-24A sur le TB reçu
         • Poly = 0x1864CFB = x²⁴ + x²³ + x⁶ + x⁵ + x³ + x + 1
         • CRC calculé à l'émission : 0xDD5713
         • CRC recalculé à la réception : 0xDD5713
         • ✅ Vérification OK → ACK envoyé à l'émetteur
         • Si erreur → NACK + requête HARQ (retransmission)

  10. MAC démux LCID
      └─ Extraction du RLC PDU en fonction du Logical Channel ID
         • LCID = 0x01 (DCCH/DTCH)
         • MAC header : 0x01 0x37 (LCID + longueur)
         • Extraction du RLC PDU (55 octets)

  11. RLC réassemble
      └─ Réassemblage des segments RLC UM en PDCP PDU complet
         • RLC header : 0xC0 (UM avec extension SN=12 bits)
         • RLC SN = 0x123
         • Fi = 0 (pas de segmentation)
         • PDCP PDU reconstitué (54 octets)

  12. PDCP déchiffre
      └─ Déchiffrement AES-CTR avec le même compteur que l'émission
         • PDCP SN = 0x123
         • Clé dérivée du RNTI (SHA-256 → AES-128)
         • Compteur : nonce = MD5(RNTI||SN)
         • Déchiffrement : plain = cipher ⊕ keystream
         • Paquet IP restauré (52 octets)
         • Vérification MAC-I (optionnelle)

  13. IP : vérif checksum
      └─ Re-calcul du checksum IPv4 → vérification d'intégrité
         • Checksum émis : 0x7A36
         • Checksum recalculé : 0x7A36
         • ✅ En-tête IP intègre
         • Somme des mots 16 bits + complément à 1

  14. TCP : vérif checksum
      └─ Re-calcul du checksum TCP (avec pseudo-header) → validation
         • Checksum émis : 0x4013
         • Checksum recalculé : 0x4013
         • ✅ Segment TCP intègre
         • Pseudo-header inclut : IP src/dst, protocole, longueur

  15. JSON parse
      └─ Extraction de la valeur "result" du JSON → entier final
         • Payload reçu : {"result":8}
         • Parsing JSON → objet Python
         • Extraction de la clé "result" → valeur = 8
         • 🔄 Vérification : 4+4=8 ✅
         • Transmission à l’application utilisateur

  ====================================================================
  ✅ DÉCAPSULATION RÉUSSIE : Le résultat a été extrait avec succès !
  ====================================================================

========================================================================
  NIVEAU 14 — Glyph "8" rastérisé (bitmap 8×8)
========================================================================
  Lookup fonte : code ASCII 0x38 → 8 octets de bitmap
  Représentation visuelle (█ = pixel ON, · = pixel OFF) :
    ··████··   0x3C  00111100
    ·██··██·   0x66  01100110
    ·██··██·   0x66  01100110
    ··████··   0x3C  00111100
    ·██··██·   0x66  01100110
    ·██··██·   0x66  01100110
    ··████··   0x3C  00111100
    ········   0x00  00000000
  Pixels allumés : 28 sur 64

========================================================================
  NIVEAU 15 — Sous-pixel OLED : U = R · I (boucle bouclée)
========================================================================
  V_OLED = 3.0 V
  R_pixel = 600 kΩ
  I_pixel = U / R = 5.00 µA
  P_pixel = V·I = 15.00 µW par sous-pixel
  28 pixels ON × 3 sous-pixels = 84 sous-pixels
  I_total = 420.00 µA   P_total = 1260.00 µW

  ┌──────────────────────────────────────────────────────────────┐
  │  Niveau 0  (TX)  : U=0.9 V   R≈5 kΩ    I≈180 µA    MOSFET    │
  │  Niveau 15 (RX)  : U=3.0 V   R=600 kΩ   I=5.00 µA    OLED      │
  │  Même loi linéaire à 2 paramètres aux deux extrémités.       │
  └──────────────────────────────────────────────────────────────┘

========================================================================
  ✅ Trace complète terminée. 4+4=8 du transistor au sous-pixel.
========================================================================

  🔄 Le résultat a voyagé :
     MOSFET → Additionneur → ARMv8 → JSON → TCP → IP → Ethernet
     → PDCP chiffré → RLC → MAC → TB → Turbo → 16-QAM → OFDM
     → RF → Propagation → Réception → Démodulation → Décapsulation
     → Glyphe → OLED
  📐 Loi U = R·I vérifiée aux deux extrémités (TX: MOSFET, RX: OLED)
  ```
