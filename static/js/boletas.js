const periodosList = document.getElementById('periodosList');
const errorMsg = document.getElementById('errorMsg');

async function cargarPeriodos() {
  try {
    const res = await fetch('/api/periodos');
    const data = await res.json();
    renderPeriodos(data.periodos || []);
  } catch (err) {
    periodosList.innerHTML = '<div class="empty-state">Error al cargar los periodos</div>';
  }
}

function renderPeriodos(periodos) {
  if (periodos.length === 0) {
    periodosList.innerHTML = '<div class="empty-state">Todavía no has creado ningún periodo de pago.</div>';
    return;
  }

  periodosList.innerHTML = '';
  periodos.forEach((p) => {
    const pendientes = p.total_cargadas - p.total_enviadas - p.total_error;

    const item = document.createElement('div');
    item.className = 'result-item';
    item.style.cursor = 'default';
    item.innerHTML = `
      <div style="cursor:pointer;flex:1;" class="periodo-link">
        <div class="name">${escapeHtml(p.nombre)}</div>
        <div class="meta">
          ${p.total_cargadas} boleta(s) cargada(s) ·
          ${p.total_enviadas} enviada(s)
          ${p.total_error > 0 ? ' · ' + p.total_error + ' con error' : ''}
          ${pendientes > 0 ? ' · ' + pendientes + ' pendiente(s)' : ''}
        </div>
      </div>
      <button type="button" class="btn danger" style="font-size:0.8rem;padding:6px 10px;">Eliminar</button>
    `;

    item.querySelector('.periodo-link').addEventListener('click', () => {
      window.location.href = `/boletas/${p.id}`;
    });

    item.querySelector('.btn.danger').addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm(`¿Eliminar el periodo "${p.nombre}"? Esto borra también todas las boletas cargadas en él (las que ya se enviaron no se pueden "desenviar", solo se borra el registro).`)) return;

      try {
        const res = await fetch(`/api/periodos/${p.id}`, { method: 'DELETE' });
        if (!res.ok) {
          alert('No se pudo eliminar el periodo');
          return;
        }
        cargarPeriodos();
      } catch (err) {
        alert('Error de conexión con el servidor');
      }
    });

    periodosList.appendChild(item);
  });
}

document.getElementById('periodoForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  errorMsg.style.display = 'none';

  const nombre = document.getElementById('nombrePeriodo').value.trim();
  if (!nombre) return;

  try {
    const res = await fetch('/api/periodos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo crear el periodo';
      errorMsg.style.display = 'block';
      return;
    }

    window.location.href = `/boletas/${data.id}`;
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarPeriodos();
