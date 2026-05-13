```bash
python3 pile_trace.py pile_values.csv 4+4 --verbose
```
```txt(.env) nirvana@lenovo:~/from_electricity_to_waves$ python pile_trace.py pile_values.csv 1+1     --rx-override k=00112233445566778899AABBCCDDEEFE

📁 Config : 44 clés ; addition : 1 + 1

========================================================================
  NIVEAU 0 — Saisie clavier → deux registres (chaîne physique)
========================================================================
  Architecture (par opérande) :
    Touche → Debounce → MOSFET → Inverseur CMOS → Bascule D × N → Registre
  NAND : primitive universelle montrée en référence.
  Chaque opérande a son propre registre. L1 (adder) lit R_A et R_B.

  ┌── Saisie opérande A = 1₁₀ (1₂, 1 bits) ──
  │  Touche "1" (poids faible "1", ASCII 0x31)
  │  Matrice : ligne 1, col 6
  │  Anti-rebond 10 ms ; Vcc=3.3 V ; R_pullup=10 kΩ
  │
  ▶ MOSFET (A) : V_GS=3.3 V, V_th=0.4 V
     I_D = ½·µCox·(W/L)·(V_GS−V_th)² = 6728.0 µA
     R_on = V/I = 0.13 kΩ ; E_switch = ½·C·V² = 4.05 fJ
  ▶ Inverseur CMOS (A) : VDD=0.9 V
     t_rise = 7.36 ps, t_fall = 2.94 ps
  │  Registre 1× bascule D master-slave (front montant 1 GHz) :
  │     Q[0..0] = 1  (valeur stockée : 1)
  │  P_dyn ≈ 16.20 µW (4 portes/bascule × 1 bascules)
  └── R_A = 1

  ── Référence : porte NAND (primitive universelle) ──
     A B │ Y=NAND(A,B)
     ────┼────────────
      0 0 │     1
      0 1 │     1
      1 0 │     1
      1 1 │     0
     (toutes les portes — INV, AND, OR, XOR, FF — se construisent par cascade de NAND)

  ┌── Saisie opérande B = 1₁₀ (1₂, 1 bits) ──
  │  Touche "1" (poids faible "1", ASCII 0x31)
  │  Matrice : ligne 1, col 6
  │  Anti-rebond 10 ms ; Vcc=3.3 V ; R_pullup=10 kΩ
  │  MOSFET passant (I_D ≈ 6728 µA) → inverseur (t_d ≈ ps) → idem
  │  Registre 1× bascule D master-slave (front montant 1 GHz) :
  │     Q[0..0] = 1  (valeur stockée : 1)
  │  P_dyn ≈ 16.20 µW (4 portes/bascule × 1 bascules)
  └── R_B = 1

  🔗 Liaison L0 → L1 :
     R_A = 1  (1₂)
     R_B = 1  (1₂)
     → entrées A et B du full adder (Niveau 1)

========================================================================
  NIVEAU 1 — Full adder : R_A + R_B = 1 + 1
========================================================================
  Opérandes lues depuis L0 : R_A=1, R_B=1
  Largeur calculée : 2 bits (= max(bit_length) + 1)

  bit  0: A=1 B=1 Cin=0 → S=0 Cout=1
  bit  1: A=0 B=0 Cin=1 → S=1 Cout=0

  Résultat : 10₂ = 2₁₀
  Envoyé à L2 (ARMv8 ALU)

========================================================================
  NIVEAU 2 — Instruction ARMv8 ADD
========================================================================
  MOV  W0, #1          ; W0 = 0x00000001
  MOV  W1, #1          ; W1 = 0x00000001
  ADD  W2, W0, W1        ; W2 = 0x00000002
  Encodage 32 bits : 0x0B010002

========================================================================
  NIVEAU 3 — Payload JSON applicatif
========================================================================
  json.dumps → "{"result":2}" (12 octets)
  0000: 7b 22 72 65 73 75 6c 74 22 3a 32 7d              {"result":2}

========================================================================
  NIVEAU 4 — Segment TCP
========================================================================
  49152 → 8080 ; seq=0x12345678 ack=0x87654321
  flags=0x18 (PSH+ACK) window=8192 csum=0x4613
  Segment (32 octets) :
  0000: c0 00 1f 90 12 34 56 78 87 65 43 21 50 18 20 00  .....4Vx.eC!P. .
  0010: 46 13 00 00 7b 22 72 65 73 75 6c 74 22 3a 32 7d  F...{"result":2}

========================================================================
  NIVEAU 5 — Paquet IPv4
========================================================================
  10.45.0.42 → 10.99.0.7 ; len=52 ttl=64 proto=TCP(6)
  header csum = 0x7A36
  Paquet (52 octets) :
  0000: 45 00 00 34 ab cd 40 00 40 06 7a 36 0a 2d 00 2a  E..4..@.@.z6.-.*
  0010: 0a 63 00 07 c0 00 1f 90 12 34 56 78 87 65 43 21  .c.......4Vx.eC!
  0020: 50 18 20 00 46 13 00 00 7b 22 72 65 73 75 6c 74  P. .F...{"result
  0030: 22 3a 32 7d                                      ":2}

========================================================================
  NIVEAU 6 — Trame Ethernet
========================================================================
  02:00:00:aa:bb:01 → 02:00:00:cc:dd:fe ; EtherType=0x0800 (IPv4)
  FCS (CRC32) = 0xB84FB35B
  Trame (70 octets) :
  0000: 02 00 00 cc dd fe 02 00 00 aa bb 01 08 00 45 00  ..............E.
  0010: 00 34 ab cd 40 00 40 06 7a 36 0a 2d 00 2a 0a 63  .4..@.@.z6.-.*.c
  0020: 00 07 c0 00 1f 90 12 34 56 78 87 65 43 21 50 18  .......4Vx.eC!P.
  0030: 20 00 46 13 00 00 7b 22 72 65 73 75 6c 74 22 3a   .F...{"result":
  0040: 32 7d 5b b3 4f b8                                2}[.O.

========================================================================
  NIVEAU 7 — Pile RAN LTE Uu : Milenage AKA + PDCP / RLC / MAC / CRC
========================================================================
  Paramètres sécurité (TS 33.401, vraie chaîne Milenage) :
    IMSI = 310150123456789  (MCC=310, MNC=15 → PLMN=13f051)
    K    = 00112233445566778899aabbccddeefe
    OP   = cdc202d5123e20f62b6d676ac72cb318
    OPC  = 2a29d90dce2519b17f1339be05c109c6  ← AES_K(OP) ⊕ OP
    RAND = 23553cbe9637a89d218ae64dae47bf35
    SQN  = ff9bb4d0b607    AMF = 8000
    RNTI = 0x4601

  Étape 1 — Milenage (CryptoMobile) :
    MAC-A = 3c859da46d256235  ← f1(K, RAND, SQN, AMF)
    RES   = 875793157979bfe0              ← f2
    CK    = 9cbc64df0cf94b733bef8c762f731e8d  ← f3
    IK    = 591197deddda8703deae0142b5b97819  ← f4
    AK    = 1086a32086e9                       ← f5
  Étape 2 — AUTN = (SQN⊕AK) || AMF || MAC-A :
    SQN⊕AK = ef1d17f030ee
    AUTN   = ef1d17f030ee80003c859da46d256235
  Étape 3 — K_ASME (TS 33.401 A.2, FC=0x10) :
    00bdee72b7446012cbe974b3ac9a110b3542cc24bb0cb6c6dc1dba95cdc4bdbd
  Étape 4 — K_eNB (A.3, FC=0x11, NAS_UL_COUNT=0) :
    6afc487fff07d26e33a2eabf41b9d55b3fa909d5da124e77ae5bc1d09284d519
  Étape 5 — K_UPenc (A.7, FC=0x15, P0=0x05, P1=EEA1) [128 LSB] :
    d8746cdfc0c05bc0c308a2cebc3ac51d

  PDCP SN=0x123, COUNT=0x00000123 (HFN=0x0000)
  AES-128-CTR chiffrement → PDU 54 octets :
    0000: 01 23 f5 66 3a 05 8b 42 6b 32 38 04 42 01 c5 33  .#.f:..Bk28.B..3
    0010: d5 3c 78 f5 c8 a7 ce 81 2a 62 3f a6 67 29 62 df  .<x.....*b?.g)b.
    0020: 9d e8 8c e9 71 d9 53 98 22 48 11 ce 66 e5 cf b8  ....q.S."H..f...
    0030: 22 8d 1e 5a dd ca                                "..Z..

  RLC UM : SN=0x123, PDU 56 octets
  MAC subheader (TS 36.321 §6.1.2) : LCID=1, L=56
    octets header = 0138  (R=0 F=0 E=0 LCID=0x01)
    PDU 58 octets

  CRC-24A = 0xF3A02E
  Transport Block (61 octets = 488 bits) :
    0000: 01 38 01 23 01 23 f5 66 3a 05 8b 42 6b 32 38 04  .8.#.#.f:..Bk28.
    0010: 42 01 c5 33 d5 3c 78 f5 c8 a7 ce 81 2a 62 3f a6  B..3.<x.....*b?.
    0020: 67 29 62 df 9d e8 8c e9 71 d9 53 98 22 48 11 ce  g)b.....q.S."H..
    0030: 66 e5 cf b8 22 8d 1e 5a dd ca f3 a0 2e           f..."..Z.....

========================================================================
  NIVEAU 8 — Codage convolutif rate-1/3 (commpy) + scrambling Gold (TS 36.211 §7.2)
========================================================================
  Codeur convolutif : g=(13,15,17)₈, K=4, rate=1/3
  TB = 488 bits → coded = 1473 bits (rate effectif 0.331)
  ⚠️  Substitut pédagogique au turbo 3GPP (TS 36.212 §5.1.3, RSC×2 + QPP).
      Même principe à treillis ; vraie lib (commpy) ; Viterbi en RX.

  Dimensionnement grid : n_prb=3 (forcé par coded_len), bits_avail=1728, padding=255
  Scrambling LTE Gold (Nc=1600) :
    c_init = 0x11804601  (RNTI=0x4601, subframe=3, PCI=1)
    Premiers 32 bits scramblés : 10010011100011000101101110111110

========================================================================
  NIVEAU 9 — Mapping 16-QAM (TS 36.211 §7.1.3, Gray normalisé √10)
========================================================================
  432 symboles 16-QAM
  Premiers 8 symboles :
    [0] bits=1001 → s = -0.3162 +0.9487j  |s|=1.0000
    [1] bits=0011 → s = +0.9487 +0.9487j  |s|=1.3416
    [2] bits=1000 → s = -0.3162 +0.3162j  |s|=0.4472
    [3] bits=1100 → s = -0.3162 -0.3162j  |s|=0.4472
    [4] bits=0101 → s = +0.3162 -0.9487j  |s|=1.0000
    [5] bits=1011 → s = -0.9487 +0.9487j  |s|=1.3416
    [6] bits=1011 → s = -0.9487 +0.9487j  |s|=1.3416
    [7] bits=1110 → s = -0.9487 -0.3162j  |s|=1.0000
  E[|s|²] = 0.9852  (cible 1.0)

  Démo soft demap (max-log-MAP, σ²=1) — LLRs des 4 premiers symboles :
    [0] LLR(b0..b3) = [ -1.265,  +3.795,  +1.265,  -1.265]  → bits durs = [1, 0, 0, 1]
    [1] LLR(b0..b3) = [ +3.795,  +3.795,  -1.265,  -1.265]  → bits durs = [0, 0, 1, 1]
    [2] LLR(b0..b3) = [ -1.265,  +1.265,  +1.265,  +1.265]  → bits durs = [1, 0, 0, 0]
    [3] LLR(b0..b3) = [ -1.265,  -1.265,  +1.265,  +1.265]  → bits durs = [1, 1, 0, 0]

========================================================================
  NIVEAU 9.5 — PSS Zadoff-Chu (TS 36.211 §6.11.1) — illustration
========================================================================
  N_ID_2 = 1  (PCI=1 mod 3) → u = {25,29,34}[1]
  Séquence Zadoff-Chu longueur 62 (E[|d|²] = 1.0000)
  Auto-corrélation circulaire (peak/sidelobe) :
    peak = 62.000, max sidelobe = 12.243, ratio = 5.06
  Premiers 4 échantillons : [ 1.        +0.j         -0.96907729-0.2467574j  -0.73305187-0.68017274j
  0.07473009+0.9972038j ]
  ✓ Injectée par L10 dans le 1er symbole OFDM (SCs center±31 autour de DC, TS 36.211 §6.11.1.2).

========================================================================
  NIVEAU 10 — OFDM : 1 sym PSS (sync) + N sym data, IFFT + CP
========================================================================
  Symbole 0 (PSS) : ZC u={25,29,34}[N_ID_2=1], placée aux SCs center±31 (62 SCs autour de DC)
                    → en vrai LTE, PSS est au sym 6 du slot 0 ; ici en tête pour pédagogie (sync préambule)
  N_FFT=2048, CP=144, n_sc data actives=36 (n_prb=3)
  fs=30.72 MS/s, T_sym(+CP)=71.35 µs
  Total : 1 PSS + 12 data = 13 symboles OFDM (durée = 927.60 µs)
  Premiers 8 échantillons I/Q du symbole PSS (après CP) :
    n=0  I=-0.15078  Q=+0.09228  |s|=0.17678
    n=1  I=-0.15031  Q=+0.09214  |s|=0.17631
    n=2  I=-0.14920  Q=+0.09128  |s|=0.17491
    n=3  I=-0.14745  Q=+0.08969  |s|=0.17259
    n=4  I=-0.14507  Q=+0.08739  |s|=0.16936
    n=5  I=-0.14208  Q=+0.08438  |s|=0.16524
    n=6  I=-0.13848  Q=+0.08068  |s|=0.16027
    n=7  I=-0.13431  Q=+0.07630  |s|=0.15447

========================================================================
  NIVEAU 11 — Chaîne RF (GNU Radio) : interp + filtre + upconv IF + vérif
========================================================================
  Paramètres :
    fs_in           = 30.72 MS/s   (sortie L10)
    interp_factor   = ×4
    fs_out          = 122.88 MS/s
    f_IF            = 5.00 MHz   (upconv digital)
    f_c (RF final)  = 1747.50 MHz   ← upconv analogique via SDR
    P_TX consigne   = 23 dBm
    n_taps filtre   = 101

  TX RF : scipy fallback (resample_poly + numpy LO complexe)
  Sortie : 113984 samples complexes à 122.88 MS/s (927.6 µs)

  Premiers 8 échantillons I/Q après chaîne RF complète :
    n=0  I=-0.01718  Q=-0.03157  |s|=0.03594
    n=1  I=-0.00769  Q=-0.04039  |s|=0.04111
    n=2  I=+0.00605  Q=-0.04278  |s|=0.04321
    n=3  I=+0.02033  Q=-0.03836  |s|=0.04341
    n=4  I=+0.03239  Q=-0.02886  |s|=0.04338
    n=5  I=+0.04098  Q=-0.01661  |s|=0.04422
    n=6  I=+0.04633  Q=-0.00313  |s|=0.04643
    n=7  I=+0.04850  Q=+0.01119  |s|=0.04977

  Vérif spectre (FFT 8192 samples) :
    Pic spectral à +5.14 MHz  (attendu ~+5.00 MHz)

  Boucle TX RF → RX RF (vérification d'invertibilité) :
    Downconv (LO conjugué) + decim ÷4 → 28496 samples baseband
    max|err| full       = 1.09e-02  (inclut transitoires bords)
    max|err| middle     = 6.94e-03  [⚠ écart résiduel]

  Note : L13 continue à utiliser le baseband direct (fs_in) ; en vrai pipeline,
         le SDR RX downconverterait le signal réel à 1.7 GHz vers baseband.
         Pour exporter vers fichier IQ (HackRF/USRP) : np.save("tx.iq", x_rf).

========================================================================
  NIVEAU 12 — Bilan de liaison Friis (UE → eNB)
========================================================================
  d=500 m, λ=17.17 cm
  L_FS=91.3 dB + L_excess=30 dB → L_total=121.3 dB
  P_r = 23+0+17−121.3 = -81.3 dBm
  N_sys = -98.0 dBm → SNR ≈ 16.7 dB

  🔧 Application des overrides RX (avant L13) :
     cfg_rx["k"] : '00112233445566778899AABBCCDDEEFE'  →  '00112233445566778899AABBCCDDEEFE'

========================================================================
  NIVEAU 13 — Décap RX indépendante (SNR=∞ dB, demap=hard)
========================================================================
  Canal AWGN désactivé (SNR ≥ 300 dB)
  PSS sync   : pic corrélation à sample 144 (attendu 144, écart=+0)
             amplitude=62.00, N_ID_2_essai=1
  L10 skip   : 1er symbole OFDM (PSS) écarté → 26304 samples data
  L10 inverse : 12 FFT data → 432 symboles 16-QAM
  L9  inverse : démap hard → 1728 bits
  L8  inverse : descramble (c_init=0x11804601 regénérée depuis cfg)
  L8          : Viterbi rate-1/3 → 488 TB bits (coded_len déduit de DCI.tb_byte_len=61)
  L7  CRC-24A : 0xF3A02E vs 0xF3A02E  [OK]
  L7  MAC parsed : LCID=1, L=56
  L7  PDCP header : SN=0x123 (lue depuis octets reçus)
  L7  K_UPenc (re-dérivée côté RX, AKA complète) :
        d8746cdfc0c05bc0c308a2cebc3ac51d
        ↑ HSS détient K, MME reçoit K_ASME, eNB reçoit K_eNB via S1AP,
          puis dérive K_UPenc. Ici on simule en re-faisant la chaîne complète.
  L7  COUNT reconstruit : (HFN=0x0000 << 12) | SN=0x123 = 0x00000123
  L7  AES-128-CTR déchiffrement → IP 52 octets
  L5  IPv4 parsed : version=4, IHL=5
  L4  TCP parsed : data_offset=5, payload 12 octets

  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
  ┃  Payload JSON décodé du flux RX : b'{"result":2}'              ┃
  ┃  result_rx = 2            (attendu : 2)                  ┃
  ┃  ✅ MATCH : le « 2 » a réellement traversé la pile               ┃
  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

========================================================================
  NIVEAU 14 — Glyph "2" rastérisé (1 × bitmap 8×8) [depuis result_rx, pas depuis L1]
========================================================================
  Représentation visuelle (█ = pixel ON, · = pixel OFF) :
    ········ 
    ··███··· 
    ····█··· 
    ····█··· 
    ···█···· 
    ··█····· 
    ··███··· 
    ········ 

  Total pixels allumés : 10 sur 64

========================================================================
  NIVEAU 15 — Sous-pixel OLED : diode Shockley + Rs (boucle bouclée)
========================================================================
  Modèle : I = Is·(exp(V_d/(n·VT)) − 1)  ;  V = V_d + I·Rs
    V = 3.0 V  ;  Is = 1.00e-12 A  ;  n = 2.0  ;  VT = 25.85 mV (T=300.0 K)  ;  Rs = 10.0 kΩ
  Résolution bisection :
    V_diode  = 988.56 mV
    V_Rs     = 2011.44 mV  (chute IR sur Rs)
    I_pixel  = 201.144 µA
    P_pixel  = V·I = 603.433 µW
  10 pixels ON × 3 sous-pixels = 30 sous-pixels
    I_total = 6.034 mA   P_total = 18.103 mW

  ┌──────────────────────────────────────────────────────────────────┐
  │  TX (L0)  : MOSFET en saturation, I_D ≈ µA (modèle quadratique)  │
  │  RX (L15) : Shockley + Rs, I_pixel =  201.14 µA               │
  │  Deux régimes physiques distincts, deux équations distinctes.    │
  │  Sans Rs, Shockley nu diverge à V > V_th ; Rs auto-limite.       │
  └──────────────────────────────────────────────────────────────────┘

========================================================================
  ✅ Trace complète : 1 + 1 = 2
  🔍 Décodage RX indépendant : result_rx = 2 ≡ attendu (2)
========================================================================
  ```
