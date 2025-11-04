import os
import subprocess

def install_requirements():
    print("Instalando librerías necesarias...")
    subprocess.check_call(["pip","install","-r","requirements.txt"])
    
    
def create_directories():
    print("Creando directorios...")
    directories = ["Videos","output"]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Directorio '{directory}' creado.")
            
        else:
            print(f"Directorio '{directory}' ya existe.")
            
            

if __name__ == "__main__":
    install_requirements()
    create_directories()
    print("Setup completado. Los vídeos de pruebas se encuentran en la carpeta 'Videos'.")