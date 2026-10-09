# Chispa, Caramelo y Truco

Videojuego de Truco Argentino 1 vs 1, con cliente gráfico Pygame, servidor TCP
con mensajes JSON, autenticación y persistencia PostgreSQL. Se puede jugar
contra otro cliente conectado al servidor o contra un bot de estrategia fija.

## Requisitos

- Python 3.10 o superior.
- PostgreSQL 13 o superior.
- Windows, Linux o macOS con un escritorio gráfico para ejecutar el cliente.

## Instalación

Desde PowerShell, en la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si PowerShell indica que `python` tampoco se reconoce, instala Python 3.10 o
superior y habilita **Add python.exe to PATH** durante la instalación. También
puedes cerrar y volver a abrir PowerShell después de instalarlo. El lanzador
`py` es opcional y no está disponible en todas las instalaciones de Windows.
No hace falta activar el entorno virtual: los ejemplos llaman directamente al
Python instalado dentro de `.venv`.

Crear la base de datos y aplicar el esquema:

```sql
CREATE DATABASE truco;
```

```powershell
psql -U postgres -d truco -f .\BD.Sql
```

El servidor también crea las tablas que falten al arrancar. Configurar el
acceso mediante variables de entorno (no guardar contraseñas en el repositorio):

```powershell
$env:PGHOST = "localhost"
$env:PGPORT = "5432"
$env:PGDATABASE = "truco"
$env:PGUSER = "postgres"
$env:PGPASSWORD = "1234"
```

Reemplaza el último valor por la contraseña que configuraste para el usuario
de PostgreSQL (no es la contraseña de la cuenta del juego). Ejecuta estas
líneas en la misma ventana de PowerShell desde la que inicias el servidor.
No compartas ni guardes esa clave en el proyecto. Si no recuerdas la clave,
debes restablecerla en PostgreSQL o configurar una contraseña para ese usuario.

## Ejecución

En una terminal, iniciar PostgreSQL y luego el servidor:

```powershell
.\.venv\Scripts\python.exe .\Servidor.py
```

En otra terminal, iniciar el cliente:

```powershell
.\.venv\Scripts\python.exe .\Cliente.py
```

Para jugar desde otra computadora de la misma red, iniciar el cliente indicando
la dirección IP de la computadora que ejecuta el servidor:

```powershell
.\.venv\Scripts\python.exe .\Cliente.py --host 192.168.1.20 --port 12345
```

El firewall debe permitir conexiones TCP entrantes al puerto 12345. El servidor
escucha en todas las interfaces de red; el cliente local usa `127.0.0.1`.

## Cómo jugar

1. Crear una cuenta o iniciar sesión. El usuario admite letras, números y `_`;
   la contraseña debe tener entre 8 y 128 caracteres.
2. Elegir **Jugar contra bot** o **Buscar rival en línea**. Para emparejar dos
   personas, ambas deben iniciar sesión en el mismo servidor.
3. Jugar las cartas haciendo clic en ellas. Las acciones del servidor se
   validan antes de actualizar la mesa.
4. El juego incluye las jerarquías de cartas argentinas, las bazas pardas,
   Envido, Real Envido, Falta Envido, Truco, Retruco y Vale Cuatro; la partida
   se juega a 30 puntos. Desde el propio turno se puede quemar una carta boca
   abajo una vez por mano; esa variante acorta la mano a dos bazas. También se
   puede aceptar el Envido sin mostrar el tanto declarado.
5. El chat es privado para los participantes de la partida y se guarda en la
   base de datos.

Después de aceptar un Envido, cada jugador declara su puntaje desde el chat:
`/tanto 33` lo muestra al rival y `/tanto-oculto 33` lo mantiene oculto. El
rival puede escribir `/reclamar` para que el servidor compruebe las cartas; si
solo uno mintió, pierde la apuesta y los puntos van al otro. Jugar una carta
acepta las declaraciones sin reclamarlas; por eso una mentira no reclamada
puede ganar la apuesta. El bot declara su puntaje real y reclama declaraciones
ocultas o incorrectas.

## Reglas y alcance de esta versión

- Es una primera versión académica de Truco mano a mano. El Envido se canta
  antes de que se juegue la primera carta; se aceptan los tres cantos, pero no
  se encadenan varias apuestas de Envido.
- El reclamo de Envido revela los tantos reales. Si ambos mienten, el resultado
  del reclamo se resuelve con el tanto real de cada mano; si ninguno miente,
  se aplica el resultado real respetando quién es mano.
- Quemar una carta es una variante de esta versión, no una regla oficial:
  consume el turno y reduce a dos la cantidad de bazas necesarias.
- El bot usa reglas fijas, no aprendizaje automático.
- El protocolo usa TCP sin cifrado; ejecutar en una red de confianza. Las
  contraseñas se almacenan con hash scrypt y salt por usuario, pero no se debe
  exponer este servidor directamente a Internet.
- El servidor usa PostgreSQL; no hay almacenamiento alternativo silencioso.
  Si la base no está disponible, el servidor muestra el error y no inicia.
- Usuarios creados con el esquema anterior del ejercicio de chat, que no
  tengan salt, necesitan registrarse con otro nombre o que el administrador
  migre/reinicie su cuenta antes de iniciar sesión.

## Pruebas

Las reglas principales se pueden validar sin conectarse a PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_truco.py" -v
```

## Dependencias para la entrega

`requirements.txt` contiene las dependencias directas con versiones fijadas.
Después de instalar el proyecto dentro del entorno virtual de entrega, para
adjuntar además el inventario completo instalado:

```powershell
.\.venv\Scripts\python.exe -m pip freeze > requirements-entrega.txt
```

No se recomienda generar el archivo congelado desde un Python global, porque
podría incluir paquetes ajenos al proyecto.
