#!/usr/bin/env bash
# test_chain.sh — vérifie l'intégrité de la chaîne pile_trace.py
#
# Modes :
#   ./test_chain.sh              28 tests essentiels (~30 s)
#   ./test_chain.sh --full       100+ tests exhaustifs (~3 min)
#   ./test_chain.sh --verbose    affiche SNR/CRC/result_rx par test
#   ./test_chain.sh -f -v        full + verbose (le tout)
#   ./test_chain.sh --help       ce message

set -u

USAGE="Usage: $0 [--full|-f] [--verbose|-v] [--help|-h]

Modes :
  (défaut)        : 28 tests essentiels (~30 s)
  --full, -f      : 100+ tests exhaustifs (~3 min)
  --verbose, -v   : pour chaque test, affiche les paramètres clés
                    (SNR Friis, SNR effectif, CRC, result_rx, niveau qui rate)
  --help, -h      : ce message
"

MODE="quick"
VERBOSE=0
for arg in "$@"; do
    case "$arg" in
        --full|-f)    MODE="full" ;;
        --verbose|-v) VERBOSE=1 ;;
        -h|--help)    echo "$USAGE"; exit 0 ;;
        *)            echo "Arg inconnu: $arg"; echo "$USAGE"; exit 1 ;;
    esac
done

SCRIPT="python3 pile_trace.py pile_values.csv"
TMP=$(mktemp)
trap "rm -f $TMP" EXIT

PASS=0
FAIL=0

# ─── Helpers ────────────────────────────────────────────────────────────────

run_test() {
    local desc="$1"
    local expected="$2"
    shift 2
    local args="$*"
    local got

    if [[ $VERBOSE -eq 1 ]]; then
        # Run complet (sans --check) pour récupérer la sortie détaillée
        eval "$SCRIPT $args" > "$TMP" 2>&1
        if grep -qE 'MATCH : le « .+ » a réellement traversé' "$TMP"; then
            got="OK"
        else
            got="FAIL"
        fi
    else
        # Run silencieux avec --check (plus rapide)
        eval "$SCRIPT $args --check" > "$TMP" 2>&1
        if [[ $? -eq 0 ]]; then got="OK"; else got="FAIL"; fi
    fi

    if [[ "$got" == "$expected" ]]; then
        if [[ "$expected" == "OK" ]]; then
            printf "  ✅  %s\n" "$desc"
        else
            printf "  ✅  %s  (échec attendu)\n" "$desc"
        fi
        PASS=$((PASS+1))
        [[ $VERBOSE -eq 1 ]] && verbose_show
    else
        printf "  ❌  %s  (attendu=%s, obtenu=%s)\n" "$desc" "$expected" "$got"
        FAIL=$((FAIL+1))
        verbose_show   # toujours en cas d'échec inattendu
    fi
}

verbose_show() {
    # Extrait des infos clés depuis $TMP (la sortie de pile_trace.py).
    local snr_friis snr_effective crc_status pss_pic result_rx fail_layers

    snr_friis=$(grep -oP 'SNR ≈ \K[+-]?[0-9.]+ dB' "$TMP" | head -1)
    snr_effective=$(grep -oP '(?:SNR canal AWGN = |L13 forcé à )\K[+-]?[0-9.]+\s*dB' "$TMP" | head -1)
    crc_status=$(grep -oP 'CRC-24A : 0x[0-9A-Fa-f]+ vs 0x[0-9A-Fa-f]+\s+\[\K\w+' "$TMP" | head -1)
    pss_pic=$(grep -oP 'pic corrélation à sample \K\d+\s+\(attendu \d+, écart=[+-]?\d+\)' "$TMP" | head -1)
    result_rx=$(grep -oP 'result_rx = \K\S+' "$TMP" | head -1)
    fail_layers=$(grep -oP 'Décodage RX a échoué : \K.+' "$TMP" | head -1)

    local line=""
    [[ -n "$snr_friis"     ]] && line+="Friis=$snr_friis  "
    [[ -n "$snr_effective" ]] && line+="AWGN=$snr_effective  "
    [[ -n "$pss_pic"       ]] && line+="PSS=$pss_pic  "
    [[ -n "$crc_status"    ]] && line+="CRC=$crc_status  "
    [[ -n "$result_rx"     ]] && line+="rx=$result_rx  "
    [[ -n "$fail_layers"   ]] && line+="failed=$fail_layers"

    [[ -n "$line" ]] && printf "       │ %s\n" "$line"
}

