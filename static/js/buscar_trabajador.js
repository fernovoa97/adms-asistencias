const searchInput = document.getElementById('searchInput');
const resultList = document.getElementById('resultList');
const workerDetail = document.getElementById('workerDetail');

let debounceTimer = null;
let uploadRowCount = 0;

searchInput.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  const q = searchInput.value.trim();

  if (!q) {
    resultList.innerHTML = '';
    return;
  }

  debounceTimer = setTimeout(() => doSearch(q), 180);
});

async function doSearch(q) {
  try {
    const res = await fetch(`/api/trabajadores/buscar?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderResults(data.results || []);
  } catch (err) {
    resultList.innerHTML = '<div class="empty-state">Error al buscar</div>';
  }
}

function renderResults(results) {
  if (results.length === 0) {
    resultList.innerHTML = '<div class="empty-state">No se encontraron trabajadores</div>';
    return;
  }

  resultList.innerHTML = '';
  results.forEach((w) => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `
      <div>
        <div class="name">${escapeHtml(w.nombres)} ${escapeHtml(w.apellidos)}</div>
        <div class="meta">DNI: ${escapeHtml(w.dni || '—')} ${w.cargo ? '· ' + escapeHtml(w.cargo) : ''}</div>
      </div>
      <span class="tag">${w.area ? escapeHtml(w.area) : 'Ver detalle'}</span>
    `;
    item.addEventListener('click', () => loadDetail(w.id));
    resultList.appendChild(item);
  });
}

async function loadDetail(id) {
  try {
    const res = await fetch(`/api/trabajadores/${id}`);
    const data = await res.json();
    if (!res.ok) return;
    renderDetail(data.worker, 'view');
    workerDetail.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    // noop
  }
}

function renderDetail(w, mode) {
  if (mode === 'edit') {
    renderEditForm(w);
  } else {
    renderViewMode(w);
  }
}

function renderViewMode(w) {
  const fields = [
    ['Nombres', w.nombres],
    ['Apellidos', w.apellidos],
    ['DNI', w.dni || '—'],
    ['Código de empleado', w.codigo_empleado || '— (no enrolado en el biométrico)'],
    ['Cargo', w.cargo || '—'],
    ['Área', w.area || '—'],
    ['Teléfono', w.telefono || '—'],
    ['Correo', w.email || '—'],
    ['Fecha de ingreso', w.fecha_ingreso || '—'],
    ['Horario', (w.hora_entrada || '08:00') + ' a ' + (w.hora_salida || '17:00') + (w.hora_entrada ? ' (personalizado)' : ' (estándar)')],
    ['Fecha de fin de contrato', w.fecha_fin_contrato || '—'],
    ['Última renovación', w.fecha_renovacion || '—'],
    ['Dirección', w.direccion || '—']
  ];

  const fieldsHtml = fields
    .map(([label, value]) => `
      <div class="detail-item">
        <div class="label">${label}</div>
        <div class="value">${escapeHtml(String(value))}</div>
      </div>`)
    .join('');

  const docsHtml =
    (w.documentos || []).length === 0
      ? '<p class="muted">Este trabajador no tiene documentos cargados.</p>'
      : `<div class="doc-list">${w.documentos
          .map((d) => `
        <div class="doc-item">
          <div class="doc-name">${escapeHtml(d.nombre)}</div>
          <div class="doc-actions">
            <button class="btn secondary" onclick="togglePdfPreview(${d.id}, '/documentos/${d.id}')">Vista previa</button>
            <a class="btn secondary" href="/documentos/${d.id}" target="_blank">Abrir</a>
            <button class="btn danger" onclick="eliminarDocumento(${w.id}, ${d.id})">Eliminar</button>
          </div>
        </div>`)
          .join('')}</div>`;

  workerDetail.innerHTML = `
    <div class="panel">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
        <h2 style="margin-top:0;font-size:1.1rem;">${escapeHtml(w.nombres)} ${escapeHtml(w.apellidos)}</h2>
        <button class="btn secondary" id="editWorkerBtn">Editar información</button>
      </div>
      <div class="detail-grid">${fieldsHtml}</div>
      ${w.observaciones ? `<div class="detail-item" style="margin-bottom:16px;"><div class="label">Observaciones</div><div class="value">${escapeHtml(w.observaciones)}</div></div>` : ''}

      <h3 style="font-size:0.95rem;">Documentos</h3>
      ${docsHtml}
      <div id="pdfPreviewArea"></div>

      <h3 style="font-size:0.95rem;margin-top:20px;">Agregar más documentos</h3>
      <div id="uploadRows"></div>
      <button type="button" class="btn secondary" id="addUploadRowBtn">+ Agregar documento PDF</button>
      <div style="margin-top:12px;">
        <button type="button" class="btn" id="subirDocsBtn">Subir documentos</button>
      </div>
      <div class="error-msg" id="uploadErrorMsg"></div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0;font-size:0.95rem;">Actualizar contrato</h3>
      <p class="muted">Registra la nueva fecha de fin de contrato (por ejemplo, tras una renovación).</p>
      <div class="success-msg" id="contratoSuccessMsg"></div>
      <div class="error-msg" id="contratoErrorMsg"></div>
      <form id="contratoForm">
        <div class="grid-2">
          <div class="field">
            <label for="nuevaFechaFinContrato">Nueva fecha de fin de contrato *</label>
            <input type="date" id="nuevaFechaFinContrato" required>
          </div>
          <div class="field">
            <label for="nuevaFechaRenovacion">Fecha de renovación</label>
            <input type="date" id="nuevaFechaRenovacion">
          </div>
        </div>
        <button type="submit" class="btn" id="contratoSubmitBtn">Guardar nueva fecha</button>
      </form>
    </div>
  `;

  document.getElementById('editWorkerBtn').addEventListener('click', () => renderEditForm(w));
  bindContratoForm(w.id);
  bindUploadDocs(w.id);
}

function renderEditForm(w) {
  workerDetail.innerHTML = `
    <div class="panel">
      <h2 style="margin-top:0;font-size:1.1rem;">Editar información</h2>
      <div class="error-msg" id="editErrorMsg"></div>
      <form id="editForm">
        <div class="grid-2">
          <div class="field">
            <label for="editNombres">Nombres *</label>
            <input type="text" id="editNombres" value="${escapeAttr(w.nombres)}" required>
          </div>
          <div class="field">
            <label for="editApellidos">Apellidos *</label>
            <input type="text" id="editApellidos" value="${escapeAttr(w.apellidos)}" required>
          </div>
          <div class="field">
            <label for="editDni">DNI *</label>
            <input type="text" id="editDni" value="${escapeAttr(w.dni || '')}" required>
          </div>
          <div class="field">
            <label for="editTelefono">Teléfono</label>
            <input type="text" id="editTelefono" value="${escapeAttr(w.telefono || '')}">
          </div>
          <div class="field">
            <label for="editEmail">Correo electrónico</label>
            <input type="email" id="editEmail" value="${escapeAttr(w.email || '')}">
          </div>
          <div class="field">
            <label for="editFechaIngreso">Fecha de ingreso</label>
            <input type="date" id="editFechaIngreso" value="${w.fecha_ingreso || ''}">
          </div>
          <div class="field">
            <label for="editHoraEntrada">Hora de entrada (dejar vacío = 08:00 estándar)</label>
            <input type="time" id="editHoraEntrada" value="${w.hora_entrada || ''}">
          </div>
          <div class="field">
            <label for="editHoraSalida">Hora de salida (dejar vacío = 17:00 estándar)</label>
            <input type="time" id="editHoraSalida" value="${w.hora_salida || ''}">
          </div>
          <div class="field">
            <label for="editCargo">Cargo</label>
            <input type="text" id="editCargo" value="${escapeAttr(w.cargo || '')}">
          </div>
          <div class="field">
            <label for="editArea">Área / Departamento</label>
            <input type="text" id="editArea" value="${escapeAttr(w.area || '')}">
          </div>
        </div>
        <div class="field">
          <label for="editDireccion">Dirección</label>
          <input type="text" id="editDireccion" value="${escapeAttr(w.direccion || '')}">
        </div>
        <div class="field">
          <label for="editObservaciones">Observaciones</label>
          <textarea id="editObservaciones" rows="3">${escapeHtml(w.observaciones || '')}</textarea>
        </div>
        <div style="display:flex;gap:10px;">
          <button type="submit" class="btn" id="editSubmitBtn">Guardar cambios</button>
          <button type="button" class="btn secondary" id="editCancelBtn">Cancelar</button>
        </div>
      </form>
    </div>
  `;

  document.getElementById('editCancelBtn').addEventListener('click', () => renderViewMode(w));

  document.getElementById('editForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorMsg = document.getElementById('editErrorMsg');
    errorMsg.style.display = 'none';

    const payload = {
      nombres: document.getElementById('editNombres').value.trim(),
      apellidos: document.getElementById('editApellidos').value.trim(),
      dni: document.getElementById('editDni').value.trim(),
      telefono: document.getElementById('editTelefono').value.trim(),
      email: document.getElementById('editEmail').value.trim(),
      fechaIngreso: document.getElementById('editFechaIngreso').value,
      horaEntrada: document.getElementById('editHoraEntrada').value,
      horaSalida: document.getElementById('editHoraSalida').value,
      cargo: document.getElementById('editCargo').value.trim(),
      area: document.getElementById('editArea').value.trim(),
      direccion: document.getElementById('editDireccion').value.trim(),
      observaciones: document.getElementById('editObservaciones').value.trim()
    };

    const submitBtn = document.getElementById('editSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Guardando...';

    try {
      const res = await fetch(`/api/trabajadores/${w.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo actualizar el trabajador';
        errorMsg.style.display = 'block';
        return;
      }

      renderViewMode(data.worker);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Guardar cambios';
    }
  });
}

