import numpy as np
import cv2 as cv
import chess
import os

def extraer_primer_frame(video):
    ret,frame = video.read()
    
    if not ret:
        raise Exception("Error al abrir el video")
    else:
        
        return frame
    
    
def procesar_imagen(image):
    # Aumento de contraste
    contrasted = cv.convertScaleAbs(image, alpha=1.5, beta=0)
    
    # Filtro Gaussiano
    gaussian = cv.GaussianBlur(contrasted, ksize=(5,5), sigmaX=0)
    
    # Pasar a escala de grises
    gray = cv.cvtColor(gaussian, cv.COLOR_BGR2GRAY)
    
    return gray

def polares_a_cartesianas(rho,theta):
    a = np.cos(theta)
    b = np.sin(theta)
    x0 = a * rho
    y0 = b * rho
    x1 = int(x0 + 1000 * (-b))
    y1 = int(y0 + 1000 * (a))
    x2 = int(x0 - 1000 * (-b))
    y2 = int(y0 - 1000 * (a))
    
    return x1,y1,x2,y2

def cartesianas(lines):
    lineas = []
    for line in lines:
        rho,theta = line[0]
        x1,y1,x2,y2 = polares_a_cartesianas(rho,theta)
        lineas.append([x1,y1,x2,y2])
        
    return lineas
        
        

def detectar_tablero(image,original):
    canny = cv.Canny(image, threshold1=50,threshold2=150,apertureSize=3)
    
    lines = cv.HoughLines(canny,1,np.pi/360,threshold=150)
    
    
    h_lines,v_lines = divide_lines(lines)
    
    h_lines = cartesianas(h_lines)
    v_lines = cartesianas(v_lines)
    
    h_lines = filtrar_lineas(h_lines,35,True)
    v_lines = filtrar_lineas(v_lines,40,False)
    
    h_lines = sorted(h_lines,key=lambda line:line[1])
    v_lines = sorted(v_lines,key=lambda line:line[0])
    
    dibujar_lineas(original,h_lines,v_lines)
    cv.imshow('lineas',original)
    
    print("Si no se ha detectado el tablero correctamente pulse 'b', en otro caso pulse cualquier tecla para continuar")
    key = cv.waitKey(0) & 0xFF
    if key == ord('b'):
        return False,{}
    
        
    
    cv.destroyAllWindows()
    
    
    intersections = encontrar_intersecciones(h_lines,v_lines)
    
   
    casillas = generar_coordenadas_casillas(intersections)
    
    # Comprobar las casillas de las esquinas para determinar el lado del jugador
    blanco_izq = lado_blanco(original,casillas[7],casillas[56])
    
   
    if not blanco_izq:
        casillas.reverse() # Invertir la lista de casillas ya que el blanco va a la derecha
        
        
    
    return True,crear_diccionario(casillas)
    
# Crea un diccionario en el que cada casilla tiene asociada las coordenadas de las cuatro esquinas que la forman
def crear_diccionario(casillas):
    columnas = 'abcdefgh'
    filas = '12345678'
    
    dic = {}
    index = 0
    
    for fila in filas:
        for columna in columnas:
            nombre_casilla = columna + fila
            dic[nombre_casilla] = casillas[index]
            index+= 1
            
    return dic

# Divide una lista de líneas en horizontales y verticales basándose en su pendiente
def divide_lines(lines):
    h_lines = []
    v_lines = []
    
    for line in lines:
        rho, theta = line[0]  # Coordenadas polares (rho, theta)

        # Convertir coordenadas polares a coordenadas cartesianas
        x1,y1,x2,y2 = polares_a_cartesianas(rho,theta)
            
        slope = (y2 - y1) / (x2 - x1) if (x2 - x1) != 0 else np.inf
        # Si la pendiente es cercana a cero, consideramos la línea como horizontal
        if abs(slope) < 0.02:
            
            h_lines.append(line)
        # Si la pendiente es cercana a infinito, consideramos la línea como vertical
        elif abs(slope) > 2:
            v_lines.append(line)
            
    return h_lines,v_lines
        
