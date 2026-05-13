```bash
python3 pile_trace.py pile_values.csv 4+4 --verbose
```
```txt
📁 Config chargée : 38 paramètres
🧮 Addition demandée : 4 + 4

========================================================================
  NIVEAU 0 COMPLET — Du clavier au registre (chaîne physique)
========================================================================

  📋 CHAÎNE DE TRAITEMENT :
  Touche → Contact → Anti-rebond → MOSFET → Inverseur → NAND → Bascule → Registre
     ↓         ↓          ↓          ↓         ↓        ↓        ↓         ↓
   3.3V      0V/3.3V    0V/3.3V     I_D      NOT     NAND     D Q      Stockage

========================================================================
  NIVEAU 0_origin — Driver clavier Toy (touche → signal électrique)
========================================================================
  🎮 CLAVIER TOY - SAISIE : 4 + 4 = 8
     • Touche : "8" (ASCII 0x38)
     • Matrice : ligne 0, colonne 7
     • Vcc = 3.3 V, R_pullup = 10 kΩ
     • Anti-rebond : 10 ms

  💾 SIGNAL NUMÉRIQUE FINAL :
  ┌─────────────────────────────────────────────────────────────────┐
  │ Vout(V)   Digital                                              │
  │  3.3 ┤██████████████████████████████████████████████████████████│
  │  0.0 ┤                                                          │
  │      ┼───────┬───────┬───────┬───────┬───────┬───────┬───────┬─┤
  │        0      2      4      6      8     10     12     14     16
  │                           t (ms)                                │
  └─────────────────────────────────────────────────────────────────┘

========================================================================
  NIVEAU 0 — MOSFET NMOS : commutation clavier → courant
========================================================================
  🔌 SIGNAL D'ENTRÉE :
     • Touche : "8" → V_GS = 3.3 V

  ✅ MOSFET ACTIF :
     • V_GS = 3.3 V, V_th = 0.4 V
     • I_D = 6728.0 µA
     • R_on = 0.13 kΩ
     • E_switch = 4.05 fJ

========================================================================
  NIVEAU 0 bis — Inverseur CMOS (porte NOT)
========================================================================
  • VDD = 0.9 V, seuil = 0.45 V
  • Vin = 0.0 V (sortie MOSFET)
  • Vout = 0.9 V (NOT de Vin)
  • NMOS = OFF, PMOS = ON

  ⏱️  Délais : t_rise = 7.36 ps, t_fall = 2.94 ps

========================================================================
  NIVEAU 0 ter — Porte NAND (porte universelle)
========================================================================
  • Entrée A = 0 (bit de poids fort)
  • Entrée B = 1 (bit de poids faible)
  • NAND : Y = NOT(A AND B) = 1

  Table de vérité :
  ┌─────┬─────┬───────┐
  │  A  │  B  │ Y=A·B │
  ├─────┼─────┼───────┤
  │  0  │  0  │   1   │
  │  0  │  1  │   1   │
  │  1  │  0  │   1   │
  │  1  │  1  │   0   │
  └─────┴─────┴───────┘

  ⏱️  Délais : t_HL = 198.00 ps, t_LH = 247.50 ps

========================================================================
  NIVEAU 0 quart — Bascule D → Registre 2 bits
========================================================================
  🔷 BASCULE D MASTER-SLAVE
     • Valeur à stocker : 1₁₀ = 01₂
     • Horloge : front montant (1 GHz)

     Simulation :
     ┌───────┬─────┬─────┬─────┬─────┬─────┬─────────────┐
     │ Cycle │ CLK │ D1  │ D0  │ Q1  │ Q0  │ État        │
     ├───────┼─────┼─────┼─────┼─────┼─────┼─────────────┤
     │   0   │  1  │  0  │  1  │  0  │  1  │ stocké 01   │
     │   1   │  0  │  0  │  1  │  0  │  1  │ maintien    │
     │   2   │  1  │  0  │  1  │  0  │  1  │ stocké 01   │
     │   3   │  0  │  0  │  1  │  0  │  1  │ maintien    │
     └───────┴─────┴─────┴─────┴─────┴─────┴─────────────┘

  ⚡ Consommation : 64.80 µW
  💾 Valeur stockée dans le registre : 1₁₀ = 01₂

========================================================================
  🔗 LIAISON NIVEAU 0 → NIVEAU 1 (Additionneur)
========================================================================
  • Le registre stocke la valeur : 1
  • Cette valeur est chargée dans l'additionneur du Niveau 1
  • Format : 1₁₀ = 01₂
  • Les bits sont envoyés sur les entrées A et B de l'additionneur

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

  🔗 LIAISON AVEC LE NIVEAU 0 :
     • Les entrées 4 et 4 viennent du registre du Niveau 0
     • Le résultat 8 va être envoyé au Niveau 2 (ARM ALU)

  ⚠️ NOTE : Le registre stocke 1, l'addition donne 8
      (Le registre simule la saisie clavier, l'additionneur calcule indépendamment)

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

  📡 DÉCAPSULATION DYNAMIQUE (appels inverses) :

   🔄 Niveau 11 (inverse) : Réception RF → Baseband I/Q
      • s_RF(t) reçu → down-conversion avec f_c = 1747.5 MHz
      • I(t) = s_RF(t)·cos(2πf_c t) → filtre passe-bas
      • Q(t) = -s_RF(t)·sin(2πf_c t) → filtre passe-bas

   🔄 Niveau 10 (inverse) : Démodulation OFDM
      • Suppression du CP (144 échantillons)
      • FFT N=2048 → retour domaine fréquentiel
      • Extraction des 24 sous-porteuses actives

      📊 CALCUL FFT DÉTAILLÉ :
      X[k] = Σ x[n]·e^(-j2πkn/N) pour k=0..N-1
      • X_freq calculé pour 2048 points
      • Sous-porteuses actives : indices 724 à 747

      🎯 SYMBOLES 16-QAM RECONSTRUITS (premiers) :
        - s0 = +1.2575 + -0.3935j
        - s1 = +0.5778 + -0.6492j
        - s2 = -1.0905 + +0.7187j
        - s3 = +1.1800 + -0.0805j

   🔄 Niveau 9 (inverse) : Démodulation 16-QAM → LLR
      • SNR estimée = 16.7 dB → σ² = 0.021380
      • Formules LLR (soft-demapping) :
        LLR(b0) = -4·Re(s) / (√10·σ²)
        LLR(b1) = -4·Im(s) / (√10·σ²)
        LLR(b2) = -4·(2 - |Re(s)|·√10) / (√10·σ²)
        LLR(b3) = -4·(2 - |Im(s)|·√10) / (√10·σ²)

      📊 CALCUL LLR DÉTAILLÉ :

      Symbole 0: s = +1.2575 + -0.3935j
        LLR(b0) = -74.40 → bit = 0
        LLR(b1) = +23.28 → bit = 1
        LLR(b2) = +116.95 → bit = 1
        LLR(b3) = -44.71 → bit = 0

      Symbole 1: s = +0.5778 + -0.6492j
        LLR(b0) = -34.19 → bit = 0
        LLR(b1) = +38.41 → bit = 1
        LLR(b2) = -10.22 → bit = 0
        LLR(b3) = +3.13 → bit = 1

      Symbole 2: s = -1.0905 + +0.7187j
        LLR(b0) = +64.52 → bit = 1
        LLR(b1) = -42.52 → bit = 0
        LLR(b2) = +85.69 → bit = 1
        LLR(b3) = +16.14 → bit = 1

      Symbole 3: s = +1.1800 + -0.0805j
        LLR(b0) = -69.81 → bit = 0
        LLR(b1) = +4.76 → bit = 1
        LLR(b2) = +102.44 → bit = 1
        LLR(b3) = -103.27 → bit = 0

      ✅ Bits reconstruits (premiers 16) :
        [0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0]

   🔄 Niveau 8 (inverse) : Déscramble + Décodage Turbo
      • Seed = 1174470915 (RNTI=0x4601, PCI=1, SF=3)
      • Générateur de scrambling LTE (registres à décalage) :
        c(n) = (x1(n+Nc) + x2(n+Nc)) mod 2
        x1(n+31) = (x1(n+3) + x1(n)) mod 2
        x2(n+31) = (x2(n+3) + x2(n+2) + x2(n+1) + x2(n)) mod 2
        Nc = 1600
      • Premiers bits scrambling : [1 0 0 0 1 1 0 0 0 0 0 1 0 0 0 0]
      • Bits reçus (scramblés)    : [0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0]
      • Après XOR                 : [np.int64(1), np.int64(1), np.int64(1), np.int64(0), np.int64(1), np.int64(0), np.int64(0), np.int64(1), np.int64(1), np.int64(0), np.int64(1), np.int64(0), np.int64(0), np.int64(1), np.int64(1), np.int64(0)]

      🚀 DÉCODAGE TURBO (TS 36.212 §5.1.3) :
      • 8 itérations Max-Log-MAP
      • Taux de code = 1/3
      • Polynômes RSC :
        - G0 = 1 (systématique)
        - G1 = 1 + D² + D³
        - G2 = 1 + D + D³
      • Entrelaceur QPP (Quadratic Permutation Polynomial)
      • Longueur de bloc = 480 bits

      📊 PERFORMANCES :
      • SNR d'entrée : 16.7 dB
      • Gain de codage : 7.0 dB
      • SNR après décodage : 23.7 dB
      • BER cible : < 1e-06

      ✅ Transport Block reconstruit : 61 octets = 488 bits
      • CRC-24A vérification : 0xD6E4E2
      • CRC-24A recalculé : 0xD6E4E2
      • ✅ Intégrité du TB vérifiée → ACK HARQ envoyé

   🔄 Niveau 7 (inverse) : MAC/RLC/PDCP déchiffrement
      • MAC démux LCID=0x01 → RLC PDU (56 octets)
      • RLC UM SN=0x123 → réassemblage
      • PDCP déchiffrement AES-128 CTR
      • COUNT = 0x00000123 (HFN=0, SN=0x123)
      • Paquet IP restauré (52 octets)

   🔄 Niveau 6 (inverse) : Décapsulation Ethernet
      • Vérification FCS CRC32 : 0x11313235 ✅
      • Source MAC: 02:00:00:aa:bb:01
      • Destination MAC: 02:00:00:cc:dd:fe

   🔄 Niveau 5 (inverse) : Vérification IPv4
      • Header checksum : 0x7A36 ✅
      • Source IP: 10.45.0.42
      • Destination IP: 10.99.0.7

   🔄 Niveau 4 (inverse) : Vérification TCP
      • Checksum TCP : 0x4013 ✅
      • Flags: PSH+ACK, Window: 8192

   🔄 Niveau 3 (inverse) : Parsing JSON
      • Payload reçu : b'{"result":8}'
      • json.loads() → {"result": 8}
      • Résultat extrait : 8

  ====================================================================
  ✅ DÉCAPSULATION RÉUSSIE
  ====================================================================
  📊 RÉCAPITULATIF DES OPÉRATIONS :
     • Down-conversion RF → I/Q (L11)
     • FFT + suppression CP → symboles (L10)
     • 16-QAM soft-demapping → LLR → bits (L9)
     • Déscramble + Turbo decode → TB (L8)
     • PDCP déchiffre + RLC + MAC → IP (L7)
     • Ethernet décapage → IP (L6)
     • IP checksum → TCP (L5)
     • TCP checksum → payload (L4)
     • JSON parse → résultat (L3)

  🎯 RÉSULTAT FINAL : 8
  🔄 Vérification : Le résultat correspond à l'addition du Niveau 1

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
  ✅ Trace complète. 4+4=8
  🔄 Hiérarchie complète : Clavier → MOSFET → Inverseur → NAND → Bascule → Registre → Additionneur → ... → OLED
========================================================================

  🔄 Le résultat a voyagé :
     MOSFET → Additionneur → ARMv8 → JSON → TCP → IP → Ethernet
     → PDCP chiffré → RLC → MAC → TB → Turbo → 16-QAM → OFDM
     → RF → Propagation → Réception → Démodulation → Décapsulation
     → Glyphe → OLED
  📐 Loi U = R·I vérifiée aux deux extrémités (TX: MOSFET, RX: OLED)
```
  📐 Loi U = R·I vérifiée aux deux extrémités (TX: MOSFET, RX: OLED)
  ```
