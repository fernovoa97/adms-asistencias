let itemRowCount = 0;

function crearFilaItem() {
  itemRowCount += 1;
  const wrapper = document.createElement('div');
  wrapper.className = 'upload-row';
  wrapper.innerHTML = `
    <input type="text" placeholder="Nombre del ítem (ej. Gift card, Canasta)" class="item-nombre" style="flex:1;">
    <label style="display:flex;align-items:center;gap:6px;font-size:0.85rem;white-space:nowrap;">
      <input type="checkbox" class="item-devolucion">
      Requiere devolución
    </label>
    <button type="button" class="btn danger remove-item-btn">Quitar</button>
  `;
  wrapper.querySelector('.remove-item-btn').addEventListener('click', () => wrapper.remove());
  document.getElementById('itemsRows').appendChild(wrapper);
}

document.getElementById('addItemBtn').addEventListener('click', crearFilaItem);
crearFilaItem();
crearFilaItem();

document.getElementById('actaForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errorMsg = document.getElementById('errorMsg');
  errorMsg.style.display = 'none';

  const nombre = document.getElementById('nombreActa').value.trim();
  const descripcion = document.getElementById('descripcionActa').value.trim();

  const items = Array.from(document.querySelectorAll('#itemsRows .upload-row')).map((fila) => ({
    nombre: fila.querySelector('.item-nombre').value.trim(),
    requiereDevolucion: fila.querySelector('.item-devolucion').checked
  })).filter((it) => it.nombre);

  if (items.length === 0) {
    errorMsg.textContent = 'Agrega al menos un ítem (ej. Gift card, Canasta).';
    errorMsg.style.display = 'block';
    return;
  }

  try {
    const res = await fetch('/api/actas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre, descripcion, items })
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo crear el acta';
      errorMsg.style.display = 'block';
      return;
    }

    window.location.href = `/actas/${data.id}`;
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

async function cargarActas() {
  const cont = document.getElementById('actasList');
  try {
    const res = await fetch('/api/actas');
    const data = await res.json();
    renderActas(data.actas || []);
  } catch (err) {
    cont.innerHTML = '<div class="empty-state">Error al cargar las actas</div>';
  }
}

function renderActas(actas) {
  const cont = document.getElementById('actasList');
  if (actas.length === 0) {
    cont.innerHTML = '<div class="empty-state">Todavía no has creado ninguna acta.</div>';
    return;
  }

  cont.innerHTML = '';
  actas.forEach((a) => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `
      <div style="cursor:pointer;flex:1;" class="acta-link">
        <div class="name">${escapeHtml(a.nombre)}</div>
        <div class="meta">${a.total_items} ítem(s) · ${a.trabajadores_con_entrega} trabajador(es) con al menos una entrega</div>
      </div>
      <button type="button" class="btn danger" style="font-size:0.8rem;padding:6px 10px;">Eliminar</button>
    `;

    item.querySelector('.acta-link').addEventListener('click', () => {
      window.location.href = `/actas/${a.id}`;
    });

    item.querySelector('.btn.danger').addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm(`¿Eliminar el acta "${a.nombre}"? Se borra todo su registro de entregas.`)) return;
      try {
        const res = await fetch(`/api/actas/${a.id}`, { method: 'DELETE' });
        if (!res.ok) {
          alert('No se pudo eliminar el acta');
          return;
        }
        cargarActas();
      } catch (err) {
        alert('Error de conexión con el servidor');
      }
    });

    cont.appendChild(item);
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarActas();