# Dibuja las líneas detectadas en la imagen
def dibujar_lineas(img,h_lines,v_lines):
    if h_lines is not None:
        for line in h_lines:
            x1,y1,x2,y2 = line#polares_a_cartesianas(rho,theta)
            cv.line(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
            
    if v_lines is not None:
        for line in v_lines:
            x1,y1,x2,y2 = line#polares_a_cartesianas(rho,theta)
            cv.line(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
# Elimina líneas que sean muy similares
def filtrar_lineas(lines, distance, horizontal):
    filtered = []
    for line in lines:
        x1, y1, x2, y2 = line
        agregar_linea = True
        
        for l in filtered:
            x3, y3, x4, y4 = l
            if not horizontal:
                if abs(x3 - x1) <= distance:
                    agregar_linea = False
                    break
            else:
                if abs(y3 - y1) <= distance:
                    agregar_linea = False
                    break
        
        if agregar_linea:
            filtered.append(line)
    
    return filtered


def eliminar_lineas_similares(lines,threshold_distance,threshold_angle):
    filtered_lines = []
    
    for line in lines:
        rho,theta = line[0]
        
        similar_lines = [l for l in filtered_lines if np.abs(rho-l[0]) < threshold_distance and np.abs(theta-l[1])<threshold_angle]
        
        if not similar_lines:
            filtered_lines.append([rho,theta])
            
    return filtered_lines

# Calcula todos los puntos de intersección entre un conjunto de líneas horizontales y otro de líneas verticales
def encontrar_intersecciones(h_lines,v_lines):
    intersections = []
    
    for v_line in v_lines:
        x1_v,y1_v,x2_v,y2_v = v_line#polares_a_cartesianas(rho,theta)
        
        for h_line in h_lines:
            x1_h,y1_h,x2_h,y2_h = h_line#polares_a_cartesianas(rho,theta)
            
            if x1_h<= x1_v<=x2_h and (y1_v<=y1_h<=y2_v or y1_v>=y1_h>=y2_v):
                x,y = calcular_interseccion(x1_h,y1_h,x2_h,y2_h,x1_v,y1_v,x2_v,y2_v)
                intersections.append((x,y))
                
    return intersections

# Identifica si el jugador blanco está en el lado izquierdo del tablero o no
def lado_blanco(img,casilla1,casilla2):
    tl,bl,tr,br = casilla1
    puntos = np.array([tl,tr,br,bl],dtype=np.int32)
    mask = np.zeros(img.shape[:2],dtype=np.uint8)
    cv.fillConvexPoly(mask,puntos,(255,255,255))
    masked = cv.bitwise_and(img,img,mask=mask)
    
    roi_gris = cv.cvtColor(masked,cv.COLOR_BGR2GRAY)
    roi_gris = roi_gris[roi_gris>0] # Filtrar pixeles que no sean negros
    promedio1 = np.mean(roi_gris) 
    
    tl,bl,tr,br = casilla2
    puntos = np.array([tl,tr,br,bl],dtype=np.int32)
    mask = np.zeros(img.shape[:2],dtype=np.uint8)
    cv.fillConvexPoly(mask,puntos,(255,255,255))
    masked = cv.bitwise_and(img,img,mask=mask)
    
    roi_gris = cv.cvtColor(masked,cv.COLOR_BGR2GRAY)
    roi_gris = roi_gris[roi_gris>0] # Filtrar pixeles que no sean negros
    promedio2 = np.mean(roi_gris)
    
    
    return promedio1 > promedio2 # Se compara el color promedio de cada casilla, la que sea más clara corresponde al jugador blanco


def generar_coordenadas_casillas(intersections):
    casillas = []
    for i in range(0,len(intersections)-10):
        if (i+1)%9 !=0:
            casilla = [intersections[i],intersections[i+1],intersections[i+9],intersections[i+10]]
            casillas.append(casilla)
        
    return casillas

# Calcula el punto de intersección entre dos rectas dados los puntos de inicio y final de cada una de estas
def calcular_interseccion(x1,y1,x2,y2,x3,y3,x4,y4):
    px= ( (x1*y2-y1*x2)*(x3-x4)-(x1-x2)*(x3*y4-y3*x4) ) / ( (x1-x2)*(y3-y4)-(y1-y2)*(x3-x4) ) 
    py= ( (x1*y2-y1*x2)*(y3-y4)-(y1-y2)*(x3*y4-y3*x4) ) / ( (x1-x2)*(y3-y4)-(y1-y2)*(x3-x4) )
    
    return (int(px),int(py))


# Aplica una homografia a la imagen en funcion de las cuatro esquinas que se pasen como parámetro
def homog(img,corners):
    pt1 = np.float32(corners)
    #pt1 = np.float32([[429,429],[348,716],[806,423],[894,719]]) #test1
    #pt1 = np.float32([[409,408],[316,687],[798,415],[864,690]]) #test2
    pt2 = np.float32([[0,0],[0,500],[700,0],[700,500]])
    
    matrix = cv.getPerspectiveTransform(pt1,pt2)
    transformed = cv.warpPerspective(img,matrix,(700,500))
    
    return matrix,transformed
  
# Busca si hay un movimiento de enroque disponible
def buscar_enroque(turno_blanco,cpiezas):
    c_rey = 'e1' if turno_blanco else 'e8'
    e_corto = 'h1' if turno_blanco else 'h8'
    e_largo = 'a1' if turno_blanco else 'a8'
    
    if e_corto in cpiezas:
        c_destino = 'g1' if turno_blanco else 'g8'
        return True, c_rey+c_destino
    
    if e_largo in cpiezas:
        c_destino = 'c1' if turno_blanco else 'c8'
        return True, c_rey+c_destino
    
    return False,None

    
def buscar_movimiento(diff,tablero,game):
    
    turno_blanco = game.turno_blanco()
    cpiezas = game.casillas_pieza_blanca() if turno_blanco else game.casillas_pieza_negra()
    cvacias = game.casillas_sin_piezas_jugador(cpiezas)
    
    # Lista de las casillas que han cambiado lo suficiente (ordenada)
    cpiezas = casillas_cambiadas(diff,tablero,cpiezas)
    cvacias = casillas_cambiadas(diff,tablero,cvacias)
    casillas = cpiezas + cvacias
    
    
    origen = buscar_casilla(diff,tablero,cpiezas,casillas)
    destino = buscar_casilla(diff,tablero,cvacias,casillas)
    
    
    if origen is None or destino is None:
        return False,None
    
    if len(destino)>10:
        return False,"update"
    
    if len(origen) >1 and game.puede_enrocar_ahora(turno_blanco):
        r = 'e1' if turno_blanco else 'e8'
        ec = 'h1' if turno_blanco else 'h8'
        el = 'a1' if turno_blanco else 'a8'
        c_origen = [c[0] for c in origen]
        
        if r in c_origen and ec in c_origen:
            c = 'g1' if turno_blanco else 'g8'
            move = r+c
            game.make_move(move)
            return True,move
        
        if r in c_origen and el in c_origen:
            c = 'c1' if turno_blanco else 'c8'
            move = r+c
            game.make_move(move)
            return True,move

    
    legal_moves = movimientos_legales(origen,destino,game)
    
        
    if len(legal_moves) == 0:
        return False,None
    
    if len(legal_moves) == 1:
        move = legal_moves[0][0]    
        game.make_move(move)
        return True,move
    
    else:
        move = analizar_movimientos(legal_moves)
        game.make_move(move)
        return True,move
    
    
def analizar_movimientos(legal_moves):
    umbral = 100
    v = legal_moves[0][1]
    
    legal_moves_filtered = [tupla for tupla in legal_moves if abs(tupla[1] - v) <= umbral]
    
    if legal_moves_filtered == 1:
        return legal_moves_filtered[0][0]
    
    else:
        
        for move,valor in legal_moves_filtered:
            if not mov_una_casilla(move):
                return move
        
# Comprueba si el movimiento es un movimiento en el que la pieza se mueve solo una casilla
def mov_una_casilla(move):
    origen = move[0:2]
    destino = move[2:4]
    
    return es_adyacente(origen,destino) or es_adyacente(destino,origen)


def movimientos_legales(origen,destino,game):
    l = []
    legal = game.board.legal_moves
    for o,v1 in origen:
        for d,v2 in destino:
            m = o+d
            move = chess.Move.from_uci(m)
            if move in legal:
                l.append((m,v1+v2))
    
    l = sorted(l,key=lambda x:x[1],reverse=True)            
    return l

def buscar_casilla(diff,tablero,lista,casillas):
    posibles = adyacentes(lista,casillas,tablero,diff)
    
    if len(posibles) == 0:
        return None
    
    
    res = []
    _,diff2 = cv.threshold(diff,80,255,cv.THRESH_TOZERO)
    for c in posibles:
        if c[0] == 'a':
            coords = tablero[c]
            (x1,y1) = coords[1]
            (x2,y2) = coords[3]
            
            (x3,y3) = (x1,0)
            (x4,y4) = (x2,0)
            
        else:
            ady = chr(ord(c[0])-1) + c[1]
        
            coords = tablero[c]
            coords2 = tablero[ady]
        
            (x1,y1) = coords[1]
            (x2,y2) = coords[3]
        
            (x3,y3) = coords2[0]
            (x4,y4) = coords2[2]
        
        max_x = max(x1,x2)
        max_y = max(y1,y2)
        min_x = min(x1,x2)
        min_y = min(y3,y4)
        
        
        
        area_casillas = diff2[min_y:max_y,min_x:max_x]
        n = cv.countNonZero(area_casillas)
        if n > 0:
            res.append((c,n))
    
    res = sorted(res,key=lambda x:x[1],reverse=True)
          
    return res
    
    
    
def adyacentes(lista,casillas,tablero,diff):
    posibles = []
    
    for c,v in lista:
        if c[0] == 'a':
            coords = tablero[c]
            (x1,y1) = coords[1]
            (x2,y2) = coords[3]
            
            y = min(y1,y2)
            
            c_dif = diff[0:y,x1:x2]
            
            if cv.sumElems(c_dif)[0] > 4000:
                posibles.append(c)
            
            
        for casilla,v2 in casillas:
            
            if es_adyacente(c,casilla):
                posibles.append(c)
                
            
    return posibles

# Devuelve una lista ordenada de las casillas que más han cambiado en la diferencia de dos imágenes    
def casillas_cambiadas(diff,tablero,casillas):
    moves = []
    for casilla in casillas:
        coords = tablero[casilla]
        (x1, y1) = coords[0]  # top left
        (x2, y2) = coords[1]  # bottom left
        (x3, y3) = coords[2]  # top right
        (x4, y4) = coords[3]  # bottom right
         
        # Determinar los límites de la subregión de la casilla
        min_x = min(x1, x2, x3, x4)
        max_x = max(x1, x2, x3, x4)
        min_y = min(y1, y2, y3, y4)
        max_y = max(y1, y2, y3, y4)
        
        casilla_dif = diff[min_y:max_y,min_x:max_x]
        #c = cv.countNonZero(casilla_dif)
        c = cv.sumElems(casilla_dif)[0]
        
        if c > 4000:
            moves.append((casilla,c))   
    
    moves = sorted(moves,key=lambda x:x[1],reverse=True)
    
    return moves

# Comprueba si dos casillas son adyacentes
def es_adyacente(c1,c2):
    if c1[1] == c2[1]:
        a = ord(c1[0])
        b = ord(c2[0])
        
        return a-b == 1
    
    return False
        

def ordenar_esquinas(esquinas):
    ordenadas_x = sorted(esquinas,key=lambda x:x[0])
    
    izq = ordenadas_x[:2]
    dcha = ordenadas_x[2:]
    
    izq = sorted(izq, key=lambda x:x[1])
    dcha = sorted(dcha,key=lambda x:x[1])
    
    return izq+dcha

def escribir_fichero(posiciones,nombre='posiciones'):
    output_folder = 'output'
    
    os.makedirs(output_folder,exist_ok=True) # Crear el directorio si no existe
    
    nombre = nombre + ".fen"
    output_path = os.path.join(output_folder,nombre)
    
    with open(output_path,'w') as fichero:
        for posicion in posiciones:
            fichero.write(posicion + '\n')
            
    print(f"Se han guardado todas las posiciones FEN de la partida en el fichero '{nombre}' dentro de la carpeta 'output'.")
