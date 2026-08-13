let itemsActuales = [];

async function cargarTabla() {
  try {
    const res = await fetch(`/api/actas/${ACTA_ID}/tabla`);
    const data = await res.json();
    itemsActuales = data.items || [];
    renderTabla(data.items || [], data.trabajadores || []);
  } catch (err) {
    document.getElementById('tablaCuerpo').innerHTML =
      '<tr><td class="empty-state">Error al cargar la tabla</td></tr>';
  }
}

function renderTabla(items, trabajadores) {
  const cabecera = document.getElementById('tablaCabecera');
  const cuerpo = document.getElementById('tablaCuerpo');

  // Cabecera: una columna por item, con boton para quitarlo
  const filaCabecera = document.createElement('tr');
  let html = '<th>Trabajador</th>';
  items.forEach((it) => {
    html += `
      <th>
        ${escapeHtml(it.nombre)}
        ${it.requiereDevolucion ? '<span class="tag" style="margin-left:4px;">devuelve</span>' : ''}
        <button type="button" class="quitar-item-btn" data-item-id="${it.id}" title="Quitar este ítem del acta">×</button>
      </th>
    `;
  });
  filaCabecera.innerHTML = html;
  cabecera.innerHTML = '';
  cabecera.appendChild(filaCabecera);

  cabecera.querySelectorAll('.quitar-item-btn').forEach((boton) => {
    boton.addEventListener('click', () => quitarItem(boton.dataset.itemId));
  });

  if (trabajadores.length === 0) {
    cuerpo.innerHTML = `<tr><td colspan="${items.length + 1}" class="empty-state">No hay trabajadores registrados.</td></tr>`;
    return;
  }

  if (items.length === 0) {
    cuerpo.innerHTML = `<tr><td class="empty-state">Agrega al menos un ítem arriba para empezar a registrar entregas.</td></tr>`;
    return;
  }

  cuerpo.innerHTML = '';
  trabajadores.forEach((t) => {
    const fila = document.createElement('tr');
    let filaHtml = `
      <td>
        ${escapeHtml(t.nombre)}
        ${t.estado === 'INACTIVO' ? '<span class="tag-inactivo">Inactivo</span>' : ''}
      </td>
    `;

    items.forEach((it) => {
      const registro = t.registros[it.id] || { entregado: false, fechaEntrega: null, fechaDevolucion: null };
      filaHtml += `
        <td>
          <div class="entrega-celda" data-item-id="${it.id}" data-trabajador-id="${t.id}">
            <label style="display:flex;align-items:center;gap:6px;font-size:0.85rem;">
              <input type="checkbox" class="check-entregado" ${registro.entregado ? 'checked' : ''}>
              Entregado
            </label>
            <input type="date" class="fecha-entrega" value="${registro.fechaEntrega || ''}" ${!registro.entregado ? 'disabled' : ''}>
            ${it.requiereDevolucion ? `
              <input type="date" class="fecha-devolucion" value="${registro.fechaDevolucion || ''}"
                     placeholder="Devolución" title="Fecha de devolución" ${!registro.entregado ? 'disabled' : ''}>
            ` : ''}
          </div>
        </td>
      `;
    });

    fila.innerHTML = filaHtml;
    cuerpo.appendChild(fila);

    fila.querySelectorAll('.entrega-celda').forEach((celda) => {
      const checkbox = celda.querySelector('.check-entregado');
      const fechaEntrega = celda.querySelector('.fecha-entrega');
      const fechaDevolucion = celda.querySelector('.fecha-devolucion');

      checkbox.addEventListener('change', () => {
        const habilitar = checkbox.checked;
        fechaEntrega.disabled = !habilitar;
        if (fechaDevolucion) fechaDevolucion.disabled = !habilitar;

        if (habilitar && !fechaEntrega.value) {
          fechaEntrega.value = new Date().toISOString().slice(0, 10);
        }
        if (!habilitar) {
          fechaEntrega.value = '';
          if (fechaDevolucion) fechaDevolucion.value = '';
        }

        guardarCelda(celda);
      });

      fechaEntrega.addEventListener('change', () => guardarCelda(celda));
      if (fechaDevolucion) fechaDevolucion.addEventListener('change', () => guardarCelda(celda));
    });
  });
}

async function guardarCelda(celda) {
  const itemId = celda.dataset.itemId;
  const trabajadorId = celda.dataset.trabajadorId;
  const checkbox = celda.querySelector('.check-entregado');
  const fechaEntrega = celda.querySelector('.fecha-entrega');
  const fechaDevolucion = celda.querySelector('.fecha-devolucion');

  try {
    const res = await fetch(`/api/actas/${ACTA_ID}/registro`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        itemId: Number(itemId),
        trabajadorId: Number(trabajadorId),
        entregado: checkbox.checked,
        fechaEntrega: fechaEntrega.value || null,
        fechaDevolucion: fechaDevolucion ? (fechaDevolucion.value || null) : null
      })
    });
    if (!res.ok) {
      const data = await res.json();
      alert(data.error || 'No se pudo guardar el cambio');
    }
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

async function quitarItem(itemId) {
  if (!confirm('¿Quitar este ítem del acta? Se pierde el registro de entregas de ese ítem para todos los trabajadores.')) return;
  try {
    const res = await fetch(`/api/actas/${ACTA_ID}/items/${itemId}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo quitar el ítem');
      return;
    }
    cargarTabla();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

document.getElementById('agregarItemBtn').addEventListener('click', async () => {
  const errorMsg = document.getElementById('errorMsg');
  errorMsg.style.display = 'none';

  const nombreInput = document.getElementById('nuevoItemNombre');
  const devolucionInput = document.getElementById('nuevoItemDevolucion');
  const nombre = nombreInput.value.trim();

  if (!nombre) {
    errorMsg.textContent = 'Escribe el nombre del ítem.';
    errorMsg.style.display = 'block';
    return;
  }

  try {
    const res = await fetch(`/api/actas/${ACTA_ID}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre, requiereDevolucion: devolucionInput.checked })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo agregar el ítem';
      errorMsg.style.display = 'block';
      return;
    }

    nombreInput.value = '';
    devolucionInput.checked = false;
    cargarTabla();
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

cargarTabla();
