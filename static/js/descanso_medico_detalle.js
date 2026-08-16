async function cargarDetalle() {
  const tabla = document.getElementById('tablaPeriodos');
  try {
    const res = await fetch(`/api/descansos-medicos/${TRABAJADOR_ID}`);
    const data = await res.json();
    renderPeriodos(data.periodos || []);
  } catch (err) {
    tabla.innerHTML = '<tr><td colspan="5" class="empty-state">Error al cargar</td></tr>';
  }
}

function renderPeriodos(periodos) {
  const tabla = document.getElementById('tablaPeriodos');

  if (periodos.length === 0) {
    tabla.innerHTML = '<tr><td colspan="5" class="empty-state">Todavía no se registró ningún periodo.</td></tr>';
    return;
  }

  tabla.innerHTML = '';
  periodos.forEach((p) => {
    const fila = document.createElement('tr');
    fila.innerHTML = `
      <td>${p.fechaInicio}</td>
      <td>${p.fechaFin}</td>
      <td>${p.dias}</td>
      <td>${p.observacion ? escapeHtml(p.observacion) : '<span class="muted">—</span>'}</td>
      <td><button type="button" class="btn danger" style="font-size:0.78rem;padding:5px 8px;" data-id="${p.id}">Quitar</button></td>
    `;
    fila.querySelector('button').addEventListener('click', () => eliminarPeriodo(p.id));
    tabla.appendChild(fila);
  });
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
