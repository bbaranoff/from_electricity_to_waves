#!/usr/bin/env bash
# test_chain.sh — vérifie l'intégrité de la chaîne pile_trace.py
#
# Lance pile_trace.py dans des configurations variées et vérifie que
# le comportement attendu se produit :
#   - décodage OK quand la chaîne est cohérente (TX/RX alignés, SNR suffisant)
#   - décodage CASSE quand on désynchronise quelque chose (override RX, SNR pourri)
#
# Usage :  ./test_chain.sh
#          ./test_chain.sh --verbose    # affiche les sorties des échecs

set -u

SCRIPT="python3 pile_trace.py pile_values.csv"
TMP=$(mktemp)
trap "rm -f $TMP" EXIT

PASS=0
FAIL=0
VERBOSE=0
[[ "${1:-}" == "--verbose" || "${1:-}" == "-v" ]] && VERBOSE=1

# ─── Helpers ────────────────────────────────────────────────────────────────

run_test() {
    local desc="$1"          # description humaine
    local expected="$2"      # "OK" ou "FAIL"
    shift 2
    local args="$*"          # args passés à pile_trace.py

    # mode --check : silencieux, exit 0 si décodage OK, 1 sinon
    eval "$SCRIPT $args --check" > "$TMP" 2>&1
    local got_exit=$?

    local got
    if [[ $got_exit -eq 0 ]]; then got="OK"; else got="FAIL"; fi

    if [[ "$got" == "$expected" ]]; then
        if [[ "$expected" == "OK" ]]; then
            printf "  ✅  %s\n" "$desc"
        else
            printf "  ✅  %s  (échec attendu, chaîne refuse l'incohérence)\n" "$desc"
        fi
        PASS=$((PASS+1))
    else
        printf "  ❌  %s  (attendu=%s, obtenu=%s)\n" "$desc" "$expected" "$got"
        if [[ $VERBOSE -eq 1 ]]; then
            sed 's/^/        | /' "$TMP" | head -10
        fi
        FAIL=$((FAIL+1))
    fi
}

check_in_output() {
    local desc="$1"
    local pattern="$2"
    shift 2
    local args="$*"

    eval "$SCRIPT $args" > "$TMP" 2>&1
    if grep -q -- "$pattern" "$TMP"; then
        local line
        line=$(grep -- "$pattern" "$TMP" | head -1 | sed 's/^[[:space:]]*//')
        printf "  ✅  %s\n      ↳ %s\n" "$desc" "$line"
        PASS=$((PASS+1))
    else
        printf "  ❌  %s  (motif \"%s\" introuvable dans la sortie)\n" "$desc" "$pattern"
        FAIL=$((FAIL+1))
    fi
}

section() {
    printf "\n  %s\n  ────────────────────────────────────────────────────\n" "$1"
}

# ─── Header ─────────────────────────────────────────────────────────────────

printf "\n╔══════════════════════════════════════════════════════════╗\n"
printf "║  🧪  Test d'intégrité de la chaîne pile_trace.py        ║\n"
printf "╚══════════════════════════════════════════════════════════╝\n"

START=$SECONDS

# ─── Section 1 : round-trip nominal ─────────────────────────────────────────

section "🧮  Round-trip nominal (Friis pilote le canal)"
run_test "1+1   → 2"              OK  "1+1"
run_test "0+0   → 0 (cas limite)" OK  "0+0"
run_test "16+16 → 32 (2 chiffres)" OK "16+16"
run_test "999+1 → 1000 (3 chiffres)" OK "999+1"

# ─── Section 2 : SNR canal (override de Friis) ─────────────────────────────

section "📡  SNR override — limites du décodeur"
run_test "SNR ∞ (300 dB)        → décodage parfait"       OK   "1+1 --snr-db 300"
run_test "SNR confortable 25 dB → décodage OK"            OK   "1+1 --snr-db 25"
run_test "SNR limite 18 dB      → décodage OK"            OK   "1+1 --snr-db 18"
run_test "SNR -5 dB             → décodage CASSE"         FAIL "1+1 --snr-db -10"
run_test "SNR très pourri -15 dB → décodage CASSE"        FAIL "1+1 --snr-db -15"

# ─── Section 3 : bilan de liaison Friis ────────────────────────────────────

