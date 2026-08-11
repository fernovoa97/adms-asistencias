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

    const opcionesCorreo = [];
    if (t.email_corporativo) opcionesCorreo.push(t.email_corporativo);
    if (t.email_personal) opcionesCorreo.push(t.email_personal);

    const estadoInfo = t.boleta_id
      ? (ETIQUETA_ESTADO[t.estado_envio] || ETIQUETA_ESTADO.PENDIENTE)
      : null;

    fila.innerHTML = `
      <td>${escapeHtml(t.nombre)}</td>
      <td>
        <label class="btn secondary" style="cursor:pointer;font-size:0.82rem;padding:6px 10px;">
          ${t.archivo_nombre ? 'Reemplazar PDF' : 'Subir PDF'}
          <input type="file" accept="application/pdf" class="input-archivo" style="display:none;">
        </label>
        <span class="muted archivo-nombre" style="margin-left:6px;">${t.archivo_nombre ? escapeHtml(t.archivo_nombre) : 'Sin archivo'}</span>
      </td>
      <td>
        ${opcionesCorreo.length > 0 ? `
          <select class="select-correo">
            ${opcionesCorreo.map((c) => `<option value="${escapeHtml(c)}" ${c === t.correo_destino ? 'selected' : ''}>${escapeHtml(c)}</option>`).join('')}
          </select>
        ` : '<span class="muted" style="font-style:italic;">Sin correo registrado</span>'}
      </td>
      <td class="celda-estado">
        ${estadoInfo
          ? `<span class="badge ${estadoInfo.clase}" ${t.error_detalle ? `title="${escapeHtml(t.error_detalle)}"` : ''}>${estadoInfo.texto}</span>`
          : '<span class="muted">Sin boleta</span>'}
      </td>
    `;

    const fileInput = fila.querySelector('.input-archivo');
    fileInput.addEventListener('change', () => subirBoleta(t.id, fila));

    tablaTrabajadores.appendChild(fila);
  });
}

async function subirBoleta(trabajadorId, fila) {
  const fileInput = fila.querySelector('.input-archivo');
  const file = fileInput.files[0];
  if (!file) return;

  const selectCorreo = fila.querySelector('.select-correo');
  const correoDestino = selectCorreo ? selectCorreo.value : '';

  if (!correoDestino) {
    alert('Este trabajador no tiene ningún correo registrado. Agrégale uno desde su ficha en "Buscar trabajador" antes de subir su boleta.');
    fileInput.value = '';
    return;
  }

  const formData = new FormData();
  formData.append('trabajador_id', trabajadorId);
  formData.append('correo_destino', correoDestino);
  formData.append('archivo', file);

  const nombreSpan = fila.querySelector('.archivo-nombre');
  nombreSpan.textContent = 'Subiendo…';

  try {
    const res = await fetch(`/api/periodos/${PERIODO_ID}/boletas`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || 'No se pudo subir el archivo');
      nombreSpan.textContent = 'Sin archivo';
      return;
    }

    cargarTrabajadores();
  } catch (err) {
    alert('Error de conexión con el servidor');
    nombreSpan.textContent = 'Sin archivo';
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarTrabajadores();