section() {
    printf "\n  %s\n  ────────────────────────────────────────────────────\n" "$1"
}

# ─── Header ─────────────────────────────────────────────────────────────────

printf "\n╔══════════════════════════════════════════════════════════╗\n"
printf "║  🧪  Test d'intégrité de la chaîne pile_trace.py        ║\n"
if [[ "$MODE" == "full" ]]; then
    printf "║      Mode : FULL exhaustif"
else
    printf "║      Mode : QUICK essentiel"
fi
[[ $VERBOSE -eq 1 ]] && printf "  +  VERBOSE"
printf "\n╚══════════════════════════════════════════════════════════╝\n"

START=$SECONDS

# ═══════════════════════════════════════════════════════════════════════════
# TESTS QUICK (toujours exécutés)
# ═══════════════════════════════════════════════════════════════════════════

section "🧮  Round-trip nominal (Friis pilote le canal)"
run_test "1+1   → 2"                  OK  "1+1"
run_test "0+0   → 0 (cas limite)"     OK  "0+0"
run_test "16+16 → 32 (2 chiffres)"    OK  "16+16"
run_test "999+1 → 1000 (3 chiffres)"  OK  "999+1"

section "📡  SNR override — limites du décodeur"
run_test "SNR ∞ (300 dB)        → décodage parfait" OK   "1+1 --snr-db 300"
run_test "SNR confortable 25 dB → décodage OK"      OK   "1+1 --snr-db 25"
run_test "SNR limite 18 dB      → décodage OK"      OK   "1+1 --snr-db 18"
run_test "SNR -10 dB            → décodage CASSE"   FAIL "1+1 --snr-db -10"
run_test "SNR -20 dB            → décodage CASSE"   FAIL "1+1 --snr-db -20"

section "📶  Bilan Friis — la distance pilote le canal"
run_test "Distance 100 m          (SNR Friis confortable)" OK   "1+1 --distance 100"
run_test "Distance 500 m default  (SNR Friis ≈ 17 dB)"     OK   "1+1 --distance 500"
run_test "Distance 50 km          (SNR Friis très bas)"    FAIL "1+1 --distance 50000"

section "🔒  Sécurité AKA — désynchroniser RX casse le décodage"
run_test "K override RX (clé maître différente)" \
    FAIL "1+1 --rx-override k=00000000000000000000000000000000"
run_test "RAND override RX (challenge différent)" \
    FAIL "1+1 --rx-override rand=00000000000000000000000000000000"
run_test "SQN override RX (compteur différent)" \
    FAIL "1+1 --rx-override sqn=000000000000"
run_test "OP override RX (opérateur différent)" \
    FAIL "1+1 --rx-override op=00000000000000000000000000000000"

section "📻  Scrambling LTE — RNTI/PCI différent casse le descramble"
run_test "RNTI override RX (cinit différent)" \
    FAIL "1+1 --rx-override rnti=0x9999"
run_test "PCI override RX (cinit différent)" \
    FAIL "1+1 --rx-override pci=42"
run_test "subframe override RX (cinit différent)" \
    FAIL "1+1 --rx-override subframe=7"

