# Personal y Asistencias

App unificada (Flask + PostgreSQL, desplegada en Railway) que combina:

1. **Control de Asistencias** — recibe marcajes y usuarios de un dispositivo
   biométrico (protocolo ADMS/iClock), los guarda en PostgreSQL, y muestra
   un panel con KPIs, tabla de últimos marcajes y exportación a CSV.
2. **Administración de Personal** — alta de trabajadores, búsqueda por
   nombre/DNI/código de empleado, edición de datos, control de fecha de fin
   de contrato y renovaciones, y documentos en PDF por trabajador (guardados
   directamente en la base de datos).

Ambos módulos comparten la misma tabla de trabajadores: si un trabajador ya
fue enrolado en el biométrico, aparece automáticamente en el buscador de
personal (con su nombre y código de empleado) y desde ahí puedes completarle
el DNI, cargo, contrato y documentos.

Todo protegido con **login** (usuario y contraseña) — excepto los endpoints
que usa el propio dispositivo biométrico (`/iclock/...`), que deben quedar
abiertos para que el dispositivo pueda reportar datos.

## Archivos

- `app.py` — arranque de la app, registro de módulos, rutas del panel de
  asistencias y de comunicación con el dispositivo biométrico.
- `db.py` — conexión a PostgreSQL y creación/migración automática de tablas.
- `auth.py` — login, logout y protección de rutas.
- `trabajadores.py` — todo el módulo de personal (alta, búsqueda, edición,
  contrato, documentos PDF).
- `templates/` — páginas (login, asistencias, nuevo trabajador, buscar
  trabajador).
- `static/` — CSS y JS del frontend.
- `requirements.txt` — dependencias (versiones fijas, sin cambios).
- `Procfile` — comando de arranque en Railway (`gunicorn app:app`).

## Variables de entorno necesarias

- `DATABASE_URL` — cadena de conexión a PostgreSQL (Railway la provee
  automáticamente si ya tienes el servicio de PostgreSQL en tu proyecto).
- `SECRET_KEY` — **importante definirla en Railway.** Es la clave con la que
  se firman las sesiones de login. Si no la defines, la app genera una clave
  temporal y todos los usuarios se desloguean cada vez que la app se
  reinicia o se vuelve a desplegar. Ponle cualquier texto largo y aleatorio,
  por ejemplo generado con: `python -c "import secrets; print(secrets.token_hex(32))"`
- `PORT` — puerto en el que escucha la app (Railway la define automáticamente).

## Primer usuario

La primera vez que arranca la app (si la tabla `usuarios` está vacía), se
crea automáticamente:

- Usuario: `admin`
- Contraseña: `admin123`

Cámbiala cuanto antes actualizando la fila correspondiente en la tabla
`usuarios` (o pide que se agregue una pantalla de cambio de contraseña).

## Ejecutar en local (VS Code u otro editor)

1. Crea un entorno virtual e instala las dependencias:
   ```
   python -m venv venv
   venv\Scripts\activate        (Windows)
   source venv/bin/activate     (Mac/Linux)
   pip install -r requirements.txt
   ```
2. Define las variables de entorno (usando tu Postgres de Railway o uno
   local):
   ```
   set DATABASE_URL=postgresql://usuario:password@host:5432/nombre_bd      (Windows cmd)
   $env:DATABASE_URL = "postgresql://usuario:password@host:5432/nombre_bd" (PowerShell)
   export DATABASE_URL="postgresql://usuario:password@host:5432/nombre_bd" (Mac/Linux)

   (lo mismo para SECRET_KEY)
   ```
3. Corre la app:
   ```
   python app.py
   ```
   Arranca con `waitress` en `http://localhost:8080`. Las tablas y columnas
   nuevas se crean/migran automáticamente si no existen — es seguro correr
   esto contra tu base de datos de Railway ya existente, no borra nada.

## Desplegar en Railway

1. Sube estos archivos al repositorio conectado a tu proyecto de Railway (o
   redeploy manual).
2. Verifica que el servicio de PostgreSQL siga conectado (ya deberías
   tenerlo, porque el sistema de asistencias ya lo usaba).
3. Agrega la variable `SECRET_KEY` en la configuración del servicio (ver
   arriba).
4. Railway detecta el `Procfile` y arranca con `gunicorn app:app`.
5. Al desplegar, la app migra automáticamente la tabla `trabajadores`
   existente (le agrega las columnas nuevas del módulo de personal) sin
   afectar los datos de asistencias ya guardados.

## Notas sobre los documentos PDF

Se guardan como datos binarios dentro de la misma base PostgreSQL (columna
`BYTEA` en la tabla `documentos`), no en el disco del servidor. Esto evita
que se pierdan si Railway reinicia o redespliega la app, a costa de que la
base de datos crezca más rápido según la cantidad y tamaño de PDFs que subas
(límite actual: 25MB por archivo).

## Notas de la integración

- Este proyecto reemplaza al anterior "Gestor de Trabajadores" (Node.js,
  datos en un archivo local) — ya no hace falta correr esa app por separado;
  todo vive aquí ahora.
- Probado de punta a punta con PostgreSQL real: alta de trabajador con
  documentos, búsqueda, edición de datos, renovación de contrato, subida y
  eliminación de documentos, y que el flujo del dispositivo biométrico
  (marcajes + sincronización de usuarios) sigue funcionando exactamente
  igual que antes.
