import socket
import threading
import sys

HOST = "127.0.0.1"
PORT = 12345

def recibir_mensajes(sock):
    """Hilo dedicado exclusivamente a escuchar lo que llega del servidor."""
    while True:
        try:
            data = sock.recv(1024).decode("utf-8")
            if not data:
                print("\n[SISTEMA] Conexión cerrada por el servidor.")
                break
            sys.stdout.write("\r" + data + "\n")
            sys.stdout.flush()
        except:
            break
    print("\nHilo de recepción finalizado.")


try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))

        # --- PROCESO DE AUTENTICACIÓN (3 pasos) ---
        autenticado = False
        while not autenticado:
            # 1. "¿Tenés cuenta? login/registrar"
            print(s.recv(1024).decode("utf-8"), end="")
            opcion = input()
            s.sendall(opcion.encode("utf-8"))

            # 2. "Usuario: "
            print(s.recv(1024).decode("utf-8"), end="")
            usuario = input()
            s.sendall(usuario.encode("utf-8"))

            # 3. "Contraseña: "
            print(s.recv(1024).decode("utf-8"), end="")
            password = input()
            s.sendall(password.encode("utf-8"))

            # Resultado (OK o ERROR)
            resultado = s.recv(1024).decode("utf-8")
            print(resultado, end="")

            if resultado.startswith("[OK]"):
                autenticado = True

        # Mensaje de bienvenida final del chat
        print(s.recv(1024).decode("utf-8"))

        # Hilo de recepción de mensajes grupales
        hilo_recibir = threading.Thread(target=recibir_mensajes, args=(s,), daemon=True)
        hilo_recibir.start()

        # Bucle principal del teclado
        try:
            while True:
                mensaje = input("Cliente: ")
                if mensaje == "/":
                    break
                if not mensaje.strip():
                    continue
                s.sendall(mensaje.encode("utf-8"))

        except KeyboardInterrupt:
            print("\n\n[SISTEMA] Saliendo del chat de forma segura...")

except ConnectionRefusedError:
    print("Error: No se pudo conectar al servidor.")

print("Has salido del chat.")