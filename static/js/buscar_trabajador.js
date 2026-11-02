const searchInput = document.getElementById('searchInput');
const resultList = document.getElementById('resultList');
const workerDetail = document.getElementById('workerDetail');

let debounceTimer = null;
let uploadRowCount = 0;
let ultimosResultados = [];
let tabActual = 'activos';
let tabFicha = 'datos';

const TABS_FICHA = [
  ['datos', 'Datos'],
  ['contrato', 'Contrato y renovaciones'],
  ['seguros', 'Seguros'],
  ['familia', 'Familia'],
  ['documentos', 'Documentos']
];

searchInput.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  const q = searchInput.value.trim();
  debounceTimer = setTimeout(() => doSearch(q), 180);
});

document.querySelectorAll('#tabsEstado a').forEach((tab) => {
  tab.addEventListener('click', (e) => {
    e.preventDefault();
    tabActual = tab.dataset.tab;
    document.querySelectorAll('#tabsEstado a').forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    renderResults(ultimosResultados);
  });
});

async function doSearch(q) {
  try {
    const res = await fetch(`/api/trabajadores/buscar?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    ultimosResultados = data.results || [];
    renderResults(ultimosResultados);
  } catch (err) {
    resultList.innerHTML = '<div class="empty-state">Error al buscar</div>';
  }
}

// Al entrar a la pagina, se muestra la lista completa de trabajadores de
// una vez (sin tener que escribir nada). Escribir en el buscador sigue
// filtrando esa misma lista.
doSearch('');

// Si se llega con ?id=123 en la URL (ej. desde el Resumen de personal),
// se abre directo la ficha de ese trabajador, sin tener que buscarlo.
const parametrosUrl = new URLSearchParams(window.location.search);
const idDesdeUrl = parametrosUrl.get('id');
if (TABS_FICHA.some(([id]) => id === parametrosUrl.get('tab'))) {
  tabFicha = parametrosUrl.get('tab');
}
if (idDesdeUrl) {
  loadDetail(Number(idDesdeUrl));
}

function renderResults(todosLosResultados) {
  const activos = todosLosResultados.filter((w) => w.estado !== 'INACTIVO');
  const inactivos = todosLosResultados.filter((w) => w.estado === 'INACTIVO');

  document.getElementById('contadorActivos').textContent = activos.length ? `(${activos.length})` : '';
  document.getElementById('contadorInactivos').textContent = inactivos.length ? `(${inactivos.length})` : '';

  const results = tabActual === 'inactivos' ? inactivos : activos;

  if (results.length === 0) {
    resultList.innerHTML = `<div class="empty-state">No se encontraron trabajadores ${tabActual === 'inactivos' ? 'inactivos' : 'activos'}</div>`;
    return;
  }

  resultList.innerHTML = '';
  results.forEach((w) => {
    const inactivo = w.estado === 'INACTIVO';
    const item = document.createElement('div');
    item.className = 'result-item';
    const inicial = (w.nombres || '?')[0].toUpperCase();
    const avatarHtml = w.tiene_foto
      ? `<img src="/foto/${w.id}" alt="">`
      : `<span>${inicial}</span>`;
    item.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;">
        <div class="avatar-trabajador-chico">${avatarHtml}</div>
        <div>
          <div class="name">
            ${escapeHtml(w.apellidos)} ${escapeHtml(w.nombres)}
            ${inactivo ? '<span class="tag-inactivo">Inactivo</span>' : ''}
            ${w.excluido_asistencia ? '<span class="tag-inactivo tag-info">Sin control asistencia</span>' : ''}
          </div>
          <div class="meta">DNI: ${escapeHtml(w.dni || '—')} ${w.cargo ? '· ' + escapeHtml(w.cargo) : ''}</div>
        </div>
      </div>
      <span class="tag">${w.area ? escapeHtml(w.area) : 'Ver detalle'}</span>
    `;
    item.addEventListener('click', () => loadDetail(w.id));
    resultList.appendChild(item);
  });
}

async function loadDetail(id, desplazar = true) {
  try {
    const res = await fetch(`/api/trabajadores/${id}`);
    const data = await res.json();
    if (!res.ok) return;
    renderDetail(data.worker, 'view');
    if (desplazar) workerDetail.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    // noop
  }
}

function renderDetail(w, mode) {
  if (mode === 'edit') {
    renderEditForm(w);
  } else {
    renderViewMode(w);
  }
}

function grupoDatosHtml(titulo, campos) {
  return `
    <section class="grupo-datos">
      <h3>${titulo}</h3>
      <div class="detail-grid">
        ${campos.map(([label, value]) => `
          <div class="detail-item">
            <div class="label">${label}</div>
            <div class="value">${escapeHtml(String(value))}</div>
          </div>`).join('')}
      </div>
    </section>`;
}

function textoTiempoRenovacion(tiempo, meses) {
  if (!tiempo) return '—';
  return tiempo === TIEMPO_OTRO ? `${meses} meses` : tiempo;
}

