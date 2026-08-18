async function cargarDetalle() {
  const tabla = document.getElementById('tablaPeriodos');
  try {
    const res = await fetch(`/api/descansos-medicos/${TRABAJADOR_ID}`);
    const data = await res.json();
    renderPeriodos(data.periodos || []);
  } catch (err) {
    tabla.innerHTML = '<tr><td colspan="6" class="empty-state">Error al cargar</td></tr>';
  }
}

function renderPeriodos(periodos) {
  const tabla = document.getElementById('tablaPeriodos');

  if (periodos.length === 0) {
    tabla.innerHTML = '<tr><td colspan="6" class="empty-state">Todavía no se registró ningún periodo.</td></tr>';
    return;
  }

  tabla.innerHTML = '';
  periodos.forEach((p) => {
    const archivos = p.archivos || [];
    const archivosHtml = archivos.length === 0
      ? '<span class="muted" style="font-size:0.8rem;">Sin documentos</span>'
      : archivos.map((a) => `
          <div class="archivo-item" data-archivo-id="${a.id}">
            <span title="${escapeHtml(a.nombre)}">${escapeHtml(a.nombre)}</span>
            <span style="display:flex;gap:4px;">
              <button type="button" class="archivo-ver" data-ver="${a.id}" title="Vista previa">👁</button>
              <button type="button" class="archivo-quitar" data-quitar="${a.id}" title="Quitar documento">×</button>
            </span>
          </div>
        `).join('');

    const fila = document.createElement('tr');
    fila.innerHTML = `
      <td>${p.fechaInicio}</td>
      <td>${p.fechaFin}</td>
      <td>${p.dias}</td>
      <td>${p.observacion ? escapeHtml(p.observacion) : '<span class="muted">—</span>'}</td>
      <td>
        <div class="archivos-lista" style="margin-bottom:6px;">${archivosHtml}</div>
        <label class="btn secondary" style="cursor:pointer;font-size:0.78rem;padding:5px 8px;display:inline-block;">
          + Adjuntar PDF
          <input type="file" accept="application/pdf" class="input-archivo-periodo" style="display:none;">
        </label>
      </td>
      <td><button type="button" class="btn danger" style="font-size:0.78rem;padding:5px 8px;" data-id="${p.id}">Quitar periodo</button></td>
    `;
    fila.querySelector('[data-id]').addEventListener('click', () => eliminarPeriodo(p.id));
    fila.querySelector('.input-archivo-periodo').addEventListener('change', (e) => subirArchivoPeriodo(p.id, e.target));
    fila.querySelectorAll('[data-ver]').forEach((boton) => {
      boton.addEventListener('click', () => togglePreview(boton.dataset.ver));
    });
    fila.querySelectorAll('[data-quitar]').forEach((boton) => {
      boton.addEventListener('click', () => eliminarArchivoPeriodo(boton.dataset.quitar));
    });
    tabla.appendChild(fila);
  });
}

async function subirArchivoPeriodo(periodoId, inputEl) {
  const archivo = inputEl.files[0];
  if (!archivo) return;

  const formData = new FormData();
  formData.append('archivo', archivo);

  try {
    const res = await fetch(`/api/descansos-medicos/periodos/${periodoId}/archivos`, { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || 'No se pudo subir el archivo');
      return;
    }
    cargarDetalle();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

async function eliminarArchivoPeriodo(archivoId) {
  if (!confirm('¿Quitar este documento?')) return;
  try {
    const res = await fetch(`/api/descansos-medicos/archivos/${archivoId}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo quitar el archivo');
      return;
    }
    cargarDetalle();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

function togglePreview(archivoId) {
  const area = document.getElementById('pdfPreviewArea');
  const existingId = `pdf_prev_${archivoId}`;
  const existente = document.getElementById(existingId);
  if (existente) {
    existente.remove();
    return;
  }
  area.innerHTML = '';
  const div = document.createElement('div');
  div.className = 'pdf-preview-wrap';
  div.id = existingId;
  div.innerHTML = `<iframe src="/documentos-descansos-medicos/${archivoId}"></iframe>`;
  area.appendChild(div);
}

document.getElementById('agregarPeriodoBtn').addEventListener('click', async () => {
  const errorMsg = document.getElementById('errorPeriodo');
  errorMsg.style.display = 'none';

  const fechaInicio = document.getElementById('fechaInicio').value;
  const fechaFin = document.getElementById('fechaFin').value;
  const observacion = document.getElementById('observacionPeriodo').value.trim();

  if (!fechaInicio || !fechaFin) {
    errorMsg.textContent = 'La fecha de inicio y de fin son obligatorias.';
    errorMsg.style.display = 'block';
    return;
  }

  try {
    const res = await fetch(`/api/descansos-medicos/${TRABAJADOR_ID}/periodos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fechaInicio, fechaFin, observacion })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo guardar el periodo';
      errorMsg.style.display = 'block';
      return;
    }

    document.getElementById('fechaInicio').value = '';
    document.getElementById('fechaFin').value = '';
    document.getElementById('observacionPeriodo').value = '';
    cargarDetalle();
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

async function eliminarPeriodo(id) {
  if (!confirm('¿Quitar este periodo de descanso médico?')) return;
  try {
    const res = await fetch(`/api/descansos-medicos/periodos/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo quitar el periodo');
      return;
    }
    cargarDetalle();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarDetalle();