function bindContratoForm(workerId) {
  const form = document.getElementById('contratoForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const successMsg = document.getElementById('contratoSuccessMsg');
    const errorMsg = document.getElementById('contratoErrorMsg');
    successMsg.style.display = 'none';
    errorMsg.style.display = 'none';

    const fechaFinContrato = document.getElementById('nuevaFechaFinContrato').value;
    const fechaRenovacion = document.getElementById('nuevaFechaRenovacion').value;

    if (!fechaFinContrato) {
      errorMsg.textContent = 'La nueva fecha de fin de contrato es obligatoria';
      errorMsg.style.display = 'block';
      return;
    }

    const submitBtn = document.getElementById('contratoSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Guardando...';

    try {
      const res = await fetch(`/api/trabajadores/${workerId}/contrato`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fechaFinContrato, fechaRenovacion })
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo actualizar el contrato';
        errorMsg.style.display = 'block';
        return;
      }

      renderViewMode(data.worker);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Guardar nueva fecha';
    }
  });
}

function bindUploadDocs(workerId) {
  const addBtn = document.getElementById('addUploadRowBtn');
  const uploadRows = document.getElementById('uploadRows');
  if (!addBtn || !uploadRows) return;

  uploadRows.innerHTML = '';
  addUploadRow();

  addBtn.addEventListener('click', addUploadRow);

  document.getElementById('subirDocsBtn').addEventListener('click', async () => {
    const errorMsg = document.getElementById('uploadErrorMsg');
    errorMsg.style.display = 'none';

    const rows = document.querySelectorAll('#uploadRows .upload-row');
    const formData = new FormData();
    const nombres = [];
    let hayArchivos = false;

    rows.forEach((row) => {
      const fileInput = row.querySelector('.doc-file-input');
      const labelInput = row.querySelector('.doc-label-input');
      const file = fileInput.files[0];
      if (file) {
        formData.append('documentos', file);
        nombres.push(labelInput.value.trim() || file.name);
        hayArchivos = true;
      }
    });
    formData.append('documentosNombres', JSON.stringify(nombres));

    if (!hayArchivos) {
      errorMsg.textContent = 'Elige al menos un archivo PDF';
      errorMsg.style.display = 'block';
      return;
    }

    const btn = document.getElementById('subirDocsBtn');
    btn.disabled = true;
    btn.textContent = 'Subiendo...';

    try {
      const res = await fetch(`/api/trabajadores/${workerId}/documentos`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudieron subir los documentos';
        errorMsg.style.display = 'block';
        return;
      }

      renderViewMode(data.worker);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Subir documentos';
    }
  });
}