function contratoTarjetaHtml(w) {
  const opcionesTipo = ['Necesidad de mercado', CONTRATO_INDETERMINADO]
    .map((t) => `<option value="${t}" ${w.tipo_contrato === t ? 'selected' : ''}>${t}</option>`)
    .join('');
  const opcionesTiempo = ['3 meses', '6 meses', 'Anual', TIEMPO_OTRO]
    .map((t) => `<option value="${t}" ${w.tiempo_renovacion === t ? 'selected' : ''}>${t}</option>`)
    .join('');

  const historial = [...(w.historial_renovaciones || [])].reverse();
  const historialHtml = historial.length === 0 ? '' : `
    <details class="historial">
      <summary>Historial (${historial.length})</summary>
      <div class="tabla-scroll">
        <table>
          <thead>
            <tr><th>Tipo</th><th>Renovación cada</th><th>Fin anterior</th><th>Fin nuevo</th><th>Renovación</th><th>Registrado</th></tr>
          </thead>
          <tbody>
            ${historial.map((h) => `
              <tr>
                <td>${escapeHtml(h.tipoContrato || '—')}</td>
                <td>${escapeHtml(textoTiempoRenovacion(h.tiempoRenovacion, h.tiempoRenovacionMeses))}</td>
                <td>${escapeHtml(h.fechaAnterior || '—')}</td>
                <td>${escapeHtml(h.fechaNueva || '—')}</td>
                <td>${escapeHtml(h.fechaRenovacion || '—')}</td>
                <td>${escapeHtml((h.actualizado || '—').slice(0, 16).replace('T', ' '))}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </details>`;

  return `
    <div class="panel" id="contratoPanel">
      <h3>Actualizar contrato</h3>
      <p class="muted">Registra las condiciones y la nueva fecha de fin de contrato (por ejemplo, tras una renovación).</p>
      <div class="detail-grid detail-resumen">
        <div class="detail-item"><div class="label">Tipo de contrato</div><div class="value">${escapeHtml(w.tipo_contrato || '—')}</div></div>
        <div class="detail-item"><div class="label">Renovación cada</div><div class="value">${escapeHtml(textoTiempoRenovacion(w.tiempo_renovacion, w.tiempo_renovacion_meses))}</div></div>
        <div class="detail-item"><div class="label">Fin de contrato</div><div class="value">${escapeHtml(w.fecha_fin_contrato || '—')}</div></div>
        <div class="detail-item"><div class="label">Última renovación</div><div class="value">${escapeHtml(w.fecha_renovacion || '—')}</div></div>
      </div>
      <div class="success-msg" id="contratoSuccessMsg"></div>
      <div class="error-msg" id="contratoErrorMsg"></div>
      <form id="contratoForm">
        <div class="grid-2">
          <div class="field">
            <label for="contratoTipo">Tipo de contrato *</label>
            <select id="contratoTipo" required>
              <option value="">Selecciona...</option>
              ${opcionesTipo}
            </select>
          </div>
          <div class="field">
            <label for="contratoTiempo">Tiempo de renovación <span data-obligatorio>*</span></label>
            <select id="contratoTiempo">
              <option value="">Selecciona...</option>
              ${opcionesTiempo}
            </select>
          </div>
          <div class="field" id="contratoMesesCampo" hidden>
            <label for="contratoMeses">Cantidad de meses *</label>
            <input type="number" id="contratoMeses" min="1" max="${MAXIMO_MESES_RENOVACION}" step="1" value="${w.tiempo_renovacion === TIEMPO_OTRO ? w.tiempo_renovacion_meses : ''}">
          </div>
          <div class="field">
            <label for="nuevaFechaFinContrato">Nueva fecha de fin de contrato <span data-obligatorio>*</span></label>
            <input type="date" id="nuevaFechaFinContrato">
          </div>
          <div class="field">
            <label for="nuevaFechaRenovacion">Fecha de renovación</label>
            <input type="date" id="nuevaFechaRenovacion">
          </div>
        </div>
        <button type="submit" class="btn" id="contratoSubmitBtn">Guardar contrato</button>
      </form>
      ${historialHtml}
    </div>`;
}

function bindTabsFicha() {
  document.querySelectorAll('#fichaTabs button').forEach((boton) => {
    boton.addEventListener('click', () => {
      tabFicha = boton.dataset.tabFicha;
      mostrarTabFicha();
    });
  });
  mostrarTabFicha();
}

function mostrarTabFicha() {
  document.querySelectorAll('#fichaTabs button').forEach((boton) => {
    const activa = boton.dataset.tabFicha === tabFicha;
    boton.classList.toggle('active', activa);
    boton.setAttribute('aria-selected', activa);
  });
  document.querySelectorAll('[data-panel-ficha]').forEach((panel) => {
    panel.hidden = panel.dataset.panelFicha !== tabFicha;
  });
}

function renderViewMode(w) {
  const tieneConyuge = w.estado_civil === 'Casado/a' || w.estado_civil === 'Conviviente';

  const datosHtml = [
    grupoDatosHtml('Identificación', [
      ['Nombres', w.nombres],
      ['Apellidos', w.apellidos],
      ['DNI', w.dni || '—'],
      ['Fecha de nacimiento', w.fecha_nacimiento || '—'],
      ['Estado civil', w.estado_civil || '—'],
      ['Código de empleado', w.codigo_empleado || '— (no enrolado en el biométrico)']
    ]),
    grupoDatosHtml('Puesto', [
      ['Cargo', w.cargo || '—'],
      ['Área', w.area || '—'],
      ['Sede', w.sede_nombre || '—'],
      ['Supervisor', w.supervisor || '—'],
      ['Fecha de ingreso', w.fecha_ingreso || '—'],
      ['Sueldo neto', w.sueldo_neto != null ? formatearSueldo(w.sueldo_neto) : '—'],
      ['Horario', (w.hora_entrada || '08:00') + ' a ' + (w.hora_salida || '17:00') + (w.hora_entrada ? ' (personalizado)' : ' (estándar)')],
      ['Control de asistencias', w.excluido_asistencia ? 'Excluido (no se le calculan tardanzas/faltas)' : 'Normal']
    ]),
    grupoDatosHtml('Contacto', [
      ['Teléfono personal', w.telefono || '—'],
      ['Teléfono corporativo', w.telefono_corporativo || '—'],
      ['Correo personal', w.email || '—'],
      ['Correo corporativo', w.email_corporativo || '—'],
      ['Contacto de emergencia', w.contacto_emergencia_nombres ? `${w.contacto_emergencia_nombres} · ${w.contacto_emergencia_telefono || '—'} · ${w.contacto_emergencia_direccion || '—'}` : '—']
    ]),
    grupoDatosHtml('Dirección', [
      ['País', w.pais || '—'],
      ['Departamento', w.departamento || '—'],
      ['Provincia / Ciudad', w.provincia || '—'],
      ['Distrito', w.distrito || '—'],
      ['Dirección', w.direccion || '—']
    ]),
    w.observaciones ? grupoDatosHtml('Observaciones', [['Notas', w.observaciones]]) : ''
  ].join('');

  const carpetas = w.carpetas || [];
  const documentos = w.documentos || [];

  // Agrupamos los documentos por carpeta (los que no tienen carpeta van al
  // final, bajo "Sin carpeta").
  const grupos = {};
  documentos.forEach((d) => {
    const clave = d.carpeta || 'Sin carpeta';
    if (!grupos[clave]) grupos[clave] = [];
    grupos[clave].push(d);
  });

  const nombresGrupos = Object.keys(grupos).sort((a, b) => {
    if (a === 'Sin carpeta') return 1;
    if (b === 'Sin carpeta') return -1;
    return a.localeCompare(b);
  });

  const hijos = w.hijos || [];
  const hijosHtml = hijos.length === 0
    ? '<p class="muted">Todavía no se registró ningún hijo.</p>'
    : hijos.map((h) => `
        <div class="doc-item">
          <div>
            <div class="doc-name">${escapeHtml(h.nombres_completos)}</div>
            <div class="muted">
              ${h.dni ? 'DNI: ' + escapeHtml(h.dni) : 'Sin DNI'} · ${h.fecha_nacimiento ? h.fecha_nacimiento : 'Sin fecha de nacimiento'}
            </div>
          </div>
          <button class="btn danger sm" onclick="eliminarHijo(${w.id}, ${h.id})">Quitar</button>
        </div>`).join('');

  const docsHtml =
    documentos.length === 0
      ? '<p class="muted">Este trabajador no tiene documentos cargados.</p>'
      : nombresGrupos
          .map((nombreGrupo) => `
        <div class="carpeta-grupo">
          <div class="carpeta-titulo">${escapeHtml(nombreGrupo)}</div>
          <div class="doc-list">
            ${grupos[nombreGrupo]
              .map((d) => `
              <div class="doc-item">
                <div class="doc-name">${escapeHtml(d.nombre)}</div>
                <div class="doc-actions">
                  <button class="btn secondary" onclick="togglePdfPreview(${d.id}, '/documentos/${d.id}')">Vista previa</button>
                  <a class="btn secondary" href="/documentos/${d.id}" target="_blank">Abrir</a>
                  <button class="btn danger" onclick="eliminarDocumento(${w.id}, ${d.id})">Eliminar</button>
                </div>
              </div>`)
              .join('')}
          </div>
        </div>`)
          .join('');

  const inicial = (w.nombres || '?')[0].toUpperCase();
  const avatarHtml = w.tiene_foto
    ? `<img src="/foto/${w.id}?v=${Date.now()}" alt="">`
    : `<span>${inicial}</span>`;

  const examenVigente = (w.renovaciones || []).find((r) => r.tipo === 'EMO');
  const metaPuesto = [w.cargo, w.area, w.sede_nombre].filter(Boolean).map(escapeHtml).join(' · ');

  workerDetail.innerHTML = `
    <div class="ficha-cabecera">
      <div class="ficha-identidad">
        <div class="avatar-trabajador" id="avatarFicha">${avatarHtml}</div>
        <div>
          <h2>
            ${escapeHtml(w.apellidos)} ${escapeHtml(w.nombres)}
            ${w.estado === 'INACTIVO' ? '<span class="tag-inactivo">Inactivo</span>' : ''}
          </h2>
          <div class="muted">${metaPuesto || 'Sin cargo asignado'} · DNI ${escapeHtml(w.dni || '—')}</div>
          <div class="ficha-acciones-foto">
            <label class="btn secondary sm">
              ${w.tiene_foto ? 'Cambiar foto' : 'Agregar foto'}
              <input type="file" id="inputFoto" accept="image/jpeg,image/png,image/webp" hidden>
            </label>
            ${w.tiene_foto ? '<button type="button" class="btn danger sm" id="quitarFotoBtn">Quitar foto</button>' : ''}
          </div>
        </div>
      </div>
      <button class="btn secondary" id="editWorkerBtn">Editar información</button>
    </div>

    <div class="ficha-tabs" id="fichaTabs" role="tablist">
      ${TABS_FICHA.map(([id, nombre]) => `<button type="button" role="tab" data-tab-ficha="${id}">${nombre}</button>`).join('')}
    </div>

    <div data-panel-ficha="datos">
      <div class="panel">${datosHtml}</div>
    </div>

    <div data-panel-ficha="contrato">
      <div class="ficha-tarjetas">
        ${contratoTarjetaHtml(w)}
        ${tarjetasRenovacionHtml(w)}
      </div>
    </div>

    <div data-panel-ficha="seguros">
      ${segurosSeccionHtml(w)}
    </div>

    <div data-panel-ficha="familia">
      <div class="panel">
        ${grupoDatosHtml('Familia', [
          ['Cónyuge', tieneConyuge ? (w.conyuge_nombres ? `${w.conyuge_nombres} (DNI: ${w.conyuge_dni || '—'})` : '—') : 'No aplica'],
          ['¿Tiene hijos?', w.tiene_hijos ? `Sí (${hijos.length})` : 'No']
        ])}
        <h3>Hijos</h3>
        <div id="hijosListaArea" class="doc-list">${hijosHtml}</div>
        <div class="fila-form">
          <input type="text" id="nuevoHijoNombres" placeholder="Nombres completos" aria-label="Nombres completos">
          <input type="text" id="nuevoHijoDni" placeholder="DNI (opcional)" aria-label="DNI">
          <input type="date" id="nuevoHijoFecha" aria-label="Fecha de nacimiento">
          <button type="button" class="btn secondary" id="agregarHijoBtn">+ Agregar hijo</button>
        </div>
      </div>
    </div>

    <div data-panel-ficha="documentos">
      <div class="panel">
        <h3>Examen médico (EMO)</h3>
        <div class="estado-lista">
          <div class="estado-fila">
            <span>${examenVigente ? `Vence: ${examenVigente.fecha_proxima}` : 'Sin fecha de vencimiento registrada'}</span>
            <span class="estado-acciones">
              ${examenVigente ? badgeVencimiento(examenVigente.fecha_proxima) : ''}
              <button type="button" class="btn secondary sm" id="irExamenBtn">${examenVigente ? 'Actualizar fecha' : 'Registrar fecha'}</button>
            </span>
          </div>
        </div>

        <h3>Documentos</h3>
        ${docsHtml}
        <div id="pdfPreviewArea"></div>

        <h3>Carpetas</h3>
        <p class="muted">Organiza los documentos de este trabajador en carpetas (ej. "DNI", "Contratos", "Certificados").</p>
        <div class="error-msg" id="carpetaErrorMsg"></div>
        <div class="fila-form">
          <input type="text" id="nuevaCarpetaInput" placeholder="Nombre de la nueva carpeta" aria-label="Nombre de la nueva carpeta">
          <button type="button" class="btn secondary" id="crearCarpetaBtn">+ Crear carpeta</button>
        </div>

        <h3>Agregar más documentos</h3>
        <div id="uploadRows"></div>
        <button type="button" class="btn secondary" id="addUploadRowBtn">+ Agregar documento PDF</button>
        <div class="acciones-form">
          <button type="button" class="btn" id="subirDocsBtn">Subir documentos</button>
        </div>
        <div class="error-msg" id="uploadErrorMsg"></div>
      </div>
    </div>
  `;

  document.getElementById('editWorkerBtn').addEventListener('click', () => renderEditForm(w));
  bindTabsFicha();
  document.getElementById('irExamenBtn').addEventListener('click', () => {
    tabFicha = 'contrato';
    mostrarTabFicha();
    document.querySelector('form[data-renovacion="EMO"]').scrollIntoView({ behavior: 'smooth', block: 'center' });
    document.getElementById('renovacionFechaEMO').focus({ preventScroll: true });
  });
  bindContratoForm(w.id);
  bindRenovaciones(w);
  bindSeguros(w);
  bindCarpetas(w);
  bindUploadDocs(w);
  bindFoto(w);
  bindHijos(w);
}

function bindHijos(w) {
  const btn = document.getElementById('agregarHijoBtn');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    const nombresCompletos = document.getElementById('nuevoHijoNombres').value.trim();
    const dni = document.getElementById('nuevoHijoDni').value.trim();
    const fechaNacimiento = document.getElementById('nuevoHijoFecha').value;

    if (!nombresCompletos) {
      alert('Escribe el nombre completo del hijo.');
      return;
    }

    try {
      const res = await fetch(`/api/trabajadores/${w.id}/hijos`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombresCompletos, dni, fechaNacimiento })
      });
      const data = await res.json();

      if (!res.ok) {
        alert(data.error || 'No se pudo agregar el hijo');
        return;
      }

      loadDetail(w.id);
    } catch (err) {
      alert('Error de conexión con el servidor');
    }
  });
}

async function eliminarHijo(workerId, hijoId) {
  if (!confirm('¿Quitar este hijo de la ficha?')) return;
  try {
    const res = await fetch(`/api/trabajadores/hijos/${hijoId}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo quitar el registro');
      return;
    }
    loadDetail(workerId);
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

