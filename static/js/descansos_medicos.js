function obtenerAnioDeUrl() {
  const params = new URLSearchParams(window.location.search);
  const anio = parseInt(params.get('anio'), 10);
  return Number.isInteger(anio) ? anio : new Date().getFullYear();
}

const anioActual = obtenerAnioDeUrl();

function actualizarLinksNavegacion() {
  document.getElementById('tituloAnio').textContent = `Año ${anioActual}`;
  document.getElementById('anioAnteriorBtn').href = `?anio=${anioActual - 1}`;
  document.getElementById('anioSiguienteBtn').href = `?anio=${anioActual + 1}`;
}

async function cargarDescansos() {
  const tabla = document.getElementById('tablaDescansos');
  try {
    const res = await fetch(`/api/descansos-medicos?anio=${anioActual}`);
    const data = await res.json();
    renderTabla(data.trabajadores || []);
  } catch (err) {
    tabla.innerHTML = '<tr><td colspan="3" class="empty-state">Error al cargar</td></tr>';
  }
}

function renderTabla(trabajadores) {
  const tabla = document.getElementById('tablaDescansos');

  if (trabajadores.length === 0) {
    tabla.innerHTML = '<tr><td colspan="3" class="empty-state">No hay trabajadores activos.</td></tr>';
    return;
  }

  tabla.innerHTML = '';
  trabajadores.forEach((t) => {
    const fila = document.createElement('tr');
    fila.style.cursor = 'pointer';
    fila.innerHTML = `
      <td>${escapeHtml(t.nombre)}</td>
      <td>${t.totalPeriodos}</td>
      <td><strong>${t.totalDias} día(s)</strong></td>
    `;
    fila.addEventListener('click', () => {
      window.location.href = `/descansos-medicos/${t.id}`;
    });
    tabla.appendChild(fila);
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

actualizarLinksNavegacion();
cargarDescansos();
