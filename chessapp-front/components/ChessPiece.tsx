/**
 * ChessPiece — Renderiza una pieza de ajedrez del set Merida.
 *
 * El set Merida es obra de Armando Hernandez Marroquin, publicado bajo
 * licencia GPLv2 y distribuido por el proyecto Lichess
 * (github.com/lichess-org/lila, carpeta `public/piece/merida/`). Los
 * ficheros SVG residen localmente en `assets/pieces/merida/` con la
 * convención de nombres `{w|b}{K|Q|R|B|N|P}.svg`.
 *
 * `react-native-svg-transformer` (configurado en `metro.config.js`)
 * convierte cada `.svg` importado en un componente React que acepta
 * props `width` y `height`, así que podemos usarlos como JSX directo.
 *
 * Uso:
 *   <ChessPiece piece="K" size={42} />   // rey blanco
 *   <ChessPiece piece="q" size={42} />   // dama negra
 */
import React from 'react';

import bB from '@/assets/pieces/merida/bB.svg';
import bK from '@/assets/pieces/merida/bK.svg';
import bN from '@/assets/pieces/merida/bN.svg';
import bP from '@/assets/pieces/merida/bP.svg';
import bQ from '@/assets/pieces/merida/bQ.svg';
import bR from '@/assets/pieces/merida/bR.svg';
import wB from '@/assets/pieces/merida/wB.svg';
import wK from '@/assets/pieces/merida/wK.svg';
import wN from '@/assets/pieces/merida/wN.svg';
import wP from '@/assets/pieces/merida/wP.svg';
import wQ from '@/assets/pieces/merida/wQ.svg';
import wR from '@/assets/pieces/merida/wR.svg';

const PIECES: Record<string, React.FC<{ width: number; height: number }>> = {
  K: wK, Q: wQ, R: wR, B: wB, N: wN, P: wP,
  k: bK, q: bQ, r: bR, b: bB, n: bN, p: bP,
};

type Props = {
  /** Letra FEN: K Q R B N P (blancas) o k q r b n p (negras). */
  piece: string;
  /** Tamaño en píxeles del lado de la pieza. */
  size: number;
};

export default function ChessPiece({ piece, size }: Props) {
  const Component = PIECES[piece];
  if (!Component) return null;
  return <Component width={size} height={size} />;
}