function bindFoto(w) {
  const inputFoto = document.getElementById('inputFoto');
  inputFoto.addEventListener('change', async () => {
    const file = inputFoto.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('foto', file);

    try {
      const res = await fetch(`/api/trabajadores/${w.id}/foto`, { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) {
        alert(data.error || 'No se pudo subir la foto');
        return;
      }
      loadDetail(w.id);
    } catch (err) {
      alert('Error de conexión con el servidor');
    }
  });

  const quitarBtn = document.getElementById('quitarFotoBtn');
  if (quitarBtn) {
    quitarBtn.addEventListener('click', async () => {
      if (!confirm('¿Quitar la foto de perfil de este trabajador?')) return;
      try {
        const res = await fetch(`/api/trabajadores/${w.id}/foto`, { method: 'DELETE' });
        if (!res.ok) {
          alert('No se pudo quitar la foto');
          return;
        }
        loadDetail(w.id);
      } catch (err) {
        alert('Error de conexión con el servidor');
      }
    });
  }
}

function renderEditForm(w) {
  workerDetail.innerHTML = `
    <div class="panel">
      <h2>Editar información</h2>
      <div class="error-msg" id="editErrorMsg"></div>
      <form id="editForm">
        <div class="grid-2">
          <div class="field">
            <label for="editNombres">Nombres *</label>
            <input type="text" id="editNombres" value="${escapeAttr(w.nombres)}" required>
          </div>
          <div class="field">
            <label for="editApellidos">Apellidos *</label>
            <input type="text" id="editApellidos" value="${escapeAttr(w.apellidos)}" required>
          </div>
          <div class="field">
            <label for="editDni">DNI *</label>
            <input type="text" id="editDni" value="${escapeAttr(w.dni || '')}" required>
          </div>
          <div class="field">
            <label for="editEstado">Estado</label>
            <select id="editEstado">
              <option value="ACTIVO" ${w.estado !== 'INACTIVO' ? 'selected' : ''}>Activo</option>
              <option value="INACTIVO" ${w.estado === 'INACTIVO' ? 'selected' : ''}>Inactivo</option>
            </select>
          </div>
          <div class="field">
            <label for="editTelefono">Teléfono personal</label>
            <input type="text" id="editTelefono" value="${escapeAttr(w.telefono || '')}">
          </div>
          <div class="field">
            <label for="editTelefonoCorporativo">Teléfono corporativo</label>
            <input type="text" id="editTelefonoCorporativo" value="${escapeAttr(w.telefono_corporativo || '')}">
          </div>
          <div class="field">
            <label for="editEmail">Correo personal</label>
            <input type="email" id="editEmail" value="${escapeAttr(w.email || '')}">
          </div>
          <div class="field">
            <label for="editEmailCorporativo">Correo corporativo</label>
            <input type="email" id="editEmailCorporativo" value="${escapeAttr(w.email_corporativo || '')}">
          </div>
          <div class="field">
            <label for="editFechaIngreso">Fecha de ingreso</label>
            <input type="date" id="editFechaIngreso" value="${w.fecha_ingreso || ''}">
          </div>
          <div class="field">
            <label for="editFechaNacimiento">Fecha de nacimiento</label>
            <input type="date" id="editFechaNacimiento" value="${w.fecha_nacimiento || ''}">
          </div>
          <div class="field">
            <label for="editEstadoCivil">Estado civil</label>
            <select id="editEstadoCivil">
              <option value="" ${!w.estado_civil ? 'selected' : ''}>Sin especificar</option>
              <option value="Soltero/a" ${w.estado_civil === 'Soltero/a' ? 'selected' : ''}>Soltero/a</option>
              <option value="Casado/a" ${w.estado_civil === 'Casado/a' ? 'selected' : ''}>Casado/a</option>
              <option value="Conviviente" ${w.estado_civil === 'Conviviente' ? 'selected' : ''}>Conviviente</option>
              <option value="Divorciado/a" ${w.estado_civil === 'Divorciado/a' ? 'selected' : ''}>Divorciado/a</option>
              <option value="Viudo/a" ${w.estado_civil === 'Viudo/a' ? 'selected' : ''}>Viudo/a</option>
            </select>
          </div>
          <div class="field" style="display:flex;align-items:flex-end;">
            <label style="display:flex;align-items:center;gap:8px;font-weight:400;margin-bottom:10px;">
              <input type="checkbox" id="editTieneHijos" ${w.tiene_hijos ? 'checked' : ''}>
              ¿Tiene hijos? <span class="muted">(gestiona la lista desde la ficha)</span>
            </label>
          </div>
        </div>

        <div id="editConyugeCampos" class="grid-2" style="${(w.estado_civil === 'Casado/a' || w.estado_civil === 'Conviviente') ? '' : 'display:none;'}">
          <div class="field">
            <label for="editConyugeNombres">Nombres completos del cónyuge</label>
            <input type="text" id="editConyugeNombres" value="${escapeAttr(w.conyuge_nombres || '')}">
          </div>
          <div class="field">
            <label for="editConyugeDni">DNI del cónyuge</label>
            <input type="text" id="editConyugeDni" value="${escapeAttr(w.conyuge_dni || '')}">
          </div>
        </div>

        <h3>Contacto de emergencia</h3>
        <div class="grid-2">
          <div class="field">
            <label for="editContactoEmergenciaNombres">Nombres</label>
            <input type="text" id="editContactoEmergenciaNombres" value="${escapeAttr(w.contacto_emergencia_nombres || '')}">
          </div>
          <div class="field">
            <label for="editContactoEmergenciaTelefono">Teléfono</label>
            <input type="text" id="editContactoEmergenciaTelefono" value="${escapeAttr(w.contacto_emergencia_telefono || '')}">
          </div>
        </div>
        <div class="field">
          <label for="editContactoEmergenciaDireccion">Dirección</label>
          <input type="text" id="editContactoEmergenciaDireccion" value="${escapeAttr(w.contacto_emergencia_direccion || '')}">
        </div>

        <div class="grid-2">
          <div class="field">
            <label for="editHoraEntrada">Hora de entrada (dejar vacío = 08:00 estándar)</label>
            <input type="time" id="editHoraEntrada" value="${w.hora_entrada || ''}">
          </div>
          <div class="field">
            <label for="editHoraSalida">Hora de salida (dejar vacío = 17:00 estándar)</label>
            <input type="time" id="editHoraSalida" value="${w.hora_salida || ''}">
          </div>
          <div class="field">
            <label for="editCargo">Cargo</label>
            <input type="text" id="editCargo" value="${escapeAttr(w.cargo || '')}">
          </div>
          <div class="field">
            <label for="editArea">Área / Departamento</label>
            <input type="text" id="editArea" value="${escapeAttr(w.area || '')}">
          </div>
          <div class="field">
            <label for="editSedeId">Sede</label>
            <div style="display:flex;gap:8px;">
              <select id="editSedeId" style="flex:1;">
                <option value="">Sin asignar</option>
              </select>
              <button type="button" class="btn secondary" id="nuevaSedeBtn" style="white-space:nowrap;">+ Nueva</button>
            </div>
          </div>
          <div class="field" style="display:flex;flex-direction:column;justify-content:flex-end;">
            <label style="display:flex;align-items:center;gap:8px;font-weight:400;margin-bottom:2px;">
              <input type="checkbox" id="editExcluidoAsistencia" ${w.excluido_asistencia ? 'checked' : ''}>
              Excluir de control de asistencias (ej. jefatura, gerencia)
            </label>
            <span class="muted">Su marcaje se sigue registrando igual, solo no se le calculan tardanzas, descuentos ni faltas.</span>
          </div>
          <div class="field">
            <label for="editSupervisor">Supervisor</label>
            <input type="text" id="editSupervisor" value="${escapeAttr(w.supervisor || '')}">
          </div>
          <div class="field">
            <label for="editSueldoNeto">Sueldo neto (S/)</label>
            <input type="number" id="editSueldoNeto" value="${w.sueldo_neto != null ? w.sueldo_neto : ''}" step="0.01" min="0">
          </div>
        </div>

        <h3>Dirección</h3>
        <div class="grid-2">
          <div class="field">
            <label for="editPais">País</label>
            <input type="text" id="editPais" value="${escapeAttr(w.pais || '')}">
          </div>
          <div class="field">
            <label for="editDepartamento">Departamento</label>
            <input type="text" id="editDepartamento" value="${escapeAttr(w.departamento || '')}">
          </div>
          <div class="field">
            <label for="editProvincia">Provincia / Ciudad</label>
            <input type="text" id="editProvincia" value="${escapeAttr(w.provincia || '')}">
          </div>
          <div class="field">
            <label for="editDistrito">Distrito</label>
            <input type="text" id="editDistrito" value="${escapeAttr(w.distrito || '')}">
          </div>
        </div>
        <div class="field">
          <label for="editDireccion">Dirección (calle, número, referencia)</label>
          <input type="text" id="editDireccion" value="${escapeAttr(w.direccion || '')}">
        </div>
        <div class="field">
          <label for="editObservaciones">Observaciones</label>
          <textarea id="editObservaciones" rows="3">${escapeHtml(w.observaciones || '')}</textarea>
        </div>
        <div style="display:flex;gap:10px;">
          <button type="submit" class="btn" id="editSubmitBtn">Guardar cambios</button>
          <button type="button" class="btn secondary" id="editCancelBtn">Cancelar</button>
        </div>
      </form>
    </div>
  `;

  document.getElementById('editCancelBtn').addEventListener('click', () => renderViewMode(w));

  cargarSedesEnEdicion(w.sede_id);
  bindNuevaSedeModal();

  document.getElementById('editEstadoCivil').addEventListener('change', (e) => {
    const mostrar = e.target.value === 'Casado/a' || e.target.value === 'Conviviente';
    document.getElementById('editConyugeCampos').style.display = mostrar ? 'grid' : 'none';
  });

  document.getElementById('editForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorMsg = document.getElementById('editErrorMsg');
    errorMsg.style.display = 'none';

    const payload = {
      nombres: document.getElementById('editNombres').value.trim(),
      apellidos: document.getElementById('editApellidos').value.trim(),
      dni: document.getElementById('editDni').value.trim(),
      estado: document.getElementById('editEstado').value,
      telefono: document.getElementById('editTelefono').value.trim(),
      email: document.getElementById('editEmail').value.trim(),
      emailCorporativo: document.getElementById('editEmailCorporativo').value.trim(),
      fechaIngreso: document.getElementById('editFechaIngreso').value,
      fechaNacimiento: document.getElementById('editFechaNacimiento').value,
      telefonoCorporativo: document.getElementById('editTelefonoCorporativo').value.trim(),
      estadoCivil: document.getElementById('editEstadoCivil').value,
      tieneHijos: document.getElementById('editTieneHijos').checked,
      conyugeNombres: document.getElementById('editConyugeNombres').value.trim(),
      conyugeDni: document.getElementById('editConyugeDni').value.trim(),
      contactoEmergenciaNombres: document.getElementById('editContactoEmergenciaNombres').value.trim(),
      contactoEmergenciaTelefono: document.getElementById('editContactoEmergenciaTelefono').value.trim(),
      contactoEmergenciaDireccion: document.getElementById('editContactoEmergenciaDireccion').value.trim(),
      horaEntrada: document.getElementById('editHoraEntrada').value,
      horaSalida: document.getElementById('editHoraSalida').value,
      cargo: document.getElementById('editCargo').value.trim(),
      area: document.getElementById('editArea').value.trim(),
      sedeId: document.getElementById('editSedeId').value,
      excluidoAsistencia: document.getElementById('editExcluidoAsistencia').checked,
      supervisor: document.getElementById('editSupervisor').value.trim(),
      sueldoNeto: document.getElementById('editSueldoNeto').value,
      pais: document.getElementById('editPais').value.trim(),
      departamento: document.getElementById('editDepartamento').value.trim(),
      provincia: document.getElementById('editProvincia').value.trim(),
      distrito: document.getElementById('editDistrito').value.trim(),
      direccion: document.getElementById('editDireccion').value.trim(),
      observaciones: document.getElementById('editObservaciones').value.trim()
    };

    const submitBtn = document.getElementById('editSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Guardando...';

    try {
      const res = await fetch(`/api/trabajadores/${w.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo actualizar el trabajador';
        errorMsg.style.display = 'block';
        return;
      }

      renderViewMode(data.worker);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Guardar cambios';
    }
  });
}

function bindContratoForm(workerId) {
  const form = document.getElementById('contratoForm');
  if (!form) return;

  const campos = {
    tipo: document.getElementById('contratoTipo'),
    tiempo: document.getElementById('contratoTiempo'),
    meses: document.getElementById('contratoMeses'),
    mesesCampo: document.getElementById('contratoMesesCampo'),
    fechaFin: document.getElementById('nuevaFechaFinContrato'),
    raiz: form
  };
  enlazarCamposContrato(campos);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const successMsg = document.getElementById('contratoSuccessMsg');
    const errorMsg = document.getElementById('contratoErrorMsg');
    successMsg.style.display = 'none';
    errorMsg.style.display = 'none';

    const error = errorDeContrato(campos, true);
    if (error) {
      errorMsg.textContent = error;
      errorMsg.style.display = 'block';
      return;
    }

    const submitBtn = document.getElementById('contratoSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Guardando...';

    try {
      const res = await fetch(`/api/trabajadores/${workerId}/contrato`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipoContrato: campos.tipo.value,
          tiempoRenovacion: campos.tiempo.value,
          tiempoRenovacionMeses: campos.meses.value,
          fechaFinContrato: campos.fechaFin.value,
          fechaRenovacion: document.getElementById('nuevaFechaRenovacion').value
        })
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo actualizar el contrato';
        errorMsg.style.display = 'block';
        return;
      }

      renderViewMode(data.worker);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Guardar contrato';
    }
  });
}

// ---------- Carpetas ----------

function bindCarpetas(w) {
  const btn = document.getElementById('crearCarpetaBtn');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    const errorMsg = document.getElementById('carpetaErrorMsg');
    errorMsg.style.display = 'none';

    const input = document.getElementById('nuevaCarpetaInput');
    const nombre = input.value.trim();

    if (!nombre) {
      errorMsg.textContent = 'Escribe un nombre para la carpeta';
      errorMsg.style.display = 'block';
      return;
    }

    btn.disabled = true;
    btn.textContent = 'Creando...';

    try {
      const res = await fetch(`/api/trabajadores/${w.id}/carpetas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre })
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo crear la carpeta';
        errorMsg.style.display = 'block';
        return;
      }

      loadDetail(w.id);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.textContent = '+ Crear carpeta';
    }
  });
}

