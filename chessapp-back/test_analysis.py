"""
Script de prueba del endpoint /api/partidas/analysis-chain/
Envía las posiciones FEN de la partida al backend local y muestra los resultados.

Uso: python test_analysis.py
     python test_analysis.py --depth 3      (solo 3 movimientos por posición)
     python test_analysis.py --fens 0 4     (solo las posiciones 0 a 3)
"""

import argparse
import json
import sys
import requests

# ── Posiciones FEN de la partida (limpias y sin duplicados) ──────────────────
FENS = [
    # Pos 0  – Posición inicial
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    # Pos 1  – 1.e4
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
    # Pos 2  – 1...d5
    "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2",
    # Pos 3  – 2.Nf3
    "rnbqkbnr/ppp1pppp/8/3p4/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2",
    # Pos 4  – 2...dxe4
    "rnbqkbnr/ppp1pppp/8/8/3pP3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3",
    # Pos 5  – 3.c4 (gambito de dama)
    "rnbqkbnr/ppp1pppp/8/8/2PP4/5N2/PP2PPPP/RNBQKB1R b KQkq c3 0 3",
    # Pos 6  – 3...Qe5+
    "rnbqkbnr/ppp1pppp/8/8/2PPq3/5N2/PP2PPPP/RNBQKB1R w KQkq - 0 4",
    # Pos 7  – 4.Nc3
    "rnbqkbnr/ppp1pppp/8/8/2PPq3/2N2N2/PP2PPPP/R1BQKB1R b KQkq - 1 4",
    # Pos 8  – 4...g5
    "rnbqkbnr/ppp1pp1p/8/3p4/2PPq3/2N2N2/PP2PPPP/R1BQKB1R w KQkq d6 0 5",
    # Pos 9  – 5.e3
    "rnbqkbnr/ppp1pp1p/8/3p4/2PPq3/2N1PN2/PP3PPP/R1BQKB1R b KQkq - 0 5",
    # Pos 10 – 5...g4
    "rnbqkbnr/ppp1pp1p/8/3p2p1/2PPq3/2N1PN2/PP3PPP/R1BQKB1R w KQkq g6 0 6",
    # Pos 11 – 6.h4
    "rnbqkbnr/ppp1pp1p/8/3p2p1/2PPq3/2N1PN1R/PP3PP1/R1BQKB2 b Qkq - 1 6",
    # Pos 12 – 6...Nf6
    "rnbqkb1r/ppp1pp1p/5n2/3p2p1/2PPq3/2N1PN1R/PP3PP1/R1BQKB2 w Qkq - 2 7",
    # Pos 13 – 7.a3
    "rnbqkb1r/ppp1pp1p/5n2/3p2p1/2PPq3/P1N1PN1R/1P3PP1/R1BQKB2 b Qkq - 0 7",
    # Pos 14 – 7...c6
    "rnbqkb1r/pp2pp1p/2p2n2/3p2p1/2PPq3/P1N1PN1R/1P3PP1/R1BQKB2 w Qkq - 0 8",
    # Pos 15 – 8.?? (dama negra captura en d2 → Qd2)
    "rnbqkb1r/pp2pp1p/2p2n2/3p2p1/2PP4/P1N1PN1R/1P1q1PP1/R1BQKB2 w Qkq - 0 9",
    # Pos 16 – después de Qxh1 (dama negra en h1)
    "rnbqkb1r/pp2pp1p/2p2n2/3p2p1/2PP4/P1N1PN1R/1P3PP1/R1BQKB1q w Qkq - 0 9",
    # Pos 17 – exd5
    "rnbqkb1r/pp2pp1p/2p2n2/3pP1p1/2PP4/P1N4R/1P3PP1/R1BQKB1q b Qkq - 0 9",
    # Pos 18 – ...f6 (apertura del flanco)
    "rnbqkb1r/pp2p2p/2p2n1p/3pP1p1/2PP4/P1N4R/1P3PP1/R1BQKB1q w Qkq - 0 10",
    # Pos 19 – c3 (reconstruyendo peón)
    "rnbqkb1r/pp2p2p/2p2n1p/3pP1p1/2PP4/P1N4R/1PP2PP1/R1BQKB1q b Qkq - 0 10",
    # Pos 20 – f4 (ataque al flanco rey)
    "rnbqkb1r/pp2p2p/2p2n1p/3pP1p1/3P1P2/P1N4R/1PP3P1/R1BQKB1q b Qkq f3 0 10",
    # Pos 21 – ...Nh5 (retirada del caballo)
    "rnbqkb1r/pp2p2p/2p4p/3pP1pn/3P1P2/P1N4R/1PP3P1/R1BQKB1q w Qkq - 1 11",
    # Pos 22 – Rf3 (torre activa)
    "rnbqkb1r/pp2p2p/2p4p/3pP1pn/3P1P2/P1N2R2/1PP3P1/R1BQKB1q b Qkq - 2 11",
    # Pos 23 – ...d4 (avance de peón)
    "rnbqkb1r/pp2p2p/2p4p/3p2pn/3P1P2/P1N2R2/1PP3P1/R1BQKB1q b Qkq - 2 11",
    # Pos 24 – e3 (apertura central)
    "rnbqkb1r/pp2p2p/2p4p/3p2pn/3P1P2/P1N2R2/1PP1P1P1/R1BQKB1q b Qkq - 2 11",
]

