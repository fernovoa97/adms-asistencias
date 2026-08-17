async function cargarDetalle() {
  const tabla = document.getElementById('tablaLicenciasDetalle');
  try {
    const res = await fetch(`/api/licencias/${TRABAJADOR_ID}`);
    const data = await res.json();
    renderLicencias(data.licencias || []);
  } catch (err) {
    tabla.innerHTML = '<tr><td colspan="7" class="empty-state">Error al cargar</td></tr>';
  }
}

function renderLicencias(licencias) {
  const tabla = document.getElementById('tablaLicenciasDetalle');

  if (licencias.length === 0) {
    tabla.innerHTML = '<tr><td colspan="7" class="empty-state">Todavía no se registró ninguna licencia.</td></tr>';
    return;
  }

  tabla.innerHTML = '';
  licencias.forEach((l) => {
    const archivos = l.archivos || [];
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
      <td>${l.fecha}</td>
      <td>${l.horaInicio}</td>
      <td>${l.horaFin}</td>
      <td>${l.horas} h</td>
      <td>${l.motivo ? escapeHtml(l.motivo) : '<span class="muted">—</span>'}</td>
      <td>
        <div class="archivos-lista" style="margin-bottom:6px;">${archivosHtml}</div>
        <label class="btn secondary" style="cursor:pointer;font-size:0.78rem;padding:5px 8px;display:inline-block;">
          + Adjuntar PDF
          <input type="file" accept="application/pdf" class="input-archivo-licencia" style="display:none;">
        </label>
      </td>
      <td><button type="button" class="btn danger" style="font-size:0.78rem;padding:5px 8px;" data-id="${l.id}">Quitar</button></td>
    `;
    fila.querySelector('[data-id]').addEventListener('click', () => eliminarLicencia(l.id));
    fila.querySelector('.input-archivo-licencia').addEventListener('change', (e) => subirArchivoLicencia(l.id, e.target));
    fila.querySelectorAll('[data-ver]').forEach((boton) => {
      boton.addEventListener('click', () => togglePreview(boton.dataset.ver));
    });
    fila.querySelectorAll('[data-quitar]').forEach((boton) => {
      boton.addEventListener('click', () => eliminarArchivoLicencia(boton.dataset.quitar));
    });
    tabla.appendChild(fila);
  });
}

document.getElementById('agregarLicenciaBtn').addEventListener('click', async () => {
  const errorMsg = document.getElementById('errorLicencia');
  errorMsg.style.display = 'none';

  const fecha = document.getElementById('fechaLicencia').value;
  const horaInicio = document.getElementById('horaInicioLicencia').value;
  const horaFin = document.getElementById('horaFinLicencia').value;
  const motivo = document.getElementById('motivoLicencia').value.trim();

  if (!fecha || !horaInicio || !horaFin) {
    errorMsg.textContent = 'La fecha, hora de inicio y hora de fin son obligatorias.';
    errorMsg.style.display = 'block';
    return;
  }

  try {
    const res = await fetch(`/api/licencias/${TRABAJADOR_ID}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fecha, horaInicio, horaFin, motivo })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo guardar la licencia';
      errorMsg.style.display = 'block';
      return;
    }

    document.getElementById('fechaLicencia').value = '';
    document.getElementById('horaInicioLicencia').value = '';
    document.getElementById('horaFinLicencia').value = '';
    document.getElementById('motivoLicencia').value = '';
    cargarDetalle();
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

async function eliminarLicencia(id) {
  if (!confirm('¿Quitar esta licencia?')) return;
  try {
    const res = await fetch(`/api/licencias/registro/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo quitar el registro');
      return;
    }
    cargarDetalle();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

async function subirArchivoLicencia(licenciaId, inputEl) {
  const archivo = inputEl.files[0];
  if (!archivo) return;

  const formData = new FormData();
  formData.append('archivo', archivo);

  try {
    const res = await fetch(`/api/licencias/registro/${licenciaId}/archivos`, { method: 'POST', body: formData });
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

async function eliminarArchivoLicencia(archivoId) {
  if (!confirm('¿Quitar este documento?')) return;
  try {
    const res = await fetch(`/api/licencias/archivos/${archivoId}`, { method: 'DELETE' });
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
  div.innerHTML = `<iframe src="/documentos-licencias/${archivoId}"></iframe>`;
  area.appendChild(div);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarDetalle();