section "✨  Overrides CLI symétriques (TX+RX alignés)"
run_test "RNTI custom (les 2 côtés)" OK "1+1 --rnti 0xCAFE"
run_test "PCI custom (les 2 côtés)"  OK "1+1 --pci 100"
run_test "IMSI custom (PLMN différent, KDF cohérent)" \
    OK "1+1 --imsi 208010000000001"
run_test "Distance + puissance combinés (link budget cohérent)" \
    OK "1+1 --distance 200 --p-tx 30"
run_test "Combo total (PHY + crypto + RF tous changés)" \
    OK "1+1 --distance 300 --p-tx 25 --pci 42 --rnti 0xBABE --imsi 310410000000001"

section "🔗  Chaînage L12 → L13 vérifié dans la sortie"
{
    eval "$SCRIPT 1+1" > "$TMP" 2>&1
    if grep -q "Chaînage L12 → L13" "$TMP"; then
        line=$(grep "Chaînage L12 → L13" "$TMP" | head -1 | sed 's/^[[:space:]]*//')
        printf "  ✅  Sans --snr-db : Friis pilote le canal AWGN\n"
        printf "       │ %s\n" "$line"
        PASS=$((PASS+1))
    else
        printf "  ❌  Pattern \"Chaînage L12 → L13\" introuvable\n"
        FAIL=$((FAIL+1))
    fi

    eval "$SCRIPT 1+1 --snr-db -5" > "$TMP" 2>&1
    if grep -q "Override SNR" "$TMP"; then
        line=$(grep "Override SNR" "$TMP" | head -1 | sed 's/^[[:space:]]*//')
        printf "  ✅  Avec --snr-db : override explicite signalé\n"
        printf "       │ %s\n" "$line"
        PASS=$((PASS+1))
    else
        printf "  ❌  Pattern \"Override SNR\" introuvable\n"
        FAIL=$((FAIL+1))
    fi
}

section "🎯  Démap soft LLR (chemin alternatif)"
run_test "Soft demap, canal propre"  OK   "1+1 --snr-db 25 --soft-demap"
run_test "Soft demap, canal pourri"  FAIL "1+1 --snr-db -15 --soft-demap"

# ═══════════════════════════════════════════════════════════════════════════
# TESTS FULL (uniquement si --full)
# ═══════════════════════════════════════════════════════════════════════════

if [[ "$MODE" == "full" ]]; then

section "📊  SNR sweep — caractérisation du point de bascule (hard demap)"
for snr in 30 20 15 12 10 8 6 4 0; do
    run_test "SNR = ${snr} dB" OK "1+1 --snr-db $snr"
done
for snr in -10 -15 -20 -25; do
    run_test "SNR = ${snr} dB" FAIL "1+1 --snr-db $snr"
done

section "📏  Distance sweep — Friis pilote l'AWGN"
for d in 50 100 250 500 1000 2000; do
    run_test "Distance = ${d} m"    OK   "1+1 --distance $d"
done
for d in 20000 50000 100000; do
    run_test "Distance = ${d} m"    FAIL "1+1 --distance $d"
done

section "📦  Tailles TB variées (auto-dim n_prb)"
run_test "0+0 (1 chiffre)"                      OK "0+0"
run_test "99+1 → 100 (3 chiffres)"              OK "99+1"
run_test "9999+1 → 10000 (5 chiffres)"          OK "9999+1"
run_test "99999+1 → 100000 (6 chiffres)"        OK "99999+1"
run_test "12345+67890 → 80235 (5 chiffres)"     OK "12345+67890"

section "🔐  Crypto — chaque paramètre AKA en RX override (doit casser)"
run_test "K = all-zero"        FAIL "1+1 --rx-override k=00000000000000000000000000000000"
run_test "K = all-FF"          FAIL "1+1 --rx-override k=ffffffffffffffffffffffffffffffff"
run_test "OP = all-zero"       FAIL "1+1 --rx-override op=00000000000000000000000000000000"
run_test "RAND modifié"        FAIL "1+1 --rx-override rand=11111111111111111111111111111111"
run_test "SQN = 0"             FAIL "1+1 --rx-override sqn=000000000000"
run_test "AMF = 0000 (pas vérifié, AMF ne sert qu_à MAC-A non implémenté)"   OK   "1+1 --rx-override amf=0000"
run_test "NAS count modifié"   FAIL "1+1 --rx-override nas_ul_count=42"