function addUploadRow() {
  uploadRowCount += 1;
  const rowId = `uprow_${uploadRowCount}`;

  const wrapper = document.createElement('div');
  wrapper.className = 'upload-row';
  wrapper.dataset.rowId = rowId;

  wrapper.innerHTML = `
    <input type="text" placeholder="Nombre del documento (ej. DNI, Contrato)" class="doc-label-input">
    <label class="btn secondary" style="cursor:pointer;">
      Elegir PDF
      <input type="file" accept="application/pdf" class="doc-file-input" style="display:none;">
    </label>
    <span class="file-name">Ningún archivo seleccionado</span>
    <button type="button" class="btn danger remove-row-btn">Quitar</button>
  `;

  const fileInput = wrapper.querySelector('.doc-file-input');
  const fileNameSpan = wrapper.querySelector('.file-name');
  const labelInput = wrapper.querySelector('.doc-label-input');
  const removeBtn = wrapper.querySelector('.remove-row-btn');

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    fileNameSpan.textContent = file ? file.name : 'Ningún archivo seleccionado';
    if (file && !labelInput.value.trim()) {
      labelInput.value = file.name.replace(/\.pdf$/i, '');
    }
  });

  removeBtn.addEventListener('click', () => wrapper.remove());

  document.getElementById('uploadRows').appendChild(wrapper);
}

