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
    seleccionadosArea.innerHTML = '<p class="muted" style="font-size:0.85rem;">Todavía no agregaste a ningún trabajador.</p>';
    return;
  }

  seleccionadosArea.innerHTML = `
    <p class="muted" style="font-size:0.8rem;margin-bottom:6px;">${trabajadoresSeleccionados.length} trabajador(es) seleccionado(s):</p>
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
        fechaInicio, fechaFin, motivo
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
      overlay.style.display = 'none';
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    }
  });
}

async function eliminarAjuste(ajusteId) {
  if (!confirm('¿Eliminar esta justificación?')) return;

  try {
    const res = await fetch(`/api/ajustes/${ajusteId}`, { method: 'DELETE' });
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

function renderTodosLosAjustes(ajustes) {
  const lista = document.getElementById('listaTodosLosAjustes');

  if (ajustes.length === 0) {
    lista.innerHTML = '<p class="muted">Todavía no hay ninguna justificación registrada.</p>';
    return;
  }

  lista.innerHTML = ajustes
    .map((a) => `
      <div class="doc-item">
        <div>
          <div class="doc-name">${a.fecha} — ${escapeHtml(a.trabajadorNombre)}</div>
          <div class="muted" style="font-size:0.78rem;">${escapeHtml(a.motivo)} · registrado por ${escapeHtml(a.creado_por || 'admin')}</div>
        </div>
        <div class="doc-actions">
          <button class="btn danger" onclick="eliminarAjuste(${a.id})">Eliminar</button>
        </div>
      </div>
    `)
    .join('');
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarFeriados();
cargarTodosLosAjustes();