section "🔓  Combos d'overrides RX (tous casser)"
run_test "K + RAND modifiés ensemble" FAIL \
    "1+1 --rx-override k=00000000000000000000000000000000 --rx-override rand=00000000000000000000000000000000"
run_test "RNTI + PCI modifiés ensemble" FAIL \
    "1+1 --rx-override rnti=0xABCD --rx-override pci=200"
run_test "Tout cassé (crypto + PHY)" FAIL \
    "1+1 --rx-override k=00000000000000000000000000000000 --rx-override rnti=0xDEAD --rx-override pci=100"

section "🛰️   PHY edges symétriques (TX+RX alignés)"
run_test "PCI = 0 (minimum)"           OK "1+1 --pci 0"
run_test "PCI = 503 (max LTE)"         OK "1+1 --pci 503"
run_test "RNTI = 0x0001 (min)"         OK "1+1 --rnti 0x0001"
run_test "RNTI = 0xFFFD (proche max)"  OK "1+1 --rnti 0xFFFD"
run_test "subframe = 0"                OK "1+1 --subframe 0"
run_test "subframe = 9 (max)"          OK "1+1 --subframe 9"
run_test "N_ID_2 = 0 (PSS u=25)"       OK "1+1 --n-id-2 0"
run_test "N_ID_2 = 2 (PSS u=34)"       OK "1+1 --n-id-2 2"

section "📡  Différentes bandes RF (path loss change avec λ)"
run_test "f_c = 700 MHz (B12 low)"     OK "1+1 --f-carrier 700e6"
run_test "f_c = 900 MHz (GSM900)"      OK "1+1 --f-carrier 900e6"
run_test "f_c = 2100 MHz (B1)"         OK "1+1 --f-carrier 2.1e9"
run_test "f_c = 2600 MHz (B7)"         OK "1+1 --f-carrier 2.6e9"
run_test "f_c = 3500 MHz (n78 5G)"     OK "1+1 --f-carrier 3.5e9"

section "📶  Variation puissance / gains antenne"
run_test "P_TX = 0 dBm  + d=100 m"     OK   "1+1 --p-tx 0 --distance 100"
run_test "P_TX = 30 dBm + d=5 km"      OK   "1+1 --p-tx 30 --distance 5000"
run_test "P_TX = -10 dBm + d=500 m"    FAIL "1+1 --p-tx -10 --distance 500"
run_test "G_RX = 0 dBi   + d=500 m"    OK   "1+1 --g-rx 0"
run_test "Path loss excess = 0 dB"     OK   "1+1 --path-loss 0"
run_test "Path loss excess = 100 dB"   FAIL "1+1 --path-loss 100"

section "🔧  RF chain — interp, fréquence IF, filtre"
run_test "rf_interp = 2 (×2 au lieu de ×4)" OK "1+1 --rf-interp 2"
run_test "rf_interp = 8 (×8)"               OK "1+1 --rf-interp 8"
run_test "f_IF = 1 MHz"                     OK "1+1 --f-if 1e6"
run_test "f_IF = 10 MHz"                    OK "1+1 --f-if 10e6"
run_test "rf_taps = 51 (plus court)"        OK "1+1 --rf-taps 51"
run_test "rf_taps = 201 (plus long)"        OK "1+1 --rf-taps 201"

