let trabajadoresCache = [];
let vistaActual = 'tabla';

async function cargarResumen() {
  try {
    const res = await fetch('/api/trabajadores/resumen');
    const data = await res.json();
    trabajadoresCache = data.trabajadores || [];
    render();
  } catch (err) {
    document.getElementById('tablaCuerpo').innerHTML =
      '<tr><td colspan="8" class="empty-state">Error al cargar</td></tr>';
  }
}

document.querySelectorAll('#vistaToggle a').forEach((tab) => {
  tab.addEventListener('click', (e) => {
    e.preventDefault();
    vistaActual = tab.dataset.vista;
    document.querySelectorAll('#vistaToggle a').forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('vistaTabla').style.display = vistaActual === 'tabla' ? 'block' : 'none';
    document.getElementById('vistaTarjetas').style.display = vistaActual === 'tarjetas' ? 'grid' : 'none';
  });
});

function render() {
  renderTabla();
  renderTarjetas();
}

function renderTabla() {
  const cuerpo = document.getElementById('tablaCuerpo');

  if (trabajadoresCache.length === 0) {
    cuerpo.innerHTML = '<tr><td colspan="8" class="empty-state">No hay trabajadores activos.</td></tr>';
    return;
  }

  cuerpo.innerHTML = '';
  trabajadoresCache.forEach((t) => {
    const fila = document.createElement('tr');
    const contacto = t.contactoEmergenciaNombres
      ? `${escapeHtml(t.contactoEmergenciaNombres)}${t.contactoEmergenciaTelefono ? ' · ' + escapeHtml(t.contactoEmergenciaTelefono) : ''}`
      : '<span class="muted">—</span>';

    fila.innerHTML = `
      <td><a href="/buscar-trabajador?id=${t.id}">${escapeHtml(t.nombreCompleto)}</a></td>
      <td>${escapeHtml(t.dni || '—')}</td>
      <td>${t.fechaIngreso || '<span class="muted">—</span>'}</td>
      <td>${t.fechaNacimiento || '<span class="muted">—</span>'}</td>
      <td>${t.email ? escapeHtml(t.email) : '<span class="muted">—</span>'}</td>
      <td>${t.telefono ? escapeHtml(t.telefono) : '<span class="muted">—</span>'}</td>
      <td>${t.direccion ? escapeHtml(t.direccion) : '<span class="muted">—</span>'}</td>
      <td>${contacto}</td>
    `;
    cuerpo.appendChild(fila);
  });
}

function renderTarjetas() {
  const cont = document.getElementById('vistaTarjetas');

  if (trabajadoresCache.length === 0) {
    cont.innerHTML = '<div class="empty-state">No hay trabajadores activos.</div>';
    return;
  }

  cont.innerHTML = '';
  trabajadoresCache.forEach((t) => {
    const inicial = (t.nombreCompleto || '?')[0].toUpperCase();
    const avatarHtml = t.tieneFoto
      ? `<img src="/foto/${t.id}" alt="">`
      : `<span>${inicial}</span>`;

    const tarjeta = document.createElement('div');
    tarjeta.className = 'tarjeta-personal';
    tarjeta.innerHTML = `
      <div class="tarjeta-personal-header">
        <div class="avatar-trabajador">${avatarHtml}</div>
        <div>
          <div class="tarjeta-personal-nombre">${escapeHtml(t.nombreCompleto)}</div>
          <div class="muted" style="font-size:0.8rem;">DNI: ${escapeHtml(t.dni || '—')}</div>
        </div>
      </div>
      <div class="tarjeta-personal-datos">
        <div><span class="label-chico">Ingreso</span> ${t.fechaIngreso || '—'}</div>
        <div><span class="label-chico">Nacimiento</span> ${t.fechaNacimiento || '—'}</div>
        <div><span class="label-chico">Correo</span> ${t.email ? escapeHtml(t.email) : '—'}</div>
        <div><span class="label-chico">Teléfono</span> ${t.telefono ? escapeHtml(t.telefono) : '—'}</div>
        <div><span class="label-chico">Dirección</span> ${t.direccion ? escapeHtml(t.direccion) : '—'}</div>
        <div>
          <span class="label-chico">Contacto de emergencia</span>
          ${t.contactoEmergenciaNombres ? `
            ${escapeHtml(t.contactoEmergenciaNombres)}
            ${t.contactoEmergenciaTelefono ? '· ' + escapeHtml(t.contactoEmergenciaTelefono) : ''}
            ${t.contactoEmergenciaDireccion ? '<br>' + escapeHtml(t.contactoEmergenciaDireccion) : ''}
          ` : '—'}
        </div>
      </div>
      <a class="btn secondary" href="/buscar-trabajador?id=${t.id}" style="margin-top:10px;font-size:0.8rem;">Ver ficha completa</a>
    `;
    cont.appendChild(tarjeta);
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarResumen();