// ---------- Subir documentos ----------

function bindUploadDocs(w) {
  const addBtn = document.getElementById('addUploadRowBtn');
  const uploadRows = document.getElementById('uploadRows');
  if (!addBtn || !uploadRows) return;

  const carpetas = w.carpetas || [];

  uploadRows.innerHTML = '';
  addUploadRow(carpetas);

  addBtn.addEventListener('click', () => addUploadRow(carpetas));

  document.getElementById('subirDocsBtn').addEventListener('click', async () => {
    const errorMsg = document.getElementById('uploadErrorMsg');
    errorMsg.style.display = 'none';

    const rows = document.querySelectorAll('#uploadRows .upload-row');
    const formData = new FormData();
    const nombres = [];
    const carpetasIds = [];
    let hayArchivos = false;

    rows.forEach((row) => {
      const fileInput = row.querySelector('.doc-file-input');
      const labelInput = row.querySelector('.doc-label-input');
      const carpetaSelect = row.querySelector('.doc-carpeta-select');
      const file = fileInput.files[0];
      if (file) {
        formData.append('documentos', file);
        nombres.push(labelInput.value.trim() || file.name);
        carpetasIds.push(carpetaSelect.value ? Number(carpetaSelect.value) : null);
        hayArchivos = true;
      }
    });
    formData.append('documentosNombres', JSON.stringify(nombres));
    formData.append('carpetasIds', JSON.stringify(carpetasIds));

    if (!hayArchivos) {
      errorMsg.textContent = 'Elige al menos un archivo PDF';
      errorMsg.style.display = 'block';
      return;
    }

    const btn = document.getElementById('subirDocsBtn');
    btn.disabled = true;
    btn.textContent = 'Subiendo...';

    try {
      const res = await fetch(`/api/trabajadores/${w.id}/documentos`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudieron subir los documentos';
        errorMsg.style.display = 'block';
        return;
      }

      renderViewMode(data.worker);
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Subir documentos';
    }
  });
}