# ─────────────────────────────────────────────────────────────────────────────

def print_chain(initial_fen: str, chain: list, pos_index: int):
    print(f"\n{'='*70}")
    print(f"  Posición {pos_index}: {initial_fen}")
    print(f"{'='*70}")

    for step in chain:
        if "error" in step:
            print(f"  Paso {step['step']}: ERROR → {step['error']}")
            continue

        engines = step["engines"]
        sf  = engines["stockfish"]
        ob  = engines["obsidian"]
        pc  = engines["plentychess"]
        agreement = "✓ Consenso total" if step["full_agreement"] else "~ Mayoría"

        print(f"\n  ── Paso {step['step']} ({agreement}) ──────────────────────────────")
        print(f"     Jugada consenso : {step['consensus_san']:6s}  ({step['consensus_uci']})")
        print(f"     Stockfish       : {sf['san']:6s}  ({sf['uci']})  score={sf['score']:+.2f}")
        print(f"     Obsidian        : {ob['san']:6s}  ({ob['uci']})  score={ob['score']:+.2f}")
        print(f"     PlentyChess     : {pc['san']:6s}  ({pc['uci']})  score={pc['score']:+.2f}")
        print(f"     FEN resultante  : {step['fen_after']}")


def main():
    parser = argparse.ArgumentParser(description="Prueba del endpoint analysis-chain")
    parser.add_argument("--url",   default="http://localhost:8000/api/partidas/analysis-chain/",
                        help="URL del endpoint (default: localhost:8000)")
    parser.add_argument("--depth", type=int, default=5,
                        help="Número de movimientos a calcular por posición (default: 5)")
    parser.add_argument("--fens",  type=int, nargs=2, metavar=("FROM", "TO"),
                        help="Rango de posiciones a analizar, p.ej. --fens 0 5")
    parser.add_argument("--json",  action="store_true",
                        help="Imprimir la respuesta completa en JSON sin formatear")
    args = parser.parse_args()

    fens_to_test = FENS[args.fens[0]:args.fens[1]] if args.fens else FENS

    print(f"\nAnalizando {len(fens_to_test)} posición(es) con profundidad {args.depth}...")
    print(f"Endpoint: {args.url}\n")

    try:
        response = requests.post(
            args.url,
            json={"fens": fens_to_test, "depth": args.depth},
            headers={"Content-Type": "application/json"},
            timeout=300,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("ERROR: No se pudo conectar. ¿Está el servidor corriendo en localhost:8000?")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR HTTP {e.response.status_code}: {e.response.text}")
        sys.exit(1)

    data = response.json()

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    for i, result in enumerate(data.get("results", [])):
        base_index = args.fens[0] if args.fens else 0
        if "error" in result:
            print(f"\nPosición {base_index + i}: ERROR → {result['error']}")
        else:
            print_chain(result["initial_fen"], result["chain"], base_index + i)

    print(f"\n{'='*70}")
    print("Análisis completado.")


if __name__ == "__main__":
    main()