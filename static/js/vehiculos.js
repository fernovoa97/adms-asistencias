const ETIQUETA_DOC_ESTADO = {
  vencido: { texto: 'Vencido', clase: 'doc-vencido' },
  por_vencer: { texto: 'Por vencer', clase: 'doc-por-vencer' },
  vigente: { texto: 'Vigente', clase: 'doc-vigente' },
  sin_fecha: { texto: 'Sin fecha', clase: 'doc-sin-fecha' }
};

async function cargarConductores() {
  try {
    const res = await fetch('/api/trabajadores/buscar?q=');
    const data = await res.json();
    const select = document.getElementById('conductorId');
    (data.results || []).forEach((t) => {
      if (t.estado === 'INACTIVO') return;
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = `${t.nombres} ${t.apellidos}`;
      select.appendChild(opt);
    });
  } catch (err) {
    // si falla, simplemente se queda solo la opcion "Sin asignar"
  }
}

document.getElementById('tipoAdquisicion').addEventListener('change', (e) => {
  document.getElementById('camposAlquiler').style.display = e.target.value === 'ALQUILER' ? 'grid' : 'none';
});

document.getElementById('vehiculoForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errorMsg = document.getElementById('errorMsg');
  errorMsg.style.display = 'none';

  const payload = {
    placa: document.getElementById('placa').value.trim(),
    tipoAdquisicion: document.getElementById('tipoAdquisicion').value,
    marca: document.getElementById('marca').value.trim(),
    modelo: document.getElementById('modelo').value.trim(),
    anio: document.getElementById('anio').value || null,
    color: document.getElementById('color').value.trim(),
    tipo: document.getElementById('tipo').value.trim(),
    fechaAdquisicion: document.getElementById('fechaAdquisicion').value || null,
    conductorId: document.getElementById('conductorId').value || null,
    alquilerProveedor: document.getElementById('alquilerProveedor').value.trim(),
    alquilerFechaFin: document.getElementById('alquilerFechaFin').value || null,
    observaciones: document.getElementById('observaciones').value.trim()
  };

  try {
    const res = await fetch('/api/vehiculos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo crear el vehículo';
      errorMsg.style.display = 'block';
      return;
    }

    window.location.href = `/vehiculos/${data.id}`;
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  }
});

async function cargarVehiculos() {
  const cont = document.getElementById('vehiculosList');
  try {
    const res = await fetch('/api/vehiculos');
    const data = await res.json();
    renderVehiculos(data.vehiculos || []);
  } catch (err) {
    cont.innerHTML = '<div class="empty-state">Error al cargar los vehículos</div>';
  }
}

function renderVehiculos(vehiculos) {
  const cont = document.getElementById('vehiculosList');
  if (vehiculos.length === 0) {
    cont.innerHTML = '<div class="empty-state">Todavía no hay vehículos registrados.</div>';
    return;
  }

  cont.innerHTML = '';
  vehiculos.forEach((v) => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.style.cursor = 'pointer';

    let docHtml = '<span class="muted" style="font-style:italic;">Sin documentos con fecha</span>';
    if (v.documentoUrgente) {
      const info = ETIQUETA_DOC_ESTADO[v.documentoUrgente.estado] || ETIQUETA_DOC_ESTADO.sin_fecha;
      const detalle = v.documentoUrgente.diasRestantes !== null
        ? (v.documentoUrgente.diasRestantes >= 0
            ? `vence en ${v.documentoUrgente.diasRestantes} día(s)`
            : `venció hace ${Math.abs(v.documentoUrgente.diasRestantes)} día(s)`)
        : '';
      docHtml = `<span class="badge ${info.clase}">${escapeHtml(v.documentoUrgente.tipo)}: ${info.texto}</span> <span class="muted">${detalle}</span>`;
    }

    item.innerHTML = `
      <div>
        <div class="name">
          ${escapeHtml(v.placa)}
          ${v.estado !== 'ACTIVO' ? `<span class="tag-inactivo">${escapeHtml(v.estado)}</span>` : ''}
        </div>
        <div class="meta">
          ${[v.marca, v.modelo, v.tipo].filter(Boolean).map(escapeHtml).join(' · ') || 'Sin datos de marca/modelo'}
          ${v.conductor ? ' · Conductor: ' + escapeHtml(v.conductor) : ''}
          · ${v.tipoAdquisicion === 'ALQUILER' ? 'Alquiler' : 'Propio'}
        </div>
        <div style="margin-top:6px;">${docHtml}</div>
      </div>
    `;

    item.addEventListener('click', () => {
      window.location.href = `/vehiculos/${v.id}`;
    });

    cont.appendChild(item);
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

cargarConductores();
cargarVehiculos();
