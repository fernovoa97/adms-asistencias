const tablaTrabajadores = document.getElementById('tablaTrabajadores');

const ETIQUETA_ESTADO = {
  ENVIADO: { texto: 'Enviado', clase: 'estado-puntual' },
  ERROR: { texto: 'Error', clase: 'estado-tardanza' },
  PENDIENTE: { texto: 'Pendiente', clase: 'estado-justificado' }
};

async function cargarTrabajadores() {
  try {
    const res = await fetch(`/api/periodos/${PERIODO_ID}/trabajadores`);
    const data = await res.json();
    renderTabla(data.trabajadores || []);
  } catch (err) {
    tablaTrabajadores.innerHTML = '<tr><td colspan="4" class="empty-state">Error al cargar los trabajadores</td></tr>';
  }
}

function renderTabla(trabajadores) {
  if (trabajadores.length === 0) {
    tablaTrabajadores.innerHTML = '<tr><td colspan="4" class="empty-state">No hay trabajadores activos.</td></tr>';
    return;
  }

  tablaTrabajadores.innerHTML = '';

  trabajadores.forEach((t) => {
    const fila = document.createElement('tr');
    fila.dataset.trabajadorId = t.id;

    // Que correos quedan marcados ahora mismo (separados por ";")
    const correosMarcados = (t.correo_destino || '').split(';').map((c) => c.trim()).filter(Boolean);

    const estadoInfo = t.boleta_id
      ? (ETIQUETA_ESTADO[t.estado_envio] || ETIQUETA_ESTADO.PENDIENTE)
      : null;

    const listaArchivos = (t.archivos || []).map((a) => `
      <div class="archivo-item" data-archivo-id="${a.id}">
        <span>${escapeHtml(a.nombre)}</span>
        <button type="button" class="archivo-quitar" title="Quitar este PDF">×</button>
      </div>
    `).join('');

    const opcionesCorreo = [];
    if (t.email_corporativo) opcionesCorreo.push({ etiqueta: 'Corporativo', valor: t.email_corporativo });
    if (t.email_personal) opcionesCorreo.push({ etiqueta: 'Personal', valor: t.email_personal });

    fila.innerHTML = `
      <td>${escapeHtml(t.nombre)}</td>
      <td>
        <div class="archivos-lista">${listaArchivos || '<span class="muted">Sin archivos</span>'}</div>
        <label class="btn secondary" style="cursor:pointer;font-size:0.82rem;padding:6px 10px;margin-top:4px;display:inline-block;">
          + Agregar PDF
          <input type="file" accept="application/pdf" class="input-archivo" multiple style="display:none;">
        </label>
      </td>
      <td>
        ${opcionesCorreo.length > 0 ? opcionesCorreo.map((op) => `
          <label class="correo-checkbox">
            <input type="checkbox" class="check-correo" value="${escapeHtml(op.valor)}"
                   ${correosMarcados.includes(op.valor) ? 'checked' : ''}>
            ${op.etiqueta} <span class="muted">(${escapeHtml(op.valor)})</span>
          </label>
        `).join('') : '<span class="muted" style="font-style:italic;">Sin correo registrado</span>'}
      </td>
      <td class="celda-estado">
        ${estadoInfo
          ? `<span class="badge ${estadoInfo.clase}" ${t.error_detalle ? `title="${escapeHtml(t.error_detalle)}"` : ''}>${estadoInfo.texto}</span>`
          : '<span class="muted">Sin boleta</span>'}
      </td>
    `;

    const fileInput = fila.querySelector('.input-archivo');
    fileInput.addEventListener('change', () => subirArchivos(t.id, fila));

    fila.querySelectorAll('.archivo-quitar').forEach((boton) => {
      boton.addEventListener('click', () => {
        const item = boton.closest('.archivo-item');
        eliminarArchivo(t.boleta_id, item.dataset.archivoId);
      });
    });

    fila.querySelectorAll('.check-correo').forEach((checkbox) => {
      checkbox.addEventListener('change', () => actualizarCorreo(t.id, fila));
    });

    tablaTrabajadores.appendChild(fila);
  });
}

async function subirArchivos(trabajadorId, fila) {
  const fileInput = fila.querySelector('.input-archivo');
  const archivos = Array.from(fileInput.files);
  if (archivos.length === 0) return;

  const formData = new FormData();
  formData.append('trabajador_id', trabajadorId);
  archivos.forEach((archivo) => formData.append('archivos', archivo));

  try {
    const res = await fetch(`/api/periodos/${PERIODO_ID}/boletas`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || 'No se pudo subir el archivo');
      return;
    }

    cargarTrabajadores();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

async function eliminarArchivo(boletaId, archivoId) {
  if (!boletaId) return;
  if (!confirm('¿Quitar este PDF de la boleta?')) return;

  try {
    const res = await fetch(`/api/boletas/${boletaId}/archivos/${archivoId}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo quitar el archivo');
      return;
    }
    cargarTrabajadores();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

async function actualizarCorreo(trabajadorId, fila) {
  const checkboxes = Array.from(fila.querySelectorAll('.check-correo'));
  const correosElegidos = checkboxes.filter((c) => c.checked).map((c) => c.value);

  try {
    const res = await fetch(`/api/periodos/${PERIODO_ID}/correo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trabajadorId, correoDestino: correosElegidos.join(';') })
    });
    if (!res.ok) {
      const data = await res.json();
      alert(data.error || 'No se pudo actualizar el correo');
    }
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarTrabajadores();