async function eliminarDocumento(workerId, docId) {
  if (!confirm('¿Eliminar este documento? Esta acción no se puede deshacer.')) return;

  try {
    const res = await fetch(`/api/trabajadores/${workerId}/documentos/${docId}`, {
      method: 'DELETE'
    });
    if (!res.ok) {
      alert('No se pudo eliminar el documento');
      return;
    }
    loadDetail(workerId);
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

function togglePdfPreview(docId, url) {
  const area = document.getElementById('pdfPreviewArea');
  const existingId = `pdf_prev_${docId}`;
  const existing = document.getElementById(existingId);
  if (existing) {
    existing.remove();
    return;
  }
  area.innerHTML = '';
  const div = document.createElement('div');
  div.className = 'pdf-preview-wrap';
  div.id = existingId;
  div.innerHTML = `<iframe src="${url}"></iframe>`;
  area.appendChild(div);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, '&quot;');
}const searchInput = document.getElementById('searchInput');
const resultList = document.getElementById('resultList');
const workerDetail = document.getElementById('workerDetail');

let debounceTimer = null;
let uploadRowCount = 0;

searchInput.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  const q = searchInput.value.trim();

  if (!q) {
    resultList.innerHTML = '';
    return;
  }

  debounceTimer = setTimeout(() => doSearch(q), 180);
});

