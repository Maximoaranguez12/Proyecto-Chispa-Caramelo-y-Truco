#Poner conectexecption error para saber si del otro lado el cliente hay desconexión o viceversa.
import time
import requests # type: ignore
import socket
import threading
import db_example 
# Diccionario global para registrar a los clientes activos:
# Estructura de socket_cliente: "nombre_de_usuario"
clientes_activos = {}
# Candado para evitar que dos hilos modifiquen el diccionario al mismo tiempo
clientes_lock = threading.Lock()

def Broadcast(mensaje, socket_remitente=None):
    """Envía un mensaje a absolutamente todos los usuarios conectados."""
    with clientes_lock:
        for sock in clientes_activos:
            # Opcional: No mandarle el mensaje de vuelta al que lo escribió
            if sock != socket_remitente:
                try:
                    sock.send(mensaje.encode("utf-8"))
                except:
                    # Si falla el envío, el socket probablemente esté roto
                    pass

def atender_cliente(client_socket, address):
    print(f"[*] Nueva conexión desde {address}")
    
    # --- PROCESO DE AUTENTICACIÓN ---
    username = None
    try:
        while username is None:
            client_socket.send("¿Tenés cuenta? Escribe 'login' o 'registrar': ".encode("utf-8"))
            opcion = client_socket.recv(1024).decode("utf-8").strip().lower()

            client_socket.send("Usuario: ".encode("utf-8"))
            user_input = client_socket.recv(1024).decode("utf-8").strip()

            client_socket.send("Contraseña: ".encode("utf-8"))
            pass_input = client_socket.recv(1024).decode("utf-8").strip()

            if opcion == "registrar":
                if db_example.existe_usuario(user_input) :
                    client_socket.send("[ERROR] Ese usuario ya existe. Probá de nuevo.\n".encode("utf-8"))
                    continue
                db_example.registrar_usuario(user_input, pass_input)
                username = user_input
                client_socket.send(f"[OK] Usuario {username} registrado correctamente.\n".encode("utf-8"))

            elif opcion == "login":
                if  db_example.verificar_usuario(user_input, pass_input):
                    username = user_input
                    client_socket.send(f"[OK] Bienvenido de nuevo, {username}.\n".encode("utf-8"))
                else:
                    client_socket.send("[ERROR] Usuario o contraseña incorrectos.\n".encode("utf-8"))
            else:
                client_socket.send("[ERROR] Opción inválida. Escribe 'login' o 'registrar'.\n".encode("utf-8"))

    except:
        client_socket.close()
        return

    # Registrar al usuario activo
    with clientes_lock:
        clientes_activos[client_socket] = username

    # Registrar conexión en la base de datos
    db_example.registrar_conexion(username, "conexion")

    Broadcast(f"\n[SISTEMA] {username} se ha unido al chat.\n")
    client_socket.send(f"Bienvenido {username}. Comandos: '/' para salir, '/usuarios' para ver lista de usuarios,'/gato' para ver imágen de gato.\n".encode("utf-8"))


    # --- BUCLE PRINCIPAL DEL CHAT ---
    while True:
        try:
            data = client_socket.recv(1024).decode("utf-8").strip()
            
            if not data or data == "/":
                break
                
                        # COMANDO CON API: /gato (Envía un enlace de gato aleatorio a todo el grupo)
            if data == "/gato":
                try:
                    # 1. Generamos el número único de tiempo para romper el caché de red
                    url_api = "https://api.thecatapi.com/v1/images/search"
                    
                    # 2. SOLUCIÓN CLAVE: Añadimos un User-Agent real en los Headers para que la API no nos bloquee
                    cabeceras = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                    
                    # Hacemos la petición pasando las cabeceras simuladas
                    respuesta_api = requests.get(url_api, headers=cabeceras, timeout=5)
                    
                    if respuesta_api.status_code == 200:
                        datos_json = respuesta_api.json()
                        
                        # 3. Comprobamos de manera segura que sea una lista con elementos
                        if isinstance(datos_json, list) and len(datos_json) > 0:
                            
                            # <-- EXTRAEMOS EL PRIMER ELEMENTO USANDO EL ÍNDICE [0]
                            primer_gatito = datos_json[0]
                            
                            # 4. Buscamos la clave 'url' de forma segura dentro del diccionario
                            if isinstance(primer_gatito, dict) and "url" in primer_gatito:
                                url_imagen_gato = primer_gatito["url"]
                                db_example.guardar_api_call(username, "/gato", url_imagen_gato)
                                msg_gato = f"\n[🐱 MICHIS DE LA API] {username} invocó un gato: {url_imagen_gato}\n"
                                Broadcast(msg_gato)
                            else:
                                client_socket.send("[SISTEMA] No se encontró la URL del mishi.".encode("utf-8"))
                        else:
                            client_socket.send("[SISTEMA] Formato inesperado recibido de la API.".encode("utf-8"))
                    else:
                        client_socket.send(f"[SISTEMA] La API respondió con error de red: {respuesta_api.status_code}".encode("utf-8"))
                        
                except requests.exceptions.Timeout:
                    client_socket.send("[SISTEMA] La API de gatos tardó demasiado en responder (Timeout).".encode("utf-8"))
                except Exception as e:
                    # Esto te mostrará el motivo técnico real en la terminal donde corre tu server.py
                    print(f"[-] ERROR DETECTADO EN /gato: {e}")
                    client_socket.send("[SISTEMA] Error interno al procesar el comando.".encode("utf-8"))
                continue

                
            # COMANDO: /usuarios (Muestra la lista de conectados)
            if data == "/usuarios":
                with clientes_lock:
                    lista = ", ".join(clientes_activos.values())
                client_socket.send(f"[SISTEMA] Usuarios conectados: {lista}".encode("utf-8"))
                continue

            # MENSAJE NORMAL: Se transmite a todos
            print(f"[{username}]: {data}")
            Broadcast(f"[{username}]: {data}", socket_remitente=client_socket)
            db_example.guardar_mensaje(username, data)
        except ConnectionResetError:
            break

    # --- PROCESO DE DESCONEXIÓN ---
    with clientes_lock:
        if client_socket in clientes_activos:
            del clientes_activos[client_socket]

    db_example.registrar_conexion(username, "desconexion")
    Broadcast(f"\n[SISTEMA] {username} ha salido del chat.\n")
    print(f"[*] Conexión con {username} ({address}) finalizada.")
    client_socket.close()

# Configuración del servidor principal
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(("127.0.0.1", 12345))
server_socket.listen(10)

print("Servidor de Chat Grupal escuchando en el puerto 12345...")

while True:
    client_socket, address = server_socket.accept()
    hilo = threading.Thread(target=atender_cliente, args=(client_socket, address), daemon=True)
    hilo.start()
