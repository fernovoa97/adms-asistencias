// ---------- Justificar asistencia (varios trabajadores, rango de fechas) ----------

const searchWorkerInput = document.getElementById('searchWorkerInput');
const workerResults = document.getElementById('workerResults');
const seleccionadosArea = document.getElementById('seleccionadosArea');

let debounceTimerAjustes = null;
let trabajadoresSeleccionados = []; // [{id, nombres, apellidos}, ...]

searchWorkerInput.addEventListener('input', () => {
  clearTimeout(debounceTimerAjustes);
  const q = searchWorkerInput.value.trim();

  if (!q) {
    workerResults.innerHTML = '';
    return;
  }

  debounceTimerAjustes = setTimeout(() => buscarTrabajador(q), 180);
});

async function buscarTrabajador(q) {
  try {
    const res = await fetch(`/api/ajustes/buscar-trabajador?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderResultadosBusqueda(data.results || []);
  } catch (err) {
    workerResults.innerHTML = '<div class="empty-state">Error al buscar</div>';
  }
}

function renderResultadosBusqueda(results) {
  if (results.length === 0) {
    workerResults.innerHTML = '<div class="empty-state">No se encontraron trabajadores</div>';
    return;
  }

  workerResults.innerHTML = '';
  results.forEach((w) => {
    const yaEsta = trabajadoresSeleccionados.some((s) => s.id === w.id);
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `
      <div>
        <div class="name">${escapeHtml(w.apellidos)} ${escapeHtml(w.nombres)}</div>
        <div class="meta">DNI: ${escapeHtml(w.dni || '—')} ${w.codigo_empleado ? '· Código: ' + escapeHtml(w.codigo_empleado) : ''}</div>
      </div>
      <span class="tag">${yaEsta ? 'Ya agregado' : '+ Agregar'}</span>
    `;
    if (!yaEsta) {
      item.addEventListener('click', () => agregarSeleccionado(w));
    }
    workerResults.appendChild(item);
  });
}

function agregarSeleccionado(w) {
  if (trabajadoresSeleccionados.some((s) => s.id === w.id)) return;
  trabajadoresSeleccionados.push(w);
  searchWorkerInput.value = '';
  workerResults.innerHTML = '';
  renderSeleccionados();
}

function quitarSeleccionado(id) {
  trabajadoresSeleccionados = trabajadoresSeleccionados.filter((s) => s.id !== id);
  renderSeleccionados();
}

function renderSeleccionados() {
  if (trabajadoresSeleccionados.length === 0) {
    seleccionadosArea.innerHTML = '<p class="muted">Todavía no agregaste a ningún trabajador.</p>';
    return;
  }

  seleccionadosArea.innerHTML = `
    <p class="muted" style="margin-bottom:6px;">${trabajadoresSeleccionados.length} trabajador(es) seleccionado(s):</p>
    <div style="display:flex;flex-wrap:wrap;gap:6px;">
      ${trabajadoresSeleccionados.map((w) => `
        <span class="tag" style="display:inline-flex;align-items:center;gap:6px;">
          ${escapeHtml(w.apellidos)} ${escapeHtml(w.nombres)}
          <button type="button" data-quitar="${w.id}" style="background:none;border:none;cursor:pointer;color:inherit;font-weight:700;line-height:1;padding:0;">×</button>
        </span>
      `).join('')}
    </div>
  `;
  seleccionadosArea.querySelectorAll('[data-quitar]').forEach((boton) => {
    boton.addEventListener('click', () => quitarSeleccionado(Number(boton.dataset.quitar)));
  });
}

renderSeleccionados();

document.getElementById('ajusteForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const successMsg = document.getElementById('ajusteSuccessMsg');
  const errorMsg = document.getElementById('ajusteErrorMsg');
  successMsg.style.display = 'none';
  errorMsg.style.display = 'none';

  const fechaInicio = document.getElementById('fechaInicioAjuste').value;
  const fechaFin = document.getElementById('fechaFinAjuste').value;
  const motivo = document.getElementById('motivoAjuste').value.trim();
  const observacion = document.getElementById('observacionAjuste').value.trim();

  if (trabajadoresSeleccionados.length === 0) {
    errorMsg.textContent = 'Agrega al menos un trabajador.';
    errorMsg.style.display = 'block';
    return;
  }
  if (!fechaInicio || !fechaFin || !motivo) {
    errorMsg.textContent = 'El rango de fechas y el motivo son obligatorios.';
    errorMsg.style.display = 'block';
    return;
  }

  const btn = document.getElementById('ajusteSubmitBtn');
  btn.disabled = true;
  btn.textContent = 'Guardando...';

  try {
    const res = await fetch('/api/ajustes/masivo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        trabajadorIds: trabajadoresSeleccionados.map((w) => w.id),
        fechaInicio, fechaFin, motivo, observacion
      })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo guardar la justificación';
      errorMsg.style.display = 'block';
      return;
    }

    successMsg.textContent = `Se justificaron ${data.totalDias} día(s) para ${data.totalTrabajadores} trabajador(es) (${data.totalRegistros} registro(s) en total).`;
    successMsg.style.display = 'block';
    document.getElementById('ajusteForm').reset();
    trabajadoresSeleccionados = [];
    renderSeleccionados();
    cargarTodosLosAjustes();
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Guardar justificación';
  }
});

cargarMotivos();
bindNuevoMotivoModal();

// ---------- Motivos de justificacion (combo administrable) ----------

async function cargarMotivos(seleccionarNombre) {
  const select = document.getElementById('motivoAjuste');
  if (!select) return;
  try {
    const res = await fetch('/api/motivos-justificacion');
    const data = await res.json();
    select.innerHTML = '<option value="">Elige un motivo...</option>';
    (data.motivos || []).forEach((m) => {
      const opt = document.createElement('option');
      opt.value = m.nombre;
      opt.textContent = m.nombre;
      select.appendChild(opt);
    });
    if (seleccionarNombre) select.value = seleccionarNombre;
  } catch (err) {
    // si falla, se queda solo la opcion por defecto
  }
}

function bindNuevoMotivoModal() {
  const overlay = document.getElementById('nuevoMotivoModalOverlay');
  const btnAbrir = document.getElementById('nuevoMotivoBtn');
  if (!overlay || !btnAbrir) return;

  btnAbrir.addEventListener('click', () => {
    document.getElementById('nuevoMotivoErrorMsg').style.display = 'none';
    document.getElementById('nuevoMotivoNombre').value = '';
    overlay.style.display = 'flex';
  });

  document.getElementById('nuevoMotivoCancelarBtn').addEventListener('click', () => {
    overlay.style.display = 'none';
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.style.display = 'none';
  });

  document.getElementById('nuevoMotivoGuardarBtn').addEventListener('click', async () => {
    const errorMsg = document.getElementById('nuevoMotivoErrorMsg');
    errorMsg.style.display = 'none';

    const nombre = document.getElementById('nuevoMotivoNombre').value.trim();
    if (!nombre) {
      errorMsg.textContent = 'Escribe el nombre del motivo.';
      errorMsg.style.display = 'block';
      return;
    }

    try {
      const res = await fetch('/api/motivos-justificacion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre })
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo crear el motivo';
        errorMsg.style.display = 'block';
        return;
      }

      await cargarMotivos(data.nombre);
      cargarTipos();
      overlay.style.display = 'none';
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    }
  });
}

async function eliminarAjustes(ids, mensaje) {
  if (!confirm(mensaje)) return;

  try {
    const res = await fetch('/api/ajustes', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids })
    });
    if (!res.ok) {
      alert('No se pudo eliminar');
      return;
    }
    cargarTodosLosAjustes();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

// ---------- Feriados ----------

document.getElementById('feriadoForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const errorMsg = document.getElementById('feriadoErrorMsg');
  errorMsg.style.display = 'none';

  const fecha = document.getElementById('nuevaFechaFeriado').value;
  const descripcion = document.getElementById('nuevaDescripcionFeriado').value.trim();

  if (!fecha) {
    errorMsg.textContent = 'La fecha es obligatoria';
    errorMsg.style.display = 'block';
    return;
  }

  try {
    const res = await fetch('/api/feriados', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fecha, descripcion })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo guardar el feriado';
      errorMsg.style.display = 'block';
      return;
    }

    document.getElementById('feriadoForm').reset();
    cargarFeriados();
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

async function cargarFeriados() {
  const lista = document.getElementById('feriadosList');
  try {
    const res = await fetch('/api/feriados');
    const data = await res.json();
    renderFeriados(data.feriados || []);
  } catch (err) {
    lista.innerHTML = '<p class="muted">Error al cargar</p>';
  }
}

function renderFeriados(feriados) {
  const lista = document.getElementById('feriadosList');

  if (feriados.length === 0) {
    lista.innerHTML = '<p class="muted">No hay feriados registrados.</p>';
    return;
  }

  lista.innerHTML = feriados
    .map((f) => `
      <div class="doc-item">
        <div class="doc-name">${f.fecha} ${f.descripcion ? '— ' + escapeHtml(f.descripcion) : ''}</div>
        <div class="doc-actions">
          <button class="btn danger" onclick="eliminarFeriado('${f.fecha}')">Eliminar</button>
        </div>
      </div>
    `)
    .join('');
}

async function eliminarFeriado(fecha) {
  if (!confirm('¿Eliminar este feriado?')) return;

  try {
    const res = await fetch(`/api/feriados/${fecha}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo eliminar');
      return;
    }
    cargarFeriados();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

// ---------- Todas las justificaciones (vista general) ----------

const DIAS_SEMANA = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
const MS_POR_DIA = 24 * 60 * 60 * 1000;

// Ids de las justificaciones con el detalle abierto: asi sigue abierto al
// recargar la lista despues de eliminar un dia.
const ajustesAbiertos = new Set();

function fechaUtc(fecha) {
  return new Date(`${fecha}T00:00:00Z`);
}

function nombreDia(fecha) {
  return DIAS_SEMANA[fechaUtc(fecha).getUTCDay()];
}

// Dos fechas son de la misma franja si entre ellas solo hay fin de semana
// (lo mismo que hace /api/ajustes/masivo: guarda solo de lunes a viernes).
function sonDiasSeguidos(fechaAnterior, fechaSiguiente) {
  const fin = fechaUtc(fechaSiguiente).getTime();
  for (let t = fechaUtc(fechaAnterior).getTime() + MS_POR_DIA; t < fin; t += MS_POR_DIA) {
    const dia = new Date(t).getUTCDay();
    if (dia !== 0 && dia !== 6) return false;
  }
  return true;
}

// La BD guarda un registro por dia y trabajador; aqui se juntan de nuevo en
// franjas: mismo trabajador, motivo y autor, en dias laborables seguidos.
function agruparEnFranjas(ajustes) {
  const ordenados = [...ajustes].sort((a, b) => a.fecha.localeCompare(b.fecha));
  const ultimaPorClave = new Map();
  const franjas = [];

  ordenados.forEach((a) => {
    const clave = JSON.stringify([a.trabajadorId, a.motivo, a.observacion, a.creado_por]);
    let franja = ultimaPorClave.get(clave);
    const ultimoDia = franja && franja.dias[franja.dias.length - 1].fecha;

    if (!franja || !sonDiasSeguidos(ultimoDia, a.fecha)) {
      franja = {
        trabajadorNombre: a.trabajadorNombre,
        motivo: a.motivo,
        observacion: a.observacion,
        creado_por: a.creado_por,
        dias: []
      };
      ultimaPorClave.set(clave, franja);
      franjas.push(franja);
    }
    franja.dias.push(a);
  });

  return franjas.sort((a, b) => b.dias[0].fecha.localeCompare(a.dias[0].fecha));
}

async function cargarTodosLosAjustes() {
  const lista = document.getElementById('listaTodosLosAjustes');
  try {
    const res = await fetch('/api/ajustes');
    const data = await res.json();
    renderTodosLosAjustes(data.ajustes || []);
  } catch (err) {
    lista.innerHTML = '<p class="muted">Error al cargar</p>';
  }
}

function periodoDeFranja(franja) {
  const desde = franja.dias[0].fecha;
  const hasta = franja.dias[franja.dias.length - 1].fecha;
  return desde === hasta ? desde : `${desde} al ${hasta}`;
}

function detalleDeFranja(franja) {
  const total = franja.dias.length;
  const dias = franja.dias.map((d) => `
    <div class="ajuste-dia">
      <span>${nombreDia(d.fecha)} ${d.fecha}${d.creadoEn ? ` <span class="muted">· registrado ${escapeHtml(d.creadoEn)}</span>` : ''}</span>
      <button type="button" class="btn danger" data-eliminar-dia="${d.id}">Eliminar día</button>
    </div>
  `).join('');

  return `
    <div class="ajuste-detalle-datos">
      <div><strong>Trabajador:</strong> ${escapeHtml(franja.trabajadorNombre)}</div>
      <div><strong>Motivo:</strong> ${escapeHtml(franja.motivo)}</div>
      ${franja.observacion ? `<div><strong>Observación:</strong> ${escapeHtml(franja.observacion)}</div>` : ''}
      <div><strong>Periodo:</strong> ${periodoDeFranja(franja)}</div>
      <div><strong>Días justificados:</strong> ${total}</div>
      <div><strong>Registrado por:</strong> ${escapeHtml(franja.creado_por || 'admin')}</div>
    </div>
    ${dias}
  `;
}

function renderTodosLosAjustes(ajustes) {
  const lista = document.getElementById('listaTodosLosAjustes');

  if (ajustes.length === 0) {
    lista.innerHTML = '<p class="muted">Todavía no hay ninguna justificación registrada.</p>';
    return;
  }

  lista.innerHTML = '';
  agruparEnFranjas(ajustes).forEach((franja) => {
    const ids = franja.dias.map((d) => d.id);
    const total = ids.length;

    const contenedor = document.createElement('div');
    contenedor.innerHTML = `
      <div class="doc-item">
        <div>
          <div class="doc-name">${periodoDeFranja(franja)} — ${escapeHtml(franja.trabajadorNombre)}</div>
          <div class="muted">${escapeHtml(franja.motivo)} · ${total} día(s) · registrado por ${escapeHtml(franja.creado_por || 'admin')}</div>
        </div>
        <div class="doc-actions">
          <button type="button" class="btn secondary" data-ver-detalle></button>
          <button type="button" class="btn danger" data-eliminar-franja>Eliminar</button>
        </div>
      </div>
      <div class="ajuste-detalle">${detalleDeFranja(franja)}</div>
    `;

    const detalle = contenedor.querySelector('.ajuste-detalle');
    const botonDetalle = contenedor.querySelector('[data-ver-detalle]');

    const mostrarDetalle = (abierto) => {
      detalle.style.display = abierto ? 'block' : 'none';
      botonDetalle.textContent = abierto ? 'Ocultar detalle' : 'Ver detalle';
    };
    mostrarDetalle(ids.some((id) => ajustesAbiertos.has(id)));

    botonDetalle.addEventListener('click', () => {
      const abrir = detalle.style.display === 'none';
      ids.forEach((id) => (abrir ? ajustesAbiertos.add(id) : ajustesAbiertos.delete(id)));
      mostrarDetalle(abrir);
    });

    contenedor.querySelector('[data-eliminar-franja]').addEventListener('click', () => {
      const mensaje = total > 1
        ? `¿Eliminar la justificación completa (${total} días)?`
        : '¿Eliminar esta justificación?';
      eliminarAjustes(ids, mensaje);
    });

    contenedor.querySelectorAll('[data-eliminar-dia]').forEach((boton) => {
      boton.addEventListener('click', () => {
        eliminarAjustes([Number(boton.dataset.eliminarDia)], '¿Eliminar la justificación de este día?');
      });
    });

    lista.appendChild(contenedor);
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---------- Configuracion del panel de asistencia ----------

async function cargarConfigAsistencia() {
  try {
    const res = await fetch('/api/asistencia/config');
    const data = await res.json();
    document.getElementById('configHoraEntrada').value = data.horaEntrada;
    document.getElementById('configUmbral').value = data.umbralSemanal;
  } catch (err) {
    // los campos quedan vacios y el formulario exige completarlos
  }
}

document.getElementById('configForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const successMsg = document.getElementById('configSuccessMsg');
  const errorMsg = document.getElementById('configErrorMsg');
  successMsg.style.display = 'none';
  errorMsg.style.display = 'none';

  try {
    const res = await fetch('/api/asistencia/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        horaEntrada: document.getElementById('configHoraEntrada').value.trim(),
        umbralSemanal: document.getElementById('configUmbral').value.trim()
      })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo guardar la configuración';
      errorMsg.style.display = 'block';
      return;
    }

    successMsg.textContent = 'Configuración guardada.';
    successMsg.style.display = 'block';
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

// ---------- Tipos de justificacion (nombre, color y si cuenta como falta) ----------

function mostrarErrorTipos(mensaje) {
  const errorMsg = document.getElementById('tiposErrorMsg');
  errorMsg.textContent = mensaje || '';
  errorMsg.style.display = mensaje ? 'block' : 'none';
}

async function enviarTipo(url, method, cuerpo) {
  mostrarErrorTipos('');
  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: cuerpo ? JSON.stringify(cuerpo) : undefined
    });
    const data = await res.json();

    if (!res.ok) {
      mostrarErrorTipos(data.error || 'No se pudo guardar el tipo');
      return false;
    }

    await Promise.all([cargarTipos(), cargarMotivos()]);
    return true;
  } catch (err) {
    mostrarErrorTipos('Error de conexión con el servidor');
    return false;
  }
}

async function cargarTipos() {
  const lista = document.getElementById('tiposLista');
  try {
    const res = await fetch('/api/motivos-justificacion');
    const data = await res.json();
    renderTipos(data.motivos || []);
  } catch (err) {
    lista.innerHTML = '<p class="muted">Error al cargar</p>';
  }
}

function renderTipos(tipos) {
  const lista = document.getElementById('tiposLista');
  lista.innerHTML = '';

  tipos.forEach((tipo) => {
    const fila = document.createElement('div');
    fila.className = 'tipo-fila';
    fila.innerHTML = `
      <input type="color" data-color value="${escapeHtml(tipo.color)}" aria-label="Color">
      <input type="text" data-nombre value="${escapeHtml(tipo.nombre).replace(/"/g, '&quot;')}" aria-label="Nombre">
      <label class="check-linea"><input type="checkbox" data-falta ${tipo.esFalta ? 'checked' : ''}> Cuenta como falta</label>
      <button type="button" class="btn secondary sm" data-guardar>Guardar</button>
      <button type="button" class="btn danger sm" data-eliminar>Eliminar</button>
    `;

    fila.querySelector('[data-guardar]').addEventListener('click', () => {
      enviarTipo(`/api/motivos-justificacion/${tipo.id}`, 'PUT', {
        nombre: fila.querySelector('[data-nombre]').value.trim(),
        color: fila.querySelector('[data-color]').value,
        esFalta: fila.querySelector('[data-falta]').checked
      });
    });

    fila.querySelector('[data-eliminar]').addEventListener('click', () => {
      if (confirm(`¿Eliminar el tipo "${tipo.nombre}"?`)) {
        enviarTipo(`/api/motivos-justificacion/${tipo.id}`, 'DELETE');
      }
    });

    lista.appendChild(fila);
  });
}

document.getElementById('nuevoTipoForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const guardado = await enviarTipo('/api/motivos-justificacion', 'POST', {
    nombre: document.getElementById('nuevoTipoNombre').value.trim(),
    color: document.getElementById('nuevoTipoColor').value,
    esFalta: document.getElementById('nuevoTipoFalta').checked
  });

  if (guardado) e.target.reset();
});

cargarFeriados();
cargarTodosLosAjustes();
cargarConfigAsistencia();
cargarTipos();