async function doSearch(q) {
  try {
    const res = await fetch(`/api/trabajadores/buscar?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderResults(data.results || []);
  } catch (err) {
    resultList.innerHTML = '<div class="empty-state">Error al buscar</div>';
  }
}

function renderResults(results) {
  if (results.length === 0) {
    resultList.innerHTML = '<div class="empty-state">No se encontraron trabajadores</div>';
    return;
  }

  resultList.innerHTML = '';
  results.forEach((w) => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `
      <div>
        <div class="name">${escapeHtml(w.nombres)} ${escapeHtml(w.apellidos)}</div>
        <div class="meta">DNI: ${escapeHtml(w.dni || '—')} ${w.cargo ? '· ' + escapeHtml(w.cargo) : ''}</div>
      </div>
      <span class="tag">${w.area ? escapeHtml(w.area) : 'Ver detalle'}</span>
    `;
    item.addEventListener('click', () => loadDetail(w.id));
    resultList.appendChild(item);
  });
}

async function loadDetail(id) {
  try {
    const res = await fetch(`/api/trabajadores/${id}`);
    const data = await res.json();
    if (!res.ok) return;
    renderDetail(data.worker, 'view');
    workerDetail.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    // noop
  }
}

function renderDetail(w, mode) {
  if (mode === 'edit') {
    renderEditForm(w);
  } else {
    renderViewMode(w);
  }
}

function renderViewMode(w) {
  const fields = [
    ['Nombres', w.nombres],
    ['Apellidos', w.apellidos],
    ['DNI', w.dni || '—'],
    ['Código de empleado', w.codigo_empleado || '— (no enrolado en el biométrico)'],
    ['Cargo', w.cargo || '—'],
    ['Área', w.area || '—'],
    ['Teléfono', w.telefono || '—'],
    ['Correo', w.email || '—'],
    ['Fecha de ingreso', w.fecha_ingreso || '—'],
    ['Horario', (w.hora_entrada || '08:00') + ' a ' + (w.hora_salida || '17:00') + (w.hora_entrada ? ' (personalizado)' : ' (estándar)')],
    ['Fecha de fin de contrato', w.fecha_fin_contrato || '—'],
    ['Última renovación', w.fecha_renovacion || '—'],
    ['Dirección', w.direccion || '—']
  ];

  const fieldsHtml = fields
    .map(([label, value]) => `
      <div class="detail-item">
        <div class="label">${label}</div>
        <div class="value">${escapeHtml(String(value))}</div>
      </div>`)
    .join('');

  const carpetas = w.carpetas || [];
  const documentos = w.documentos || [];

  // Agrupamos los documentos por carpeta (los que no tienen carpeta van al
  // final, bajo "Sin carpeta").
  const grupos = {};
  documentos.forEach((d) => {
    const clave = d.carpeta || 'Sin carpeta';
    if (!grupos[clave]) grupos[clave] = [];
    grupos[clave].push(d);
  });

  const nombresGrupos = Object.keys(grupos).sort((a, b) => {
    if (a === 'Sin carpeta') return 1;
    if (b === 'Sin carpeta') return -1;
    return a.localeCompare(b);
  });

  const docsHtml =
    documentos.length === 0
      ? '<p class="muted">Este trabajador no tiene documentos cargados.</p>'
      : nombresGrupos
          .map((nombreGrupo) => `
        <div class="carpeta-grupo">
          <div class="carpeta-titulo">📁 ${escapeHtml(nombreGrupo)}</div>
          <div class="doc-list">
            ${grupos[nombreGrupo]
              .map((d) => `
              <div class="doc-item">
                <div class="doc-name">${escapeHtml(d.nombre)}</div>
                <div class="doc-actions">
                  <button class="btn secondary" onclick="togglePdfPreview(${d.id}, '/documentos/${d.id}')">Vista previa</button>
                  <a class="btn secondary" href="/documentos/${d.id}" target="_blank">Abrir</a>
                  <button class="btn danger" onclick="eliminarDocumento(${w.id}, ${d.id})">Eliminar</button>
                </div>
              </div>`)
              .join('')}
          </div>
        </div>`)
          .join('');

  const opcionesCarpetas = carpetas
    .map((c) => `<option value="${c.id}">${escapeHtml(c.nombre)}</option>`)
    .join('');

  workerDetail.innerHTML = `
    <div class="panel">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
        <h2 style="margin-top:0;font-size:1.1rem;">${escapeHtml(w.nombres)} ${escapeHtml(w.apellidos)}</h2>
        <button class="btn secondary" id="editWorkerBtn">Editar información</button>
      </div>
      <div class="detail-grid">${fieldsHtml}</div>
      ${w.observaciones ? `<div class="detail-item" style="margin-bottom:16px;"><div class="label">Observaciones</div><div class="value">${escapeHtml(w.observaciones)}</div></div>` : ''}

      <h3 style="font-size:0.95rem;">Documentos</h3>
      ${docsHtml}
      <div id="pdfPreviewArea"></div>

      <h3 style="font-size:0.95rem;margin-top:20px;">Carpetas</h3>
      <p class="muted">Organiza los documentos de este trabajador en carpetas (ej. "DNI", "Contratos", "Certificados").</p>
      <div class="error-msg" id="carpetaErrorMsg"></div>
      <div style="display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap;">
        <input type="text" id="nuevaCarpetaInput" placeholder="Nombre de la nueva carpeta" style="flex:1;min-width:200px;padding:10px 12px;border:1px solid var(--border);border-radius:8px;">
        <button type="button" class="btn secondary" id="crearCarpetaBtn">+ Crear carpeta</button>
      </div>

      <h3 style="font-size:0.95rem;">Agregar más documentos</h3>
      <div id="uploadRows"></div>
      <button type="button" class="btn secondary" id="addUploadRowBtn">+ Agregar documento PDF</button>
      <div style="margin-top:12px;">
        <button type="button" class="btn" id="subirDocsBtn">Subir documentos</button>
      </div>
      <div class="error-msg" id="uploadErrorMsg"></div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0;font-size:0.95rem;">Actualizar contrato</h3>
      <p class="muted">Registra la nueva fecha de fin de contrato (por ejemplo, tras una renovación).</p>
      <div class="success-msg" id="contratoSuccessMsg"></div>
      <div class="error-msg" id="contratoErrorMsg"></div>
      <form id="contratoForm">
        <div class="grid-2">
          <div class="field">
            <label for="nuevaFechaFinContrato">Nueva fecha de fin de contrato *</label>
            <input type="date" id="nuevaFechaFinContrato" required>
          </div>
          <div class="field">
            <label for="nuevaFechaRenovacion">Fecha de renovación</label>
            <input type="date" id="nuevaFechaRenovacion">
          </div>
        </div>
        <button type="submit" class="btn" id="contratoSubmitBtn">Guardar nueva fecha</button>
      </form>
    </div>
  `;

  document.getElementById('editWorkerBtn').addEventListener('click', () => renderEditForm(w));
  bindContratoForm(w.id);
  bindCarpetas(w);
  bindUploadDocs(w);
}

function renderEditForm(w) {
  workerDetail.innerHTML = `
    <div class="panel">
      <h2 style="margin-top:0;font-size:1.1rem;">Editar información</h2>
      <div class="error-msg" id="editErrorMsg"></div>
      <form id="editForm">
        <div class="grid-2">
          <div class="field">
            <label for="editNombres">Nombres *</label>
            <input type="text" id="editNombres" value="${escapeAttr(w.nombres)}" required>
          </div>
          <div class="field">
            <label for="editApellidos">Apellidos *</label>
            <input type="text" id="editApellidos" value="${escapeAttr(w.apellidos)}" required>
          </div>
          <div class="field">
            <label for="editDni">DNI *</label>
            <input type="text" id="editDni" value="${escapeAttr(w.dni || '')}" required>
          </div>
          <div class="field">
            <label for="editTelefono">Teléfono</label>
            <input type="text" id="editTelefono" value="${escapeAttr(w.telefono || '')}">
          </div>
          <div class="field">
            <label for="editEmail">Correo electrónico</label>
            <input type="email" id="editEmail" value="${escapeAttr(w.email || '')}">
          </div>
          <div class="field">
            <label for="editFechaIngreso">Fecha de ingreso</label>
            <input type="date" id="editFechaIngreso" value="${w.fecha_ingreso || ''}">
          </div>
          <div class="field">
            <label for="editHoraEntrada">Hora de entrada (dejar vacío = 08:00 estándar)</label>
            <input type="time" id="editHoraEntrada" value="${w.hora_entrada || ''}">
          </div>
          <div class="field">
            <label for="editHoraSalida">Hora de salida (dejar vacío = 17:00 estándar)</label>
            <input type="time" id="editHoraSalida" value="${w.hora_salida || ''}">
          </div>
          <div class="field">
            <label for="editCargo">Cargo</label>
            <input type="text" id="editCargo" value="${escapeAttr(w.cargo || '')}">
          </div>
          <div class="field">
            <label for="editArea">Área / Departamento</label>
            <input type="text" id="editArea" value="${escapeAttr(w.area || '')}">
          </div>
        </div>
        <div class="field">
          <label for="editDireccion">Dirección</label>
          <input type="text" id="editDireccion" value="${escapeAttr(w.direccion || '')}">
        </div>
        <div class="field">
          <label for="editObservaciones">Observaciones</label>
          <textarea id="editObservaciones" rows="3">${escapeHtml(w.observaciones || '')}</textarea>
        </div>
        <div style="display:flex;gap:10px;">
          <button type="submit" class="btn" id="editSubmitBtn">Guardar cambios</button>
          <button type="button" class="btn secondary" id="editCancelBtn">Cancelar</button>
        </div>
      </form>
    </div>
  `;

  document.getElementById('editCancelBtn').addEventListener('click', () => renderViewMode(w));

  document.getElementById('editForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorMsg = document.getElementById('editErrorMsg');
    errorMsg.style.display = 'none';

    const payload = {
      nombres: document.getElementById('editNombres').value.trim(),
      apellidos: document.getElementById('editApellidos').value.trim(),
      dni: document.getElementById('editDni').value.trim(),
      telefono: document.getElementById('editTelefono').value.trim(),
      email: document.getElementById('editEmail').value.trim(),
      fechaIngreso: document.getElementById('editFechaIngreso').value,
      horaEntrada: document.getElementById('editHoraEntrada').value,
      horaSalida: document.getElementById('editHoraSalida').value,
      cargo: document.getElementById('editCargo').value.trim(),
      area: document.getElementById('editArea').value.trim(),
      direccion: document.getElementById('editDireccion').value.trim(),
      observaciones: document.getElementById('editObservaciones').value.trim()
    };

    const submitBtn = document.getElementById('editSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Guardando...';

    try {
      const res = await fetch(`/api/trabajadores/${w.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo actualizar el trabajador';
        errorMsg.style.display = 'block';
        return;
      }

      renderViewMode(data.worker);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Guardar cambios';
    }
  });
}