section "📶  Bilan Friis — la distance pilote le canal"
run_test "Distance 100 m         (SNR Friis confortable)" OK   "1+1 --distance 100"
run_test "Distance 500 m default (SNR Friis ≈ 17 dB)"     OK   "1+1 --distance 500"
run_test "Distance 50 km         (SNR Friis ≈ -23 dB)"    FAIL "1+1 --distance 50000"

# ─── Section 4 : sécurité crypto — RX différent ≠ TX casse ─────────────────

section "🔒  Sécurité AKA — désynchroniser RX casse le décodage"
run_test "K override RX (clé maître différente)" \
    FAIL "1+1 --rx-override k=00000000000000000000000000000000"
run_test "RAND override RX (challenge différent)" \
    FAIL "1+1 --rx-override rand=00000000000000000000000000000000"
run_test "SQN override RX (compteur différent)" \
    FAIL "1+1 --rx-override sqn=000000000000"
run_test "OP override RX (opérateur différent)" \
    FAIL "1+1 --rx-override op=00000000000000000000000000000000"

# ─── Section 5 : identifiants PHY — RX différent casse ─────────────────────

section "📻  Scrambling LTE — RNTI/PCI différent casse le descramble"
run_test "RNTI override RX (cinit différent)" \
    FAIL "1+1 --rx-override rnti=0x9999"
run_test "PCI override RX (cinit différent)" \
    FAIL "1+1 --rx-override pci=42"
run_test "subframe override RX (cinit différent)" \
    FAIL "1+1 --rx-override subframe=7"

# ─── Section 6 : overrides CLI symétriques TX+RX → cohérent ────────────────

section "✨  Overrides CLI symétriques (TX+RX alignés)"
run_test "RNTI custom (les 2 côtés)" OK "1+1 --rnti 0xCAFE"
run_test "PCI custom (les 2 côtés)" OK "1+1 --pci 100"
run_test "IMSI custom (PLMN différent, KDF cohérent)" \
    OK "1+1 --imsi 208010000000001"
run_test "Distance + puissance combinés (link budget cohérent)" \
    OK "1+1 --distance 200 --p-tx 30"
run_test "Combo total (PHY + crypto + RF tous changés)" \
    OK "1+1 --distance 300 --p-tx 25 --pci 42 --rnti 0xBABE --imsi 310410000000001"

# ─── Section 7 : chaînage L12 → L13 dans la stdout ─────────────────────────

section "🔗  Chaînage L12 → L13 vérifié dans la sortie"
check_in_output \
    "Sans --snr-db : Friis pilote le canal AWGN" \
    "Chaînage L12 → L13" \
    "1+1"
check_in_output \
    "Avec --snr-db : override explicite signalé" \
    "Override SNR" \
    "1+1 --snr-db -10"

# ─── Section 8 : --soft-demap (chemin alternatif) ──────────────────────────

section "🎯  Démap soft LLR (chemin alternatif)"
run_test "Soft demap, canal propre" OK "1+1 --snr-db 25 --soft-demap"
run_test "Soft demap, canal pourri" FAIL "1+1 --snr-db -10 --soft-demap"

# ─── Bilan final ───────────────────────────────────────────────────────────

ELAPSED=$((SECONDS - START))
TOTAL=$((PASS + FAIL))

printf "\n╔══════════════════════════════════════════════════════════╗\n"
if [[ $FAIL -eq 0 ]]; then
    printf "║  🎉  TOUS LES TESTS PASSENT : %2d/%2d  (en %3ds)         ║\n" "$PASS" "$TOTAL" "$ELAPSED"
    printf "║                                                          ║\n"
    printf "║  ✅  Chaîne complète vérifiée :                         ║\n"
    printf "║      • round-trip OK quand TX/RX alignés                ║\n"
    printf "║      • décodage casse quand on désaligne quoi que ce soit║\n"
    printf "║      • Friis pilote vraiment le canal AWGN              ║\n"
    printf "║      • override SNR fait bien override                  ║\n"
    printf "╚══════════════════════════════════════════════════════════╝\n\n"
    exit 0
else
    printf "║  ⚠️   RÉSULTAT : %2d OK / %2d échecs sur %2d  (en %3ds)  ║\n" "$PASS" "$FAIL" "$TOTAL" "$ELAPSED"
    printf "║                                                          ║\n"
    printf "║  Relance avec --verbose pour voir la sortie des échecs   ║\n"
    printf "╚══════════════════════════════════════════════════════════╝\n\n"
    exit 1
fi