function addUploadRow(carpetas) {
  uploadRowCount += 1;
  const rowId = `uprow_${uploadRowCount}`;

  const opcionesCarpetas = (carpetas || [])
    .map((c) => `<option value="${c.id}">${escapeHtml(c.nombre)}</option>`)
    .join('');

  const wrapper = document.createElement('div');
  wrapper.className = 'upload-row';
  wrapper.dataset.rowId = rowId;

  wrapper.innerHTML = `
    <input type="text" placeholder="Nombre del documento (ej. DNI, Contrato)" class="doc-label-input">
    <select class="doc-carpeta-select" title="Carpeta (opcional)">
      <option value="">Sin carpeta</option>
      ${opcionesCarpetas}
    </select>
    <label class="btn secondary" style="cursor:pointer;">
      Elegir PDF
      <input type="file" accept="application/pdf" class="doc-file-input" style="display:none;">
    </label>
    <span class="file-name">Ningún archivo seleccionado</span>
    <button type="button" class="btn danger remove-row-btn">Quitar</button>
  `;

  const fileInput = wrapper.querySelector('.doc-file-input');
  const fileNameSpan = wrapper.querySelector('.file-name');
  const labelInput = wrapper.querySelector('.doc-label-input');
  const removeBtn = wrapper.querySelector('.remove-row-btn');

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    fileNameSpan.textContent = file ? file.name : 'Ningún archivo seleccionado';
    if (file && !labelInput.value.trim()) {
      labelInput.value = file.name.replace(/\.pdf$/i, '');
    }
  });

  removeBtn.addEventListener('click', () => wrapper.remove());

  document.getElementById('uploadRows').appendChild(wrapper);
}