function bindContratoForm(workerId) {
  const form = document.getElementById('contratoForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const successMsg = document.getElementById('contratoSuccessMsg');
    const errorMsg = document.getElementById('contratoErrorMsg');
    successMsg.style.display = 'none';
    errorMsg.style.display = 'none';

    const fechaFinContrato = document.getElementById('nuevaFechaFinContrato').value;
    const fechaRenovacion = document.getElementById('nuevaFechaRenovacion').value;

    if (!fechaFinContrato) {
      errorMsg.textContent = 'La nueva fecha de fin de contrato es obligatoria';
      errorMsg.style.display = 'block';
      return;
    }

    const submitBtn = document.getElementById('contratoSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Guardando...';

    try {
      const res = await fetch(`/api/trabajadores/${workerId}/contrato`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fechaFinContrato, fechaRenovacion })
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo actualizar el contrato';
        errorMsg.style.display = 'block';
        return;
      }

      renderViewMode(data.worker);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Guardar nueva fecha';
    }
  });
}

// ---------- Carpetas ----------

function bindCarpetas(w) {
  const btn = document.getElementById('crearCarpetaBtn');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    const errorMsg = document.getElementById('carpetaErrorMsg');
    errorMsg.style.display = 'none';

    const input = document.getElementById('nuevaCarpetaInput');
    const nombre = input.value.trim();

    if (!nombre) {
      errorMsg.textContent = 'Escribe un nombre para la carpeta';
      errorMsg.style.display = 'block';
      return;
    }

    btn.disabled = true;
    btn.textContent = 'Creando...';

    try {
      const res = await fetch(`/api/trabajadores/${w.id}/carpetas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre })
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo crear la carpeta';
        errorMsg.style.display = 'block';
        return;
      }

      loadDetail(w.id);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.textContent = '+ Crear carpeta';
    }
  });
}

// ---------- Subir documentos ----------

function bindUploadDocs(w) {
  const addBtn = document.getElementById('addUploadRowBtn');
  const uploadRows = document.getElementById('uploadRows');
  if (!addBtn || !uploadRows) return;

  const carpetas = w.carpetas || [];

  uploadRows.innerHTML = '';
  addUploadRow(carpetas);

  addBtn.addEventListener('click', () => addUploadRow(carpetas));

  document.getElementById('subirDocsBtn').addEventListener('click', async () => {
    const errorMsg = document.getElementById('uploadErrorMsg');
    errorMsg.style.display = 'none';

    const rows = document.querySelectorAll('#uploadRows .upload-row');
    const formData = new FormData();
    const nombres = [];
    const carpetasIds = [];
    let hayArchivos = false;

    rows.forEach((row) => {
      const fileInput = row.querySelector('.doc-file-input');
      const labelInput = row.querySelector('.doc-label-input');
      const carpetaSelect = row.querySelector('.doc-carpeta-select');
      const file = fileInput.files[0];
      if (file) {
        formData.append('documentos', file);
        nombres.push(labelInput.value.trim() || file.name);
        carpetasIds.push(carpetaSelect.value ? Number(carpetaSelect.value) : null);
        hayArchivos = true;
      }
    });
    formData.append('documentosNombres', JSON.stringify(nombres));
    formData.append('carpetasIds', JSON.stringify(carpetasIds));

    if (!hayArchivos) {
      errorMsg.textContent = 'Elige al menos un archivo PDF';
      errorMsg.style.display = 'block';
      return;
    }

    const btn = document.getElementById('subirDocsBtn');
    btn.disabled = true;
    btn.textContent = 'Subiendo...';

    try {
      const res = await fetch(`/api/trabajadores/${w.id}/documentos`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudieron subir los documentos';
        errorMsg.style.display = 'block';
        return;
      }

      renderViewMode(data.worker);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Subir documentos';
    }
  });
}

function addUploadRow(carpetas) {
  uploadRowCount += 1;
  const rowId = `uprow_${uploadRowCount}`;

  const opcionesCarpetas = (carpetas || [])
    .map((c) => `<option value="${c.id}">${escapeHtml(c.nombre)}</option>`)
    .join('');

  const wrapper = document.createElement('div');
  wrapper.className = 'upload-row';
  wrapper.dataset.rowId = rowId;

  wrapper.innerHTML = `
    <input type="text" placeholder="Nombre del documento (ej. DNI, Contrato)" class="doc-label-input">
    <select class="doc-carpeta-select" title="Carpeta (opcional)">
      <option value="">Sin carpeta</option>
      ${opcionesCarpetas}
    </select>
    <label class="btn secondary" style="cursor:pointer;">
      Elegir PDF
      <input type="file" accept="application/pdf" class="doc-file-input" style="display:none;">
    </label>
    <span class="file-name">Ningún archivo seleccionado</span>
    <button type="button" class="btn danger remove-row-btn">Quitar</button>
  `;

  const fileInput = wrapper.querySelector('.doc-file-input');
  const fileNameSpan = wrapper.querySelector('.file-name');
  const labelInput = wrapper.querySelector('.doc-label-input');
  const removeBtn = wrapper.querySelector('.remove-row-btn');

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    fileNameSpan.textContent = file ? file.name : 'Ningún archivo seleccionado';
    if (file && !labelInput.value.trim()) {
      labelInput.value = file.name.replace(/\.pdf$/i, '');
    }
  });

  removeBtn.addEventListener('click', () => wrapper.remove());

  document.getElementById('uploadRows').appendChild(wrapper);
}

async function eliminarDocumento(workerId, docId) {
  if (!confirm('¿Eliminar este documento? Esta acción no se puede deshacer.')) return;

  try {
    const res = await fetch(`/api/trabajadores/${workerId}/documentos/${docId}`, {
      method: 'DELETE'
    });
    if (!res.ok) {
      alert('No se pudo eliminar el documento');
      return;
    }
    loadDetail(workerId);
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

function togglePdfPreview(docId, url) {
  const area = document.getElementById('pdfPreviewArea');
  const existingId = `pdf_prev_${docId}`;
  const existing = document.getElementById(existingId);
  if (existing) {
    existing.remove();
    return;
  }
  area.innerHTML = '';
  const div = document.createElement('div');
  div.className = 'pdf-preview-wrap';
  div.id = existingId;
  div.innerHTML = `<iframe src="${url}"></iframe>`;
  area.appendChild(div);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, '&quot;');
}