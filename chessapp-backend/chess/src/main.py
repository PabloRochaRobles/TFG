import cv2 as cv
import functions
from Game import Game
import os

def click_event(event, x, y, flags, param):
    global corners
    
    if event == cv.EVENT_LBUTTONDOWN:
        corner = [x,y]
        corners.append(corner)
        cv.circle(copy,(x,y),5,(0,255,0),-1)
        cv.imshow('imagen',copy)
        
        if len(corners) == 4:
            cv.destroyAllWindows()
        
        
            
        
if __name__ == "__main__":
    
    # Creamos una nueva partida
    game = Game()
    
    
    video_file = input("Introduce el nombre del video a analizar: ")
    
    # Path del video a analizar
    path = "Videos/" + video_file

    # Capturamos el video
    video = cv.VideoCapture(path)

    # Extraemos primer frame
    frame = functions.extraer_primer_frame(video)
    
    
    
    
    detectado = False
    while not detectado:
        copy = frame.copy()
        corners = []
        print("Haga click en las cuatro esquinas que forman el tablero:")
        
        cv.imshow('imagen',copy)
        cv.setMouseCallback('imagen',click_event)
        cv.waitKey()
        
        corners = functions.ordenar_esquinas(corners)
       
        # Preprocesamiento de la imagen
        processed = functions.procesar_imagen(frame)
        
        # Aplicar homografia a la imagen del tablero
        h,transformed = functions.homog(frame,corners)
        detectado,tablero = functions.detectar_tablero(transformed,transformed)
    
    
    
    # Sacamos las cuatro esquinas del tablero ordenadas
    esq1 = tablero['a1'][0][0]
    esq2 = tablero['h1'][1][0]
    esq3 = tablero['a8'][2][0]
    esq4 = tablero['h8'][3][0]
   
    
    frame_count = 0 # Contador de frames del video
    previous_frame = None # Frame con la última imagen del tablero limpio
    brazo = False
    cont_dif_estable = 0 # Variable para contar el nº de frames seguidos sin muchos cambios en la imagen
    umbral_diferencia = 250 # Umbral para controlar la variable anterior
    estable = False
    s_prev = 0 # Diferencia de imágenes previa a la actual
    
    
    # Sacamos el limite izquierdo y derecho del tablero
    izq = max(esq1,esq2)
    der = max(esq3,esq4)
    
    fps = video.get(cv.CAP_PROP_FPS)
    wait_time = int(1000/fps)
    
 
    while video.isOpened(): 
        ret,frame = video.read()
        
        if not ret:
            break
        
        if frame_count % 2 == 0: # Se analiza uno de cada dos frames del video
            # Aplicar homografia a la imagen
            birdseye = cv.warpPerspective(frame,h,(700,500))
            cv.imshow('homografia',birdseye)
            
            
            
            if frame_count == 0:
                previous_frame = birdseye
            
            else:
                
                gray1 = cv.cvtColor(birdseye,cv.COLOR_BGR2GRAY)
                gray2 = cv.cvtColor(previous_frame,cv.COLOR_BGR2GRAY)
                
                diff = cv.absdiff(gray1,gray2) # Diferencia de imágenes entre el frame actual y el anterior
                _,diff = cv.threshold(diff,30,255,cv.THRESH_TOZERO) # Umbralizar la imagen diferencia
                
                
                # Poner a cero todos los píxeles de la imagen diferencia que no estén dentro del tablero
                for y in range(500): # Ancho de la imagen
                    for x in range(700): # Largo de la imagen
                        if x<izq or x>der:
                            diff[y,x] = 0
               
                
                s = cv.countNonZero(diff) # Nº de píxeles de la imagen diferencia que no tienen el valor cero
                
                # Se establece el valor del umbral en funcion de si es el turno del blanco o del negro
                umbral = 500 if not brazo else 3000 if game.turno_blanco() else 6000
                
                
                if s<umbral or estable or (s_prev-s>5000 and s-umbral<4000):
                    
                    if brazo:
                        
                        hay_move,move = functions.buscar_movimiento(diff,tablero,game)
                        
                        if hay_move:
                            previous_frame = birdseye
                        
                        elif move == "update":
                            previous_frame = birdseye
                        
                        brazo = False
                        cont_dif_estable = 0
                        estable = False
                        
                        
                    
                else:
                    
                    brazo = True
                    
                    if abs(s-s_prev) <= umbral_diferencia: # Comprobar si las últimas imágenes tienen pocos cambios
                        cont_dif_estable+=1
                    
                    # Si hay cinco frames seguidos sin cambios actualizar la variable estable
                    if cont_dif_estable >= 5 and s-umbral<8000:
                        estable = True
                        
                    
                    
                    
                
                s_prev = s
                if cv.waitKey(wait_time) & 0xFF == ord('q'): # Pulsar tecla q para finalizar el programa
                    break

            
        
        frame_count+=1
        

   
    video.release()
    cv.destroyAllWindows()
    
    print("Final de la partida")
    
    # Sacar la lista de posiciones FEN de la partida
    posiciones = game.get_lista_fen()
    
    # Sacar el nombre del fichero sin la extensión
    file = os.path.splitext(video_file)[0]
    
    # Generar el fichero con las posiciones FEN
    functions.escribir_fichero(posiciones,file)