async function eliminarDocumento(workerId, docId) {
  if (!confirm('¿Eliminar este documento? Esta acción no se puede deshacer.')) return;

  try {
    const res = await fetch(`/api/trabajadores/${workerId}/documentos/${docId}`, {
      method: 'DELETE'
    });
    if (!res.ok) {
      alert('No se pudo eliminar el documento');
      return;
    }
    loadDetail(workerId);
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
}

function togglePdfPreview(docId, url) {
  const area = document.getElementById('pdfPreviewArea');
  const existingId = `pdf_prev_${docId}`;
  const existing = document.getElementById(existingId);
  if (existing) {
    existing.remove();
    return;
  }
  area.innerHTML = '';
  const div = document.createElement('div');
  div.className = 'pdf-preview-wrap';
  div.id = existingId;
  div.innerHTML = `<iframe src="${url}"></iframe>`;
  area.appendChild(div);
}

function formatearSueldo(monto) {
  const numero = Number(monto);
  if (Number.isNaN(numero)) return '—';
  return 'S/ ' + numero.toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ---------- Sedes ----------

async function cargarSedesEnEdicion(sedeIdActual) {
  const select = document.getElementById('editSedeId');
  if (!select) return;
  try {
    const res = await fetch('/api/sedes');
    const data = await res.json();
    select.innerHTML = '<option value="">Sin asignar</option>';
    (data.sedes || []).forEach((s) => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = s.nombre;
      select.appendChild(opt);
    });
    if (sedeIdActual) select.value = sedeIdActual;
  } catch (err) {
    // si falla, se queda solo la opcion "Sin asignar"
  }
}

function bindNuevaSedeModal() {
  const overlay = document.getElementById('nuevaSedeModalOverlay');
  const btnAbrir = document.getElementById('nuevaSedeBtn');
  if (!overlay || !btnAbrir) return;

  btnAbrir.addEventListener('click', () => {
    document.getElementById('nuevaSedeErrorMsg').style.display = 'none';
    document.getElementById('nuevaSedeNombre').value = '';
    document.getElementById('nuevaSedeAlerta').checked = false;
    overlay.style.display = 'flex';
  });

  document.getElementById('nuevaSedeCancelarBtn').addEventListener('click', () => {
    overlay.style.display = 'none';
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.style.display = 'none';
  });

  document.getElementById('nuevaSedeGuardarBtn').addEventListener('click', async () => {
    const errorMsg = document.getElementById('nuevaSedeErrorMsg');
    errorMsg.style.display = 'none';

    const nombre = document.getElementById('nuevaSedeNombre').value.trim();
    const alertaInasistencia = document.getElementById('nuevaSedeAlerta').checked;

    if (!nombre) {
      errorMsg.textContent = 'Escribe el nombre de la sede.';
      errorMsg.style.display = 'block';
      return;
    }

    try {
      const res = await fetch('/api/sedes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre, alertaInasistencia })
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo crear la sede';
        errorMsg.style.display = 'block';
        return;
      }

      await cargarSedesEnEdicion(data.id);
      overlay.style.display = 'none';
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    }
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, '&quot;');
}
