// Registro de proveedores de las ordenes de compra.

let temporizadorBusqueda = null;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function mostrarError(id, texto) {
  const caja = document.getElementById(id);
  caja.textContent = texto;
  caja.style.display = texto ? 'block' : 'none';
}

async function enviar(url, metodo, cuerpo) {
  const res = await fetch(url, {
    method: metodo,
    headers: { 'Content-Type': 'application/json' },
    body: cuerpo ? JSON.stringify(cuerpo) : undefined
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'No se pudo completar la acción');
  return data;
}

function soloDigitos(input) {
  input.addEventListener('input', () => {
    input.value = input.value.replace(/\D/g, '').slice(0, 11);
  });
}

async function cargarProveedores() {
  const body = document.getElementById('proveedoresBody');
  const q = document.getElementById('busquedaProveedor').value.trim();
  try {
    const res = await fetch(`/api/proveedores?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderProveedores(data.proveedores || [], q);
  } catch (err) {
    body.innerHTML = '<tr><td colspan="5" class="empty-state">Error al cargar los proveedores</td></tr>';
  }
}

function renderProveedores(proveedores, q) {
  const body = document.getElementById('proveedoresBody');
  if (proveedores.length === 0) {
    body.innerHTML = `<tr><td colspan="5" class="empty-state">${q ? 'No hay proveedores que coincidan con la búsqueda.' : 'Todavía no hay proveedores registrados.'}</td></tr>`;
    return;
  }

  body.innerHTML = '';
  proveedores.forEach((p) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="col-ruc"><input type="text" class="pv-ruc" inputmode="numeric" maxlength="11"></td>
      <td><input type="text" class="pv-nombre"></td>
      <td><input type="text" class="pv-direccion"></td>
      <td class="col-ordenes num">${p.ordenes}</td>
      <td>
        <div class="doc-actions" style="justify-content:flex-end;">
          <button type="button" class="btn secondary sm btn-guardar">Guardar</button>
          ${PUEDE_ELIMINAR ? '<button type="button" class="btn danger sm btn-eliminar">Eliminar</button>' : ''}
        </div>
      </td>
    `;
    const campoRuc = tr.querySelector('.pv-ruc');
    const campoNombre = tr.querySelector('.pv-nombre');
    const campoDireccion = tr.querySelector('.pv-direccion');
    campoRuc.value = p.ruc;
    campoNombre.value = p.nombre;
    campoDireccion.value = p.direccion;
    soloDigitos(campoRuc);

    tr.querySelector('.btn-guardar').addEventListener('click', async (e) => {
      mostrarError('errorLista', '');
      try {
        await enviar(`/api/proveedores/${p.id}`, 'PUT', {
          ruc: campoRuc.value.trim(),
          nombre: campoNombre.value.trim(),
          direccion: campoDireccion.value.trim()
        });
        e.target.textContent = 'Guardado';
        setTimeout(() => { e.target.textContent = 'Guardar'; }, 1500);
      } catch (err) {
        mostrarError('errorLista', err.message);
      }
    });

    const botonEliminar = tr.querySelector('.btn-eliminar');
    if (botonEliminar) {
      botonEliminar.addEventListener('click', async () => {
        if (!confirm(`¿Eliminar el proveedor ${p.nombre}? Sus órdenes de compra no se borran.`)) return;
        mostrarError('errorLista', '');
        try {
          await enviar(`/api/proveedores/${p.id}`, 'DELETE');
          cargarProveedores();
        } catch (err) {
          mostrarError('errorLista', err.message);
        }
      });
    }

    body.appendChild(tr);
  });
}

soloDigitos(document.getElementById('nuevoRuc'));

document.getElementById('nuevoProveedorForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  mostrarError('errorNuevo', '');
  try {
    await enviar('/api/proveedores', 'POST', {
      ruc: document.getElementById('nuevoRuc').value.trim(),
      nombre: document.getElementById('nuevoNombre').value.trim(),
      direccion: document.getElementById('nuevaDireccion').value.trim()
    });
    e.target.reset();
    cargarProveedores();
  } catch (err) {
    mostrarError('errorNuevo', err.message);
  }
});

document.getElementById('busquedaProveedor').addEventListener('input', () => {
  clearTimeout(temporizadorBusqueda);
  temporizadorBusqueda = setTimeout(cargarProveedores, 250);
});

cargarProveedores();
