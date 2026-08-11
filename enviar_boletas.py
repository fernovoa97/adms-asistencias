# pip install pywin32 requests
#
# Este script corre en TU computadora (la que tiene Outlook instalado y
# con tu sesion iniciada) -- no corre en el servidor de Railway.
#
# Se conecta al sistema web para:
#   1. Pedir la lista de periodos de pago existentes
#   2. Traer las boletas PENDIENTES del periodo que elijas (con su PDF)
#   3. Enviarlas por tu Outlook, una por una
#   4. Avisarle de vuelta al sistema el resultado de cada una, para que
#      el estado (Pendiente / Enviado / Error) se actualice solo en la
#      pagina web.

import win32com.client
import requests
import getpass
import base64
import tempfile
import os
import csv
import sys
from datetime import datetime

# ============================================================
# CONFIGURACION
# ============================================================

URL_BASE = "https://adms-asistencias-production.up.railway.app"

# ============================================================
# LOGIN AL SISTEMA WEB
# ============================================================

print("=" * 60)
print("LOGIN AL SISTEMA DE BOLETAS")
print("=" * 60)

usuario = input("Usuario: ").strip()
contrasena = getpass.getpass("Contraseña: ")

sesion = requests.Session()

resp = sesion.post(
    f"{URL_BASE}/login",
    data={"username": usuario, "password": contrasena},
    allow_redirects=False
)

# Si el login funciona, el servidor responde con una redireccion (302).
# Si vuelve a mostrar el formulario (200), las credenciales estaban mal.
if resp.status_code != 302:
    print("\nUsuario o contraseña incorrectos.")
    sys.exit()

print("Sesión iniciada correctamente.\n")

# ============================================================
# ELEGIR PERIODO
# ============================================================

resp = sesion.get(f"{URL_BASE}/api/periodos")
resp.raise_for_status()
periodos = resp.json()["periodos"]

if not periodos:
    print("Todavía no hay ningún periodo de pago creado en el sistema.")
    sys.exit()

print("=" * 60)
print("PERIODOS DISPONIBLES")
print("=" * 60)

for indice, p in enumerate(periodos, start=1):
    pendientes_count = p["total_cargadas"] - p["total_enviadas"] - p["total_error"]
    print(f"{indice}. {p['nombre']}  "
          f"({pendientes_count} pendiente(s), {p['total_enviadas']} ya enviada(s), "
          f"{p['total_error']} con error)")

seleccion = input("\nNúmero del periodo a enviar: ").strip()

try:
    periodo = periodos[int(seleccion) - 1]
except (ValueError, IndexError):
    print("Selección inválida.")
    sys.exit()

periodo_id = periodo["id"]

# ============================================================
# OBTENER BOLETAS PENDIENTES DE ESE PERIODO
# ============================================================

resp = sesion.get(f"{URL_BASE}/api/periodos/{periodo_id}/pendientes")
resp.raise_for_status()
datos = resp.json()

pendientes = datos["pendientes"]
nombre_periodo = datos["periodo_nombre"]

if not pendientes:
    print(f"\nNo hay boletas pendientes en '{nombre_periodo}'. No hay nada que enviar.")
    sys.exit()

print()
print("=" * 60)
print(f"BOLETAS PENDIENTES EN: {nombre_periodo}")
print("=" * 60)

sin_correo = []

for b in pendientes:
    if b["correo_destino"]:
        print(f"✔ {b['nombre_trabajador']}  ->  {b['correo_destino']}")
    else:
        print(f"✖ {b['nombre_trabajador']}  ->  SIN CORREO DE DESTINO")
        sin_correo.append(b)

if sin_correo:
    print()
    print(f"Hay {len(sin_correo)} trabajador(es) sin correo de destino configurado.")
    print("Se van a omitir -- corrígelo desde la página web y vuelve a correr el script para esos.")

print(f"\nTotal a enviar ahora: {len(pendientes) - len(sin_correo)} de {len(pendientes)}")

confirmacion = input("\nEscriba OK para comenzar el envío: ").strip().upper()

if confirmacion != "OK":
    print("\nProceso cancelado.")
    sys.exit()

# ============================================================
# OUTLOOK
# ============================================================

outlook = win32com.client.Dispatch("Outlook.Application")

# ============================================================
# ENVIO
# ============================================================

resultados = []
carpeta_temporal = tempfile.mkdtemp(prefix="boletas_")

print("\n")
print("=" * 60)
print("INICIANDO ENVÍO...")
print("=" * 60)

for indice, boleta in enumerate(pendientes):

    nombre = boleta["nombre_trabajador"]
    print(f"\n[{indice + 1}/{len(pendientes)}] {nombre}")

    if not boleta["correo_destino"]:
        estado_local = "ERROR: sin correo de destino"
        print(f"✖ {estado_local}")
        resultados.append({
            "nombre": nombre, "correo": "", "estado": estado_local,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        continue

    try:
        # Outlook necesita una RUTA de archivo para adjuntar, no los bytes
        # directamente -- por eso lo guardamos primero en una carpeta
        # temporal.
        contenido_pdf = base64.b64decode(boleta["archivo_base64"])
        ruta_temp = os.path.join(carpeta_temporal, boleta["archivo_nombre"])
        with open(ruta_temp, "wb") as archivo_temp:
            archivo_temp.write(contenido_pdf)

        mail = outlook.CreateItem(0)
        mail.To = boleta["correo_destino"]
        mail.Subject = f"Boleta de pago – {nombre_periodo}"
        mail.Body = f"""Estimado/a {nombre},

Adjunto encontrará su boleta de pago correspondiente al período {nombre_periodo}.

Ante cualquier consulta, no dude en contactarnos.

Saludos,
Recursos Humanos"""
        mail.Attachments.Add(os.path.abspath(ruta_temp))
        mail.Send()

        # Avisamos al sistema que esta boleta ya se envio
        sesion.post(
            f"{URL_BASE}/api/boletas/{boleta['id']}/estado",
            json={"estado": "ENVIADO"}
        )

        estado_local = "OK"
        print("✔ Enviado correctamente")

    except Exception as error:
        estado_local = f"ERROR: {error}"
        print(f"✖ {estado_local}")

        try:
            sesion.post(
                f"{URL_BASE}/api/boletas/{boleta['id']}/estado",
                json={"estado": "ERROR", "detalle": str(error)}
            )
        except Exception:
            print("  (además, no se pudo avisar al sistema del error)")

    resultados.append({
        "nombre": nombre,
        "correo": boleta["correo_destino"],
        "estado": estado_local,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
    })

# ============================================================
# LOG LOCAL
# ============================================================

nombre_log = f"log_envios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

with open(nombre_log, "w", newline="", encoding="utf-8-sig") as archivo_log:
    writer = csv.DictWriter(archivo_log, fieldnames=["nombre", "correo", "estado", "fecha"])
    writer.writeheader()
    writer.writerows(resultados)

# ============================================================
# RESUMEN
# ============================================================

ok = sum(r["estado"] == "OK" for r in resultados)
errores = len(resultados) - ok

print("\n")
print("=" * 60)
print("PROCESO FINALIZADO")
print("=" * 60)
print(f"Enviados correctamente : {ok}")
print(f"Errores                : {errores}")
print(f"Log generado           : {nombre_log}")
print("=" * 60)
