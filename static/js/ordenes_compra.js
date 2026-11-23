// Lista de ordenes de compra con busqueda.

let monedasOC = {};
let temporizadorBusqueda = null;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function formatearMonto(valor) {
  return Number(valor).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatearFecha(iso) {
  const [a, m, d] = iso.split('-');
  return `${d}/${m}/${a}`;
}

async function cargarOrdenes() {
  const body = document.getElementById('ordenesBody');
  const q = document.getElementById('busquedaOC').value.trim();
  try {
    const res = await fetch(`/api/ordenes-compra?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    monedasOC = data.monedas || {};
    renderOrdenes(data.ordenes || [], q);
  } catch (err) {
    body.innerHTML = '<tr><td colspan="6" class="empty-state">Error al cargar las órdenes de compra</td></tr>';
  }
}

function renderOrdenes(ordenes, q) {
  const body = document.getElementById('ordenesBody');
  if (ordenes.length === 0) {
    body.innerHTML = `<tr><td colspan="6" class="empty-state">${q ? 'No hay órdenes que coincidan con la búsqueda.' : 'Todavía no hay órdenes de compra.'}</td></tr>`;
    return;
  }

  body.innerHTML = '';
  ordenes.forEach((o) => {
    const simbolo = (monedasOC[o.moneda] || {}).simbolo || '';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="celda-nombre"><a href="/ordenes-compra/${o.id}"><strong>${escapeHtml(o.correlativo)}</strong></a></td>
      <td>${formatearFecha(o.fecha)}</td>
      <td>${escapeHtml(o.proveedor_nombre)}</td>
      <td>${escapeHtml(o.proveedor_ruc)}</td>
      <td class="num celda-nombre">${simbolo} ${formatearMonto(o.total)}</td>
      <td>
        <div class="doc-actions" style="justify-content:flex-end;">
          <a class="btn secondary sm" href="/ordenes-compra/${o.id}">Ver</a>
          <a class="btn secondary sm" href="/ordenes-compra/${o.id}/editar">Editar</a>
          <a class="btn secondary sm" href="/ordenes-compra/${o.id}/excel">Excel</a>
          ${PUEDE_ELIMINAR ? '<button type="button" class="btn danger sm">Eliminar</button>' : ''}
        </div>
      </td>
    `;
    const botonEliminar = tr.querySelector('.btn.danger');
    if (botonEliminar) botonEliminar.addEventListener('click', async () => {
      if (!confirm(`¿Eliminar la orden de compra ${o.correlativo}? Esta acción no se puede deshacer.`)) return;
      try {
        const res = await fetch(`/api/ordenes-compra/${o.id}`, { method: 'DELETE' });
        if (!res.ok) {
          alert('No se pudo eliminar la orden de compra');
          return;
        }
        cargarOrdenes();
      } catch (err) {
        alert('Error de conexión con el servidor');
      }
    });
    body.appendChild(tr);
  });
}

document.getElementById('busquedaOC').addEventListener('input', () => {
  clearTimeout(temporizadorBusqueda);
  temporizadorBusqueda = setTimeout(cargarOrdenes, 250);
});

cargarOrdenes();
