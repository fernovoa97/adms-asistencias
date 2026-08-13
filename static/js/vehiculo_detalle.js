const ETIQUETA_DOC_ESTADO = {
  vencido: { texto: 'Vencido', clase: 'doc-vencido' },
  por_vencer: { texto: 'Por vencer', clase: 'doc-por-vencer' },
  vigente: { texto: 'Vigente', clase: 'doc-vigente' },
  sin_fecha: { texto: 'Sin fecha de vencimiento', clase: 'doc-sin-fecha' }
};

let conductoresCache = [];

async function cargarConductores() {
  try {
    const res = await fetch('/api/trabajadores/buscar?q=');
    const data = await res.json();
    conductoresCache = (data.results || []).filter((t) => t.estado !== 'INACTIVO');
  } catch (err) {
    conductoresCache = [];
  }
}

async function cargarDetalle() {
  await cargarConductores();
  try {
    const res = await fetch(`/api/vehiculos/${VEHICULO_ID}`);
    const data = await res.json();
    renderDetalle(data.vehiculo);
    renderDocumentos(data.documentos || []);
  } catch (err) {
    document.getElementById('detalleVehiculo').innerHTML = '<div class="empty-state">Error al cargar</div>';
  }
}

function renderDetalle(v) {
  const cont = document.getElementById('detalleVehiculo');

  const opcionesConductor = conductoresCache.map((c) =>
    `<option value="${c.id}" ${v.conductorId === c.id ? 'selected' : ''}>${escapeHtml(c.nombres)} ${escapeHtml(c.apellidos)}</option>`
  ).join('');

  cont.innerHTML = `
    <div class="panel">
      <div class="barra" style="margin-bottom:10px;">
        <h1 style="margin:0;">${escapeHtml(v.placa)}</h1>
        <button type="button" class="btn danger" id="eliminarVehiculoBtn">Eliminar vehículo</button>
      </div>
      <div class="error-msg" id="errorVehiculo"></div>
      <form id="vehiculoEditForm">
        <div class="grid-2">
          <div class="field">
            <label for="editPlaca">Placa *</label>
            <input type="text" id="editPlaca" value="${escapeAttr(v.placa)}" required style="text-transform:uppercase;">
          </div>
          <div class="field">
            <label for="editEstado">Estado</label>
            <select id="editEstado">
              <option value="ACTIVO" ${v.estado === 'ACTIVO' ? 'selected' : ''}>Activo</option>
              <option value="MANTENIMIENTO" ${v.estado === 'MANTENIMIENTO' ? 'selected' : ''}>En mantenimiento</option>
              <option value="VENDIDO" ${v.estado === 'VENDIDO' ? 'selected' : ''}>Vendido</option>
              <option value="BAJA" ${v.estado === 'BAJA' ? 'selected' : ''}>De baja</option>
            </select>
          </div>
          <div class="field">
            <label for="editTipoAdquisicion">Tipo de adquisición</label>
            <select id="editTipoAdquisicion">
              <option value="COMPRA" ${v.tipoAdquisicion === 'COMPRA' ? 'selected' : ''}>Compra (propio)</option>
              <option value="ALQUILER" ${v.tipoAdquisicion === 'ALQUILER' ? 'selected' : ''}>Alquiler</option>
            </select>
          </div>
          <div class="field">
            <label for="editMarca">Marca</label>
            <input type="text" id="editMarca" value="${escapeAttr(v.marca || '')}">
          </div>
          <div class="field">
            <label for="editModelo">Modelo</label>
            <input type="text" id="editModelo" value="${escapeAttr(v.modelo || '')}">
          </div>
          <div class="field">
            <label for="editAnio">Año</label>
            <input type="number" id="editAnio" value="${v.anio || ''}" min="1970" max="2100">
          </div>
          <div class="field">
            <label for="editColor">Color</label>
            <input type="text" id="editColor" value="${escapeAttr(v.color || '')}">
          </div>
          <div class="field">
            <label for="editTipo">Tipo de vehículo</label>
            <input type="text" id="editTipo" value="${escapeAttr(v.tipo || '')}">
          </div>
          <div class="field">
            <label for="editFechaAdquisicion">Fecha de adquisición</label>
            <input type="date" id="editFechaAdquisicion" value="${v.fechaAdquisicion || ''}">
          </div>
          <div class="field">
            <label for="editConductorId">Conductor asignado</label>
            <select id="editConductorId">
              <option value="">Sin asignar</option>
              ${opcionesConductor}
            </select>
          </div>
        </div>

        <div class="grid-2" id="editCamposAlquiler" style="${v.tipoAdquisicion === 'ALQUILER' ? '' : 'display:none;'}">
          <div class="field">
            <label for="editAlquilerProveedor">Empresa / persona que alquila el vehículo</label>
            <input type="text" id="editAlquilerProveedor" value="${escapeAttr(v.alquilerProveedor || '')}">
          </div>
          <div class="field">
            <label for="editAlquilerFechaFin">Fecha de fin de contrato</label>
            <input type="date" id="editAlquilerFechaFin" value="${v.alquilerFechaFin || ''}">
          </div>
        </div>

        <div class="field">
          <label for="editObservaciones">Observaciones</label>
          <textarea id="editObservaciones" rows="2">${escapeHtml(v.observaciones || '')}</textarea>
        </div>

        <button type="submit" class="btn">Guardar cambios</button>
      </form>
    </div>
  `;

  document.getElementById('editTipoAdquisicion').addEventListener('change', (e) => {
    document.getElementById('editCamposAlquiler').style.display = e.target.value === 'ALQUILER' ? 'grid' : 'none';
  });

  document.getElementById('vehiculoEditForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorMsg = document.getElementById('errorVehiculo');
    errorMsg.style.display = 'none';

    const payload = {
      placa: document.getElementById('editPlaca').value.trim(),
      estado: document.getElementById('editEstado').value,
      tipoAdquisicion: document.getElementById('editTipoAdquisicion').value,
      marca: document.getElementById('editMarca').value.trim(),
      modelo: document.getElementById('editModelo').value.trim(),
      anio: document.getElementById('editAnio').value || null,
      color: document.getElementById('editColor').value.trim(),
      tipo: document.getElementById('editTipo').value.trim(),
      fechaAdquisicion: document.getElementById('editFechaAdquisicion').value || null,
      conductorId: document.getElementById('editConductorId').value || null,
      alquilerProveedor: document.getElementById('editAlquilerProveedor')?.value.trim() || '',
      alquilerFechaFin: document.getElementById('editAlquilerFechaFin')?.value || null,
      observaciones: document.getElementById('editObservaciones').value.trim()
    };

    try {
      const res = await fetch(`/api/vehiculos/${VEHICULO_ID}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo actualizar el vehículo';
        errorMsg.style.display = 'block';
        return;
      }

      document.title = `${payload.placa} · Vehículos`;
      cargarDetalle();
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    }
  });

  document.getElementById('eliminarVehiculoBtn').addEventListener('click', async () => {
    if (!confirm(`¿Eliminar el vehículo ${v.placa}? Se borran también todos sus documentos.`)) return;
    try {
      const res = await fetch(`/api/vehiculos/${VEHICULO_ID}`, { method: 'DELETE' });
      if (!res.ok) {
        alert('No se pudo eliminar el vehículo');
        return;
      }
      window.location.href = '/vehiculos';
    } catch (err) {
      alert('Error de conexión con el servidor');
    }
  });
}

function renderDocumentos(documentos) {
  const cont = document.getElementById('documentosList');

  if (documentos.length === 0) {
    cont.innerHTML = '<p class="muted">Todavía no se subió ningún documento.</p>';
    return;
  }

  cont.innerHTML = '';
  documentos.forEach((doc) => {
    const info = ETIQUETA_DOC_ESTADO[doc.estado] || ETIQUETA_DOC_ESTADO.sin_fecha;
    const detalle = doc.diasRestantes !== null
      ? (doc.diasRestantes >= 0 ? `vence en ${doc.diasRestantes} día(s)` : `venció hace ${Math.abs(doc.diasRestantes)} día(s)`)
      : '';

    const item = document.createElement('div');
    item.className = 'doc-item';
    item.innerHTML = `
      <div>
        <div class="doc-name">${escapeHtml(doc.tipo)}</div>
        <div class="muted" style="font-size:0.8rem;">
          <span class="badge ${info.clase}">${info.texto}</span>
          ${doc.fechaVencimiento ? `Vence: ${doc.fechaVencimiento} (${detalle})` : ''}
        </div>
      </div>
      <div class="doc-actions">
        <button class="btn secondary" data-preview="${doc.id}">Vista previa</button>
        <a class="btn secondary" href="/documentos-vehiculo/${doc.id}" target="_blank">Abrir</a>
        <button class="btn danger" data-eliminar="${doc.id}">Eliminar</button>
      </div>
    `;
    item.querySelector('[data-preview]').addEventListener('click', () => togglePreview(doc.id));
    item.querySelector('[data-eliminar]').addEventListener('click', () => eliminarDocumento(doc.id));
    cont.appendChild(item);
  });
}

document.getElementById('archivoDocumento').addEventListener('change', async (e) => {
  const errorMsg = document.getElementById('errorDoc');
  errorMsg.style.display = 'none';

  const archivo = e.target.files[0];
  if (!archivo) return;

  const tipo = document.getElementById('tipoDocumento').value.trim();
  const fechaVencimiento = document.getElementById('fechaVencimientoDoc').value;

  if (!tipo) {
    errorMsg.textContent = 'Indica el tipo de documento antes de elegir el PDF (ej. SOAT).';
    errorMsg.style.display = 'block';
    e.target.value = '';
    return;
  }

  const formData = new FormData();
  formData.append('tipo', tipo);
  formData.append('fechaVencimiento', fechaVencimiento);
  formData.append('archivo', archivo);

  try {
    const res = await fetch(`/api/vehiculos/${VEHICULO_ID}/documentos`, { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo subir el documento';
      errorMsg.style.display = 'block';
      return;
    }

    document.getElementById('tipoDocumento').value = '';
    document.getElementById('fechaVencimientoDoc').value = '';
    e.target.value = '';
    cargarDetalle();
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

async function eliminarDocumento(docId) {
  if (!confirm('¿Eliminar este documento?')) return;
  try {
    const res = await fetch(`/api/vehiculos/documentos/${docId}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo eliminar el documento');
      return;
    }
    cargarDetalle();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

function togglePreview(docId) {
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
  div.innerHTML = `<iframe src="/documentos-vehiculo/${docId}"></iframe>`;
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

cargarDetalle();
