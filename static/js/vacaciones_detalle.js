async function cargarDetalle() {
  try {
    const res = await fetch(`/api/vacaciones/${TRABAJADOR_ID}`);
    const data = await res.json();
    render(data);
  } catch (err) {
    document.getElementById('tablaTomadas').innerHTML =
      '<tr><td colspan="4" class="empty-state">Error al cargar</td></tr>';
  }
}

function render(data) {
  const { trabajador, calculo, tomadas } = data;

  document.getElementById('fechaIngresoTexto').textContent =
    trabajador.fechaIngreso ? `Fecha de ingreso: ${trabajador.fechaIngreso}` : 'Sin fecha de ingreso registrada';

  document.getElementById('statAcumulado').textContent = formatearDias(calculo.acumulado);
  document.getElementById('statTomadas').textContent = formatearDias(calculo.tomadas);
  const statSaldo = document.getElementById('statSaldo');
  statSaldo.textContent = formatearDias(calculo.saldo);
  statSaldo.className = 'stat-value' + (calculo.saldo < 0 ? ' error' : '');

  document.getElementById('calculoAutomaticoTexto').textContent =
    `Cálculo automático: ${calculo.mesesCumplidos} mes(es) cumplido(s) × 2.5 = ${formatearDias(calculo.acumuladoAutomatico)}` +
    (calculo.ajusteManual !== null ? ` — actualmente reemplazado por un ajuste manual de ${formatearDias(calculo.ajusteManual)}.` : '.');

  const ajusteInput = document.getElementById('ajusteManualInput');
  ajusteInput.value = calculo.ajusteManual !== null ? calculo.ajusteManual : '';

  renderTomadas(tomadas);
}

function renderTomadas(tomadas) {
  const tabla = document.getElementById('tablaTomadas');

  if (tomadas.length === 0) {
    tabla.innerHTML = '<tr><td colspan="5" class="empty-state">Todavía no se registró ningún día tomado.</td></tr>';
    return;
  }

  tabla.innerHTML = '';
  tomadas.forEach((t) => {
    const archivos = t.archivos || [];
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
      <td>${t.fecha}</td>
      <td>${formatearDias(t.dias)}</td>
      <td>${t.observacion ? escapeHtml(t.observacion) : '<span class="muted">—</span>'}</td>
      <td>
        <div class="archivos-lista" style="margin-bottom:6px;">${archivosHtml}</div>
        <label class="btn secondary" style="cursor:pointer;font-size:0.78rem;padding:5px 8px;display:inline-block;">
          + Adjuntar PDF
          <input type="file" accept="application/pdf" class="input-archivo-periodo" style="display:none;">
        </label>
      </td>
      <td><button type="button" class="btn danger" style="font-size:0.78rem;padding:5px 8px;" data-id="${t.id}">Quitar periodo</button></td>
    `;
    fila.querySelector('[data-id]').addEventListener('click', () => eliminarTomada(t.id));
    fila.querySelector('.input-archivo-periodo').addEventListener('change', (e) => subirArchivoPeriodo(t.id, e.target));
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
    const res = await fetch(`/api/vacaciones/tomadas/${periodoId}/archivos`, { method: 'POST', body: formData });
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
    const res = await fetch(`/api/vacaciones/archivos/${archivoId}`, { method: 'DELETE' });
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
  div.innerHTML = `<iframe src="/documentos-vacaciones/${archivoId}"></iframe>`;
  area.appendChild(div);
}

document.getElementById('guardarAjusteBtn').addEventListener('click', async () => {
  const errorMsg = document.getElementById('errorAjuste');
  errorMsg.style.display = 'none';

  const valor = document.getElementById('ajusteManualInput').value.trim();

  try {
    const res = await fetch(`/api/vacaciones/${TRABAJADOR_ID}/ajuste`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ diasAcumuladosManual: valor === '' ? null : Number(valor) })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo guardar el ajuste';
      errorMsg.style.display = 'block';
      return;
    }

    cargarDetalle();
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

document.getElementById('quitarAjusteBtn').addEventListener('click', async () => {
  document.getElementById('ajusteManualInput').value = '';
  document.getElementById('guardarAjusteBtn').click();
});

document.getElementById('agregarTomadaBtn').addEventListener('click', async () => {
  const errorMsg = document.getElementById('errorTomada');
  errorMsg.style.display = 'none';

  const fecha = document.getElementById('fechaTomada').value;
  const dias = document.getElementById('diasTomada').value;
  const observacion = document.getElementById('observacionTomada').value.trim();

  if (!fecha || !dias) {
    errorMsg.textContent = 'La fecha y la cantidad de días son obligatorias.';
    errorMsg.style.display = 'block';
    return;
  }

  try {
    const res = await fetch(`/api/vacaciones/${TRABAJADOR_ID}/tomadas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fecha, dias: Number(dias), observacion })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo guardar el registro';
      errorMsg.style.display = 'block';
      return;
    }

    document.getElementById('fechaTomada').value = '';
    document.getElementById('diasTomada').value = '';
    document.getElementById('observacionTomada').value = '';
    cargarDetalle();
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

async function eliminarTomada(id) {
  if (!confirm('¿Quitar este registro de días tomados?')) return;
  try {
    const res = await fetch(`/api/vacaciones/tomadas/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo quitar el registro');
      return;
    }
    cargarDetalle();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

function formatearDias(numero) {
  const valor = Number(numero);
  return (Number.isInteger(valor) ? valor : valor.toFixed(1)) + ' d';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarDetalle();
