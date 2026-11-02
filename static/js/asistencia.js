// ---------- Panel de asistencia: detalle de celdas, registro e importacion ----------

const panelTabla = document.getElementById('panelTabla');
const tooltip = document.getElementById('asistTooltip');
const CLAVE_SCROLL = 'asistenciaScrollX';

const registroOverlay = document.getElementById('registroOverlay');
const registroForm = document.getElementById('registroForm');
const registroError = document.getElementById('registroError');
const registroDetalle = document.getElementById('registroDetalle');
const registroTrabajador = document.getElementById('registroTrabajador');
const registroFecha = document.getElementById('registroFecha');
const registroHora = document.getElementById('registroHora');
const registroTipo = document.getElementById('registroTipo');
const registroObservacion = document.getElementById('registroObservacion');
const registroQuitarBtn = document.getElementById('registroQuitarBtn');

// Tras guardar se recarga la pagina: esto evita volver al inicio de la tabla.
function recargarPanel() {
  try {
    if (panelTabla) sessionStorage.setItem(CLAVE_SCROLL, panelTabla.scrollLeft);
  } catch (err) {
    // sin almacenamiento, la tabla simplemente vuelve al inicio
  }
  location.reload();
}

try {
  const scrollGuardado = sessionStorage.getItem(CLAVE_SCROLL);
  if (panelTabla && scrollGuardado) panelTabla.scrollLeft = Number(scrollGuardado);
  sessionStorage.removeItem(CLAVE_SCROLL);
} catch (err) {
  // sin almacenamiento no hay nada que restaurar
}

function lineasDeDetalle(celda) {
  const lineas = [];
  if (celda.tipo) lineas.push(['Tipo', celda.tipo]);
  if (celda.observacion) lineas.push(['Motivo u observación', celda.observacion]);
  if (celda.hora) lineas.push(['Entrada', celda.hora]);
  if (celda.segundos > 0) lineas.push(['Tardanza', celda.tardanza]);
  if (celda.hora && celda.origen) lineas.push(['Marcación', celda.origen]);
  if (celda.registrado_por) lineas.push(['Registrado por', celda.registrado_por]);
  return lineas;
}

function pintarDetalle(contenedor, lineas) {
  contenedor.replaceChildren(...lineas.map(([etiqueta, valor]) => {
    const fila = document.createElement('div');
    const titulo = document.createElement('strong');
    titulo.textContent = `${etiqueta}: `;
    fila.append(titulo, valor);
    return fila;
  }));
}

// ---------- Detalle al pasar el cursor ----------

function celdaDe(evento) {
  const boton = evento.target.closest('[data-celda]');
  return boton ? { boton, celda: JSON.parse(boton.dataset.celda) } : null;
}

function mostrarTooltip(evento) {
  const encontrada = celdaDe(evento);
  if (!encontrada) return;

  const lineas = lineasDeDetalle(encontrada.celda);
  if (lineas.length === 0) return;

  pintarDetalle(tooltip, lineas);
  tooltip.hidden = false;

  const caja = encontrada.boton.getBoundingClientRect();
  const izquierda = Math.min(caja.left, window.innerWidth - tooltip.offsetWidth - 8);
  const arriba = caja.bottom + tooltip.offsetHeight + 8 > window.innerHeight
    ? caja.top - tooltip.offsetHeight - 6
    : caja.bottom + 6;
  tooltip.style.left = `${Math.max(8, izquierda)}px`;
  tooltip.style.top = `${Math.max(8, arriba)}px`;
}

function ocultarTooltip() {
  tooltip.hidden = true;
}

if (panelTabla) {
  panelTabla.addEventListener('mouseover', mostrarTooltip);
  panelTabla.addEventListener('mouseout', ocultarTooltip);
  panelTabla.addEventListener('focusin', mostrarTooltip);
  panelTabla.addEventListener('focusout', ocultarTooltip);
  panelTabla.addEventListener('scroll', ocultarTooltip);
  panelTabla.addEventListener('click', (e) => {
    const encontrada = celdaDe(e);
    if (encontrada) abrirRegistro(encontrada.celda);
  });
}

// ---------- Formulario de registro ----------

function tipoRegistroElegido() {
  return registroForm.querySelector('[name="tipoRegistro"]:checked').value;
}

function actualizarCamposRegistro() {
  const esMarcacion = tipoRegistroElegido() === 'marcacion';
  document.getElementById('camposMarcacion').hidden = !esMarcacion;
  document.getElementById('camposJustificacion').hidden = esMarcacion;
}

registroForm.querySelectorAll('[name="tipoRegistro"]').forEach((opcion) => {
  opcion.addEventListener('change', actualizarCamposRegistro);
});

function mostrarErrorRegistro(mensaje) {
  registroError.textContent = mensaje;
  registroError.style.display = 'block';
}

