# pip install pywin32 requests
# (tkinter viene incluido con Python en Windows, no hace falta instalarlo)
#
# Version con ventana grafica del script de envio de boletas. Hace
# exactamente lo mismo que enviar_boletas.py (login al sistema web, elegir
# periodo, mandar por Outlook, avisar el resultado), pero con una interfaz
# de verdad en vez del Simbolo del sistema.
#
# Para que no aparezca ninguna ventana negra de consola, este archivo
# termina en .pyw (Windows lo abre con "pythonw" en vez de "python").

import base64
import csv
import os
import queue
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

import requests

URL_BASE = "https://adms-asistencias-production.up.railway.app"


class AppBoletas:
    def __init__(self, root):
        self.root = root
        self.root.title("Envío de Boletas de Pago")
        self.root.geometry("640x580")
        self.root.resizable(False, False)

        self.sesion = requests.Session()
        self.periodos = []
        self.periodo_seleccionado = None
        self.pendientes = []
        self.sin_correo = []
        self.nombre_periodo = ""
        self.cola_log = queue.Queue()

        self._construir_pantalla_login()
        self.root.after(150, self._procesar_cola_log)

    # ================================================================
    # PANTALLA 1: Login
    # ================================================================
    def _construir_pantalla_login(self):
        self._limpiar_pantalla()

        marco = ttk.Frame(self.root, padding=30)
        marco.pack(expand=True)

        ttk.Label(marco, text="Envío de Boletas de Pago", font=("Segoe UI", 16, "bold")).pack(pady=(0, 4))
        ttk.Label(marco, text="Ingresa con tu usuario del sistema web", foreground="#666").pack(pady=(0, 20))

        ttk.Label(marco, text="Usuario:").pack(anchor="w")
        self.entrada_usuario = ttk.Entry(marco, width=38)
        self.entrada_usuario.pack(pady=(2, 12))
        self.entrada_usuario.focus()

        ttk.Label(marco, text="Contraseña:").pack(anchor="w")
        self.entrada_password = ttk.Entry(marco, width=38, show="●")
        self.entrada_password.pack(pady=(2, 20))
        self.entrada_password.bind("<Return>", lambda evento: self._iniciar_sesion())

        self.boton_login = ttk.Button(marco, text="Iniciar sesión", command=self._iniciar_sesion)
        self.boton_login.pack()

        self.etiqueta_error_login = ttk.Label(marco, text="", foreground="#b3413a")
        self.etiqueta_error_login.pack(pady=(12, 0))

    def _iniciar_sesion(self):
        usuario = self.entrada_usuario.get().strip()
        contrasena = self.entrada_password.get()

        if not usuario or not contrasena:
            self.etiqueta_error_login.config(text="Completa usuario y contraseña.")
            return

        self.boton_login.config(state="disabled", text="Ingresando...")
        self.etiqueta_error_login.config(text="")
        self.root.update()

        try:
            resp = self.sesion.post(
                f"{URL_BASE}/login",
                data={"username": usuario, "password": contrasena},
                allow_redirects=False,
                timeout=15
            )
        except Exception as error:
            self.etiqueta_error_login.config(text=f"No se pudo conectar: {error}")
            self.boton_login.config(state="normal", text="Iniciar sesión")
            return

        if resp.status_code != 302:
            self.etiqueta_error_login.config(text="Usuario o contraseña incorrectos.")
            self.boton_login.config(state="normal", text="Iniciar sesión")
            return

        self._cargar_periodos()

    # ================================================================
    # PANTALLA 2: Elegir periodo
    # ================================================================
    def _cargar_periodos(self):
        try:
            resp = self.sesion.get(f"{URL_BASE}/api/periodos", timeout=15)
            resp.raise_for_status()
            self.periodos = resp.json()["periodos"]
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo obtener la lista de periodos:\n{error}")
            self.boton_login.config(state="normal", text="Iniciar sesión")
            return

        if not self.periodos:
            messagebox.showinfo("Sin periodos", "Todavía no hay ningún periodo de pago creado en el sistema.")
            self.boton_login.config(state="normal", text="Iniciar sesión")
            return

        self._construir_pantalla_periodos()

    def _construir_pantalla_periodos(self):
        self._limpiar_pantalla()

        marco = ttk.Frame(self.root, padding=20)
        marco.pack(fill="both", expand=True)

        ttk.Label(marco, text="Elige el periodo a enviar", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 15))

        self.lista_periodos = tk.Listbox(marco, height=10, font=("Segoe UI", 10))
        self.lista_periodos.pack(fill="x", pady=(0, 15))

        for p in self.periodos:
            pendientes_n = p["total_cargadas"] - p["total_enviadas"] - p["total_error"]
            texto = f"{p['nombre']}   —   {pendientes_n} pendiente(s), {p['total_enviadas']} ya enviada(s)"
            self.lista_periodos.insert("end", texto)

        self.lista_periodos.bind("<Double-Button-1>", lambda evento: self._ver_pendientes())
        if self.periodos:
            self.lista_periodos.selection_set(0)

        ttk.Button(marco, text="Ver boletas pendientes  →", command=self._ver_pendientes).pack()

    def _ver_pendientes(self):
        seleccion = self.lista_periodos.curselection()
        if not seleccion:
            messagebox.showwarning("Selecciona un periodo", "Haz clic en un periodo de la lista primero.")
            return

        self.periodo_seleccionado = self.periodos[seleccion[0]]

        try:
            resp = self.sesion.get(
                f"{URL_BASE}/api/periodos/{self.periodo_seleccionado['id']}/pendientes", timeout=15
            )
            resp.raise_for_status()
            datos = resp.json()
            self.pendientes = datos["pendientes"]
            self.nombre_periodo = datos["periodo_nombre"]
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo obtener las boletas pendientes:\n{error}")
            return

        self._construir_pantalla_confirmacion()

    # ================================================================
    # PANTALLA 3: Confirmar y enviar
    # ================================================================
    def _construir_pantalla_confirmacion(self):
        self._limpiar_pantalla()

        marco = ttk.Frame(self.root, padding=20)
        marco.pack(fill="both", expand=True)

        encabezado = ttk.Frame(marco)
        encabezado.pack(fill="x", pady=(0, 10))
        ttk.Button(encabezado, text="← Volver", command=self._construir_pantalla_periodos).pack(side="left")
        ttk.Label(encabezado, text=self.nombre_periodo, font=("Segoe UI", 14, "bold")).pack(side="left", padx=15)

        if not self.pendientes:
            ttk.Label(marco, text="No hay boletas pendientes en este periodo. ¡Ya está todo enviado!").pack(pady=30)
            return

        ttk.Label(marco, text=f"{len(self.pendientes)} boleta(s) pendiente(s):").pack(anchor="w", pady=(5, 5))

        marco_lista = ttk.Frame(marco)
        marco_lista.pack(fill="both", expand=False, pady=(0, 10))

        columnas = ("nombre", "correo", "archivos")
        self.tabla = ttk.Treeview(marco_lista, columns=columnas, show="headings", height=7)
        self.tabla.heading("nombre", text="Trabajador")
        self.tabla.heading("correo", text="Correo(s) destino")
        self.tabla.heading("archivos", text="PDFs")
        self.tabla.column("nombre", width=220)
        self.tabla.column("correo", width=260)
        self.tabla.column("archivos", width=50, anchor="center")
        self.tabla.pack(fill="both", expand=True)

        self.sin_correo = []
        for b in self.pendientes:
            sin_archivos = not b["archivos"]
            correo = b["correo_destino"].replace(";", ", ") if b["correo_destino"] else "⚠ SIN CORREO"
            if not b["correo_destino"] or sin_archivos:
                self.sin_correo.append(b)
            texto_archivos = "⚠ 0" if sin_archivos else str(len(b["archivos"]))
            self.tabla.insert("", "end", values=(b["nombre_trabajador"], correo, texto_archivos))

        if self.sin_correo:
            ttk.Label(
                marco,
                text=f"⚠ {len(self.sin_correo)} trabajador(es) se van a omitir (sin correo o sin PDF) — revisa la tabla.",
                foreground="#b45309"
            ).pack(anchor="w", pady=(0, 5))

        self.boton_enviar = ttk.Button(marco, text="Enviar boletas pendientes", command=self._confirmar_envio)
        self.boton_enviar.pack(pady=(5, 10))

        ttk.Label(marco, text="Registro:").pack(anchor="w")
        self.area_log = scrolledtext.ScrolledText(marco, height=9, font=("Consolas", 9), state="disabled")
        self.area_log.pack(fill="both", expand=True)

    def _confirmar_envio(self):
        cantidad = len(self.pendientes) - len(self.sin_correo)
        if cantidad == 0:
            messagebox.showwarning("Nada para enviar", "Ningún trabajador pendiente tiene correo configurado.")
            return

        respuesta = messagebox.askyesno(
            "Confirmar envío",
            f"¿Enviar {cantidad} boleta(s) por correo ahora?\n\n"
            f"Esta acción manda correos reales y no se puede deshacer."
        )
        if not respuesta:
            return

        self.boton_enviar.config(state="disabled", text="Enviando...")
        hilo = threading.Thread(target=self._enviar_boletas_hilo, daemon=True)
        hilo.start()

    def _log(self, mensaje):
        self.cola_log.put(("log", mensaje))

    def _notificar_fin(self, resumen):
        self.cola_log.put(("fin", resumen))

    def _procesar_cola_log(self):
        try:
            while True:
                tipo, dato = self.cola_log.get_nowait()

                if tipo == "log":
                    self.area_log.config(state="normal")
                    self.area_log.insert("end", dato + "\n")
                    self.area_log.see("end")
                    self.area_log.config(state="disabled")

                elif tipo == "fin":
                    self.boton_enviar.config(state="normal", text="Enviar boletas pendientes")
                    if dato.get("fallo_outlook"):
                        messagebox.showerror(
                            "No se pudo conectar con Outlook",
                            "Verifica que Outlook esté abierto en esta computadora con tu cuenta iniciada, "
                            "y vuelve a intentar."
                        )
                    else:
                        messagebox.showinfo(
                            "Proceso terminado",
                            f"Enviados correctamente: {dato['ok']}\nErrores: {dato['errores']}\n\n"
                            f"Log guardado en:\n{dato['archivo']}"
                        )
        except queue.Empty:
            pass
        self.root.after(150, self._procesar_cola_log)

    def _enviar_boletas_hilo(self):
        # win32com necesita que el hilo este "inicializado" para COM, o
        # falla al intentar abrir Outlook desde un hilo que no es el
        # principal.
        import pythoncom
        pythoncom.CoInitialize()

        try:
            import win32com.client
            outlook = win32com.client.Dispatch("Outlook.Application")
        except Exception as error:
            self._log(f"✖ No se pudo conectar con Outlook: {error}")
            self._notificar_fin({"fallo_outlook": True})
            pythoncom.CoUninitialize()
            return

        resultados = []
        carpeta_temporal = tempfile.mkdtemp(prefix="boletas_")

        self._log("=" * 50)
        self._log("INICIANDO ENVÍO...")
        self._log("=" * 50)

        for indice, boleta in enumerate(self.pendientes):
            nombre = boleta["nombre_trabajador"]

            if not boleta["correo_destino"] or not boleta["archivos"]:
                continue

            self._log(f"[{indice + 1}/{len(self.pendientes)}] {nombre}...")

            try:
                rutas_temp = []
                for archivo in boleta["archivos"]:
                    contenido_pdf = base64.b64decode(archivo["contenido_base64"])
                    ruta_temp = os.path.join(carpeta_temporal, f"{boleta['id']}_{archivo['nombre']}")
                    with open(ruta_temp, "wb") as archivo_temp:
                        archivo_temp.write(contenido_pdf)
                    rutas_temp.append(ruta_temp)

                destinatarios = [c.strip() for c in boleta["correo_destino"].split(";") if c.strip()]

                mail = outlook.CreateItem(0)
                mail.To = "; ".join(destinatarios)
                mail.Subject = f"Boleta de pago – {self.nombre_periodo}"
                mail.Body = (
                    f"Estimado/a {nombre},\n\n"
                    f"Adjunto encontrará su boleta de pago correspondiente al período {self.nombre_periodo}.\n\n"
                    f"Ante cualquier consulta, no dude en contactarnos.\n\n"
                    f"Saludos,\nRecursos Humanos"
                )
                for ruta_temp in rutas_temp:
                    mail.Attachments.Add(os.path.abspath(ruta_temp))
                mail.Send()

                self.sesion.post(
                    f"{URL_BASE}/api/boletas/{boleta['id']}/estado",
                    json={"estado": "ENVIADO"}, timeout=15
                )
                self._log("   ✔ Enviado correctamente")
                estado = "OK"

            except Exception as error:
                self._log(f"   ✖ Error: {error}")
                estado = f"ERROR: {error}"
                try:
                    self.sesion.post(
                        f"{URL_BASE}/api/boletas/{boleta['id']}/estado",
                        json={"estado": "ERROR", "detalle": str(error)}, timeout=15
                    )
                except Exception:
                    self._log("     (además, no se pudo avisar al sistema del error)")

            resultados.append({
                "nombre": nombre,
                "correo": boleta["correo_destino"],
                "estado": estado,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
            })

        pythoncom.CoUninitialize()

        nombre_log = f"log_envios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(nombre_log, "w", newline="", encoding="utf-8-sig") as archivo_log:
            writer = csv.DictWriter(archivo_log, fieldnames=["nombre", "correo", "estado", "fecha"])
            writer.writeheader()
            writer.writerows(resultados)

        ok = sum(r["estado"] == "OK" for r in resultados)
        errores = len(resultados) - ok

        self._log("=" * 50)
        self._log(f"TERMINADO — Enviados: {ok}   Errores: {errores}")
        self._log(f"Log guardado en: {nombre_log}")
        self._log("=" * 50)

        self._notificar_fin({"fallo_outlook": False, "ok": ok, "errores": errores, "archivo": nombre_log})

    # ================================================================
    def _limpiar_pantalla(self):
        for widget in self.root.winfo_children():
            widget.destroy()


if __name__ == "__main__":
    raiz = tk.Tk()
    app = AppBoletas(raiz)
    raiz.mainloop()
