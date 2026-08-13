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
    tabla.innerHTML = '<tr><td colspan="4" class="empty-state">Todavía no se registró ningún día tomado.</td></tr>';
    return;
  }

  tabla.innerHTML = '';
  tomadas.forEach((t) => {
    const fila = document.createElement('tr');
    fila.innerHTML = `
      <td>${t.fecha}</td>
      <td>${formatearDias(t.dias)}</td>
      <td>${t.observacion ? escapeHtml(t.observacion) : '<span class="muted">—</span>'}</td>
      <td><button type="button" class="btn danger" style="font-size:0.78rem;padding:5px 8px;" data-id="${t.id}">Quitar</button></td>
    `;
    fila.querySelector('button').addEventListener('click', () => eliminarTomada(t.id));
    tabla.appendChild(fila);
  });
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