function abrirRegistro(celda) {
  ocultarTooltip();
  registroForm.reset();
  registroError.style.display = 'none';

  const conCelda = Boolean(celda);
  const tieneJustificacion = conCelda && (celda.estado === 'justificado' || celda.estado === 'falta');
  const lineas = conCelda ? lineasDeDetalle(celda) : [];

  document.getElementById('campoTrabajador').hidden = conCelda;
  document.getElementById('campoFecha').hidden = conCelda;
  document.getElementById('registroTitulo').textContent = conCelda
    ? `${celda.trabajador} · ${celda.fecha}`
    : 'Registrar asistencia';

  registroDetalle.hidden = lineas.length === 0;
  registroDetalle.style.background = (conCelda && celda.color) || 'var(--superficie-suave)';
  registroDetalle.style.color = (conCelda && celda.color_texto) || '';
  pintarDetalle(registroDetalle, lineas);

  document.getElementById('avisoReemplazo').hidden = !tieneJustificacion;
  registroQuitarBtn.hidden = !(tieneJustificacion || (conCelda && celda.origen && celda.origen !== 'Dispositivo biométrico'));

  if (conCelda) {
    registroTrabajador.value = celda.trabajador_id;
    registroFecha.value = celda.fecha;
    registroHora.value = celda.hora || '';
    registroTipo.value = celda.tipo_id || '';
    registroObservacion.value = tieneJustificacion ? celda.observacion || '' : '';
    if (tieneJustificacion) {
      registroForm.querySelector('[value="justificacion"]').checked = true;
    }
  }

  actualizarCamposRegistro();
  registroOverlay.hidden = false;
}

function cerrarRegistro() {
  registroOverlay.hidden = true;
}

document.getElementById('nuevoRegistroBtn').addEventListener('click', () => abrirRegistro(null));
document.getElementById('registroCancelarBtn').addEventListener('click', cerrarRegistro);
registroOverlay.addEventListener('click', (e) => {
  if (e.target === registroOverlay) cerrarRegistro();
});

async function enviarRegistro(method, cuerpo) {
  registroError.style.display = 'none';

  try {
    const res = await fetch('/api/asistencia/registro', {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cuerpo)
    });
    const data = await res.json();

    if (!res.ok) {
      mostrarErrorRegistro(data.error || 'No se pudo guardar el registro');
      return;
    }
    recargarPanel();
  } catch (err) {
    mostrarErrorRegistro('Error de conexión con el servidor');
  }
}

registroForm.addEventListener('submit', (e) => {
  e.preventDefault();

  if (!registroTrabajador.value || !registroFecha.value) {
    mostrarErrorRegistro('Elige el trabajador y la fecha.');
    return;
  }

  enviarRegistro('POST', {
    trabajadorId: Number(registroTrabajador.value),
    fecha: registroFecha.value,
    tipoRegistro: tipoRegistroElegido(),
    hora: registroHora.value,
    tipoId: registroTipo.value ? Number(registroTipo.value) : null,
    observacion: registroObservacion.value
  });
});

registroQuitarBtn.addEventListener('click', () => {
  if (!confirm('¿Quitar el registro de este día? Si había una marcación del dispositivo, vuelve a quedar vigente.')) return;

  enviarRegistro('DELETE', {
    trabajadorId: Number(registroTrabajador.value),
    fecha: registroFecha.value
  });
});

// ---------- Importacion de marcaciones ----------

const importarOverlay = document.getElementById('importarOverlay');
const importarForm = document.getElementById('importarForm');
const importarError = document.getElementById('importarError');
const importarExito = document.getElementById('importarExito');
const importarDetalle = document.getElementById('importarDetalle');
let huboImportacion = false;

document.getElementById('importarBtn').addEventListener('click', () => {
  importarForm.reset();
  importarError.style.display = 'none';
  importarExito.style.display = 'none';
  importarDetalle.hidden = true;
  importarOverlay.hidden = false;
});

function cerrarImportar() {
  importarOverlay.hidden = true;
  if (huboImportacion) recargarPanel();
}

document.getElementById('importarCerrarBtn').addEventListener('click', cerrarImportar);

importarForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  importarError.style.display = 'none';
  importarExito.style.display = 'none';
  importarDetalle.hidden = true;

  const boton = document.getElementById('importarSubirBtn');
  const formulario = new FormData();
  formulario.append('archivo', document.getElementById('importarArchivo').files[0]);

  boton.disabled = true;
  boton.textContent = 'Importando...';

  try {
    const res = await fetch('/api/asistencia/importar', { method: 'POST', body: formulario });
    const data = await res.json();

    if (!res.ok) {
      importarError.textContent = data.error || 'No se pudo importar el archivo';
      importarError.style.display = 'block';
      return;
    }

    huboImportacion = huboImportacion || data.insertadas > 0;
    importarExito.textContent = `${data.insertadas} marcación(es) nueva(s), ${data.duplicadas} ya existían, ${data.errores} con error.`;
    importarExito.style.display = 'block';

    importarDetalle.replaceChildren(...data.detalle.map((texto) => {
      const item = document.createElement('li');
      item.textContent = texto;
      return item;
    }));
    importarDetalle.hidden = data.detalle.length === 0;
  } catch (err) {
    importarError.textContent = 'Error de conexión con el servidor';
    importarError.style.display = 'block';
  } finally {
    boton.disabled = false;
    boton.textContent = 'Importar';
  }
});
