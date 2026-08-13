async function cargarVacaciones() {
  const tabla = document.getElementById('tablaVacaciones');
  try {
    const res = await fetch('/api/vacaciones');
    const data = await res.json();
    renderTabla(data.trabajadores || []);
  } catch (err) {
    tabla.innerHTML = '<tr><td colspan="6" class="empty-state">Error al cargar</td></tr>';
  }
}

function renderTabla(trabajadores) {
  const tabla = document.getElementById('tablaVacaciones');

  if (trabajadores.length === 0) {
    tabla.innerHTML = '<tr><td colspan="6" class="empty-state">No hay trabajadores activos.</td></tr>';
    return;
  }

  tabla.innerHTML = '';
  trabajadores.forEach((t) => {
    const fila = document.createElement('tr');
    fila.style.cursor = 'pointer';
    fila.innerHTML = `
      <td>${escapeHtml(t.nombre)}</td>
      <td>${t.fechaIngreso || '<span class="muted">—</span>'}</td>
      <td>${t.mesesCumplidos}</td>
      <td>${formatearDias(t.acumulado)} ${t.ajusteManual !== null ? '<span class="tag" title="Ajustado manualmente">manual</span>' : ''}</td>
      <td>${formatearDias(t.tomadas)}</td>
      <td class="${t.saldo < 0 ? 'descuento-alto' : ''}"><strong>${formatearDias(t.saldo)}</strong></td>
    `;
    fila.addEventListener('click', () => {
      window.location.href = `/vacaciones/${t.id}`;
    });
    tabla.appendChild(fila);
  });
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

cargarVacaciones();
