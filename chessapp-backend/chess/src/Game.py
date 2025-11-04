import chess

# Clase para representar una partida de ajedrez. Tiene un atributo board para representar las posiciones de las piezas y
# otro atributo posiciones en el que se guarda una lista de todas las posiciones FEN de la partida
class Game:
    def __init__(self):
        self.board = chess.Board()
        self.posiciones = [self.board.fen()] # Añadimos la posición inicial a la lista de FEN
        
        
    def make_move(self,str_move):
        print(f"\nMovimiento: {str_move}")
        move = chess.Move.from_uci(str_move)
        
        if move in self.board.legal_moves:
            self.board.push(move)
            self.posiciones.append(self.board.fen())
            print(self.board)
        
        # Vemos si el movimiento es un movimiento de coronacion, en cuyo caso se asume que el jugador ha coronado una dama    
        elif chess.Move.from_uci(str_move+"q") in self.board.legal_moves:
            move = chess.Move.from_uci(str_move+"q")
            self.board.push(move)
            self.posiciones.append(self.board.fen())
            print(self.board)
        
        else:
            print("Se ha detectado un movimiento ilegal")
            
    
    def turno_blanco(self):
        return self.board.turn == chess.WHITE
    
    
    def get_lista_fen(self):
        return self.posiciones
    
    # Devuelve una lista con todas las casillas en las que haya una pieza blanca
    def casillas_pieza_blanca(self):
        casillas = self.board.pieces(chess.PAWN, chess.WHITE) | \
                   self.board.pieces(chess.KNIGHT, chess.WHITE) | \
                   self.board.pieces(chess.BISHOP, chess.WHITE) | \
                   self.board.pieces(chess.ROOK, chess.WHITE) | \
                   self.board.pieces(chess.QUEEN, chess.WHITE) | \
                   self.board.pieces(chess.KING, chess.WHITE)
                   
        return [chess.square_name(casilla) for casilla in casillas]
    
    # Devuelve una lista con todas las casillas en las que haya una pieza negra
    def casillas_pieza_negra(self):
        casillas = self.board.pieces(chess.PAWN, chess.BLACK) | \
                   self.board.pieces(chess.KNIGHT, chess.BLACK) | \
                   self.board.pieces(chess.BISHOP, chess.BLACK) | \
                   self.board.pieces(chess.ROOK, chess.BLACK) | \
                   self.board.pieces(chess.QUEEN, chess.BLACK) | \
                   self.board.pieces(chess.KING, chess.BLACK)
                   
        return [chess.square_name(casilla) for casilla in casillas]
    
    # Recibe una lista de casillas con piezas de un color y devuelve el resto de casillas del tablero    
    def casillas_sin_piezas_jugador(self,casillas_piezas):
        todas_casillas = chess.SquareSet(chess.BB_ALL)
        casillas_piezas_set = {chess.square(chess.FILE_NAMES.index(casilla[0]), int(casilla[1])-1) for casilla in casillas_piezas}
        casillas_sin = todas_casillas.difference(casillas_piezas_set)
        
        return [chess.square_name(casilla) for casilla in casillas_sin]
    
    
    # Comprueba si el jugador que tiene el turno puede enrocarse en este turno
    def puede_enrocar_ahora(self,jugador_blanco):
        
        c_rey = 'e1' if jugador_blanco else 'e8'
        e_corto = 'h1' if jugador_blanco else 'h8'
        e_largo = 'a1' if jugador_blanco else 'a8'
        
        move1 = chess.Move.from_uci(c_rey+e_corto)
        move2 = chess.Move.from_uci(c_rey+e_largo)
        
        return move1 in self.board.legal_moves or move2 in self.board.legal_moves
    
   