section "💡  OLED Shockley — variation Rs et tension"
run_test "OLED V = 2.5 V (sous-tension)"    OK "1+1 --oled-v 2.5"
run_test "OLED V = 4.0 V (sur-tension)"     OK "1+1 --oled-v 4.0"
run_test "OLED Rs = 1 kΩ (faible)"          OK "1+1 --oled-rs 1000"
run_test "OLED Rs = 100 kΩ (élevée)"        OK "1+1 --oled-rs 100000"
run_test "OLED T = 250 K (-23 °C froid)"    OK "1+1 --oled-temp 250"
run_test "OLED T = 350 K (+77 °C chaud)"    OK "1+1 --oled-temp 350"

section "⚡  MOSFET (silicium TX, n'affecte pas le décodage)"
run_test "VDD core = 0.5 V (low)"           OK "1+1 --vdd-core 0.5"
run_test "VDD core = 1.2 V (high)"          OK "1+1 --vdd-core 1.2"
run_test "Vth = 0.3 V (rapide)"             OK "1+1 --vth 0.3"
run_test "W/L = 1"                          OK "1+1 --w-l 1"
run_test "W/L = 10"                         OK "1+1 --w-l 10"

section "🎯  Soft demap — gain par rapport au hard"
run_test "Soft, SNR = 10 dB"    OK   "1+1 --snr-db 10 --soft-demap"
run_test "Soft, SNR = 5 dB"     OK   "1+1 --snr-db 5 --soft-demap"
run_test "Soft, SNR = 0 dB"     OK   "1+1 --snr-db 0 --soft-demap"
run_test "Soft, SNR = -5 dB"    OK   "1+1 --snr-db -5 --soft-demap"
run_test "Soft, SNR = -15 dB"   FAIL "1+1 --snr-db -15 --soft-demap"
run_test "Soft, SNR = -25 dB"   FAIL "1+1 --snr-db -25 --soft-demap"

section "🌐  Réseau IP/MAC/TCP (changement transparent pour décap)"
run_test "Autre IP src"     OK "1+1 --src-ip 192.168.42.1"
run_test "Autre IP dst"     OK "1+1 --dst-ip 1.1.1.1"
run_test "Autre MAC src"    OK "1+1 --src-mac de:ad:be:ef:00:01"
run_test "Port src custom"  OK "1+1 --src-port 12345 --dst-port 443"
run_test "TCP SEQ 0x0"      OK "1+1 --tcp-seq 0x0"

fi  # ─── fin du bloc --full ────────────────────────────────────────────────

# ─── Bilan final ───────────────────────────────────────────────────────────

ELAPSED=$((SECONDS - START))
TOTAL=$((PASS + FAIL))

printf "\n╔══════════════════════════════════════════════════════════╗\n"
if [[ $FAIL -eq 0 ]]; then
    printf "║  🎉  TOUS LES TESTS PASSENT : %3d/%3d  (en %3ds)       ║\n" "$PASS" "$TOTAL" "$ELAPSED"
    printf "║                                                          ║\n"
    printf "║  ✅  Chaîne complète vérifiée :                         ║\n"
    printf "║      • round-trip OK quand TX/RX alignés                ║\n"
    printf "║      • décodage casse quand on désaligne quoi que ce soit║\n"
    printf "║      • Friis pilote vraiment le canal AWGN              ║\n"
    printf "║      • override SNR fait bien override                  ║\n"
    if [[ "$MODE" == "full" ]]; then
    printf "║      • tous les paramètres du CSV exposés en CLI        ║\n"
    printf "║      • caractérisation point de bascule SNR / distance  ║\n"
    fi
    printf "╚══════════════════════════════════════════════════════════╝\n\n"
    exit 0
else
    printf "║  ⚠️   RÉSULTAT : %3d OK / %2d échecs sur %3d  (en %3ds)║\n" "$PASS" "$FAIL" "$TOTAL" "$ELAPSED"
    printf "║                                                          ║\n"
    printf "║  Relance avec --verbose pour voir le détail des échecs   ║\n"
    printf "╚══════════════════════════════════════════════════════════╝\n\n"
    exit 1
fi
