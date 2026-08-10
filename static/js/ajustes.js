// ---------- Justificar un día ----------

const searchWorkerInput = document.getElementById('searchWorkerInput');
const workerResults = document.getElementById('workerResults');
const workerAjustesArea = document.getElementById('workerAjustesArea');

let debounceTimerAjustes = null;
let trabajadorSeleccionado = null;

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
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `
      <div>
        <div class="name">${escapeHtml(w.nombres)} ${escapeHtml(w.apellidos)}</div>
        <div class="meta">DNI: ${escapeHtml(w.dni || '—')} ${w.codigo_empleado ? '· Código: ' + escapeHtml(w.codigo_empleado) : ''}</div>
      </div>
      <span class="tag">Seleccionar</span>
    `;
    item.addEventListener('click', () => seleccionarTrabajador(w));
    workerResults.appendChild(item);
  });
}

function seleccionarTrabajador(w) {
  trabajadorSeleccionado = w;
  workerResults.innerHTML = '';
  searchWorkerInput.value = '';
  renderFormularioAjuste(w);
  cargarAjustesDeTrabajador(w.id);
}

function renderFormularioAjuste(w) {
  workerAjustesArea.innerHTML = `
    <div class="panel" style="background:#f5faf7;margin-top:16px;">
      <h3 style="margin-top:0;font-size:0.95rem;">
        Justificando a: ${escapeHtml(w.nombres)} ${escapeHtml(w.apellidos)}
      </h3>
      <div class="success-msg" id="ajusteSuccessMsg"></div>
      <div class="error-msg" id="ajusteErrorMsg"></div>
      <form id="ajusteForm" class="grid-2" style="align-items:end;">
        <div class="field">
          <label for="fechaAjuste">Fecha</label>
          <input type="date" id="fechaAjuste" required>
        </div>
        <div class="field">
          <label for="motivoAjuste">Motivo</label>
          <input type="text" id="motivoAjuste" placeholder="Ej. Cita médica" required>
        </div>
        <div class="field" style="grid-column: span 2;">
          <button type="submit" class="btn" id="ajusteSubmitBtn">Guardar justificación</button>
        </div>
      </form>
      <h4 style="font-size:0.85rem;margin-bottom:8px;">Justificaciones ya guardadas</h4>
      <div id="listaAjustesTrabajador" class="doc-list"></div>
    </div>
  `;

  document.getElementById('ajusteForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const successMsg = document.getElementById('ajusteSuccessMsg');
    const errorMsg = document.getElementById('ajusteErrorMsg');
    successMsg.style.display = 'none';
    errorMsg.style.display = 'none';

    const fecha = document.getElementById('fechaAjuste').value;
    const motivo = document.getElementById('motivoAjuste').value.trim();

    if (!fecha || !motivo) {
      errorMsg.textContent = 'La fecha y el motivo son obligatorios';
      errorMsg.style.display = 'block';
      return;
    }

    const btn = document.getElementById('ajusteSubmitBtn');
    btn.disabled = true;
    btn.textContent = 'Guardando...';

    try {
      const res = await fetch('/api/ajustes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trabajadorId: w.id, fecha, motivo })
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo guardar la justificación';
        errorMsg.style.display = 'block';
        return;
      }

      successMsg.textContent = 'Justificación guardada.';
      successMsg.style.display = 'block';
      document.getElementById('ajusteForm').reset();
      cargarAjustesDeTrabajador(w.id);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Guardar justificación';
    }
  });
}

async function cargarAjustesDeTrabajador(trabajadorId) {
  const lista = document.getElementById('listaAjustesTrabajador');
  if (!lista) return;

  try {
    const res = await fetch(`/api/ajustes/trabajador/${trabajadorId}`);
    const data = await res.json();
    renderListaAjustes(data.ajustes || [], trabajadorId);
  } catch (err) {
    lista.innerHTML = '<p class="muted">Error al cargar</p>';
  }
}

function renderListaAjustes(ajustes, trabajadorId) {
  const lista = document.getElementById('listaAjustesTrabajador');
  if (!lista) return;

  if (ajustes.length === 0) {
    lista.innerHTML = '<p class="muted">Sin justificaciones registradas.</p>';
    return;
  }

  lista.innerHTML = ajustes
    .map((a) => `
      <div class="doc-item">
        <div>
          <div class="doc-name">${a.fecha} — ${escapeHtml(a.motivo)}</div>
          <div class="muted" style="font-size:0.75rem;">Registrado por ${escapeHtml(a.creado_por || 'admin')}</div>
        </div>
        <div class="doc-actions">
          <button class="btn danger" onclick="eliminarAjuste(${a.id}, ${trabajadorId})">Eliminar</button>
        </div>
      </div>
    `)
    .join('');
}

async function eliminarAjuste(ajusteId, trabajadorId) {
  if (!confirm('¿Eliminar esta justificación?')) return;

  try {
    const res = await fetch(`/api/ajustes/${ajusteId}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo eliminar');
      return;
    }
    cargarAjustesDeTrabajador(trabajadorId);
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

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarFeriados();
