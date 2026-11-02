let contratoActual = null;
let adendaEditandoId = null;

async function cargarContrato() {
  try {
    const res = await fetch(`/api/contratos/${CONTRATO_ID}`);
    const data = await res.json();
    contratoActual = data.contrato;
    renderContrato(data.contrato, data.adendas);
  } catch (err) {
    document.getElementById('contratoDetalle').innerHTML = '<div class="empty-state">Error al cargar</div>';
  }
}

function campoFicha(etiqueta, valorHtml) {
  return `
    <div class="detail-item">
      <div class="label">${etiqueta}</div>
      <div class="value">${valorHtml}</div>
    </div>
  `;
}

function adendaFilaHtml(a, cerrado) {
  return `
    <div class="seguro-item">
      <div class="seguro-cabecera">
        <div>
          <div class="seguro-tipo">${escapeHtml(a.tipo)} N.º ${a.numero} ${badgeAdenda(a.formalizada)}</div>
          <div class="muted">
            ${a.nuevoFin ? `Nuevo fin: ${a.nuevoFin} · ` : ''}Firma: ${a.fechaSuscripcion || 'pendiente'}
          </div>
        </div>
        <div class="doc-actions">
          ${a.tieneDocumento
            ? `<a class="btn secondary sm" href="/documentos-adenda/${a.id}" target="_blank">Ver PDF</a>`
            : (cerrado ? '' : `
              <label class="btn secondary sm">
                Subir PDF
                <input type="file" accept="application/pdf" data-adenda-pdf="${a.id}" hidden>
              </label>`)}
          ${cerrado ? '' : `
            <button type="button" class="btn secondary sm" data-adenda-editar="${a.id}">Editar</button>
            <button type="button" class="btn danger sm" data-adenda-eliminar="${a.id}">Eliminar</button>`}
        </div>
      </div>
      <p class="texto-largo">${escapeHtml(a.descripcion)}</p>
    </div>
  `;
}

function renderContrato(c, adendas) {
  const cerrado = c.estado === 'finalizado';
  const ampliado = c.finEfectivo !== c.finVigencia;

  document.getElementById('contratoDetalle').innerHTML = `
    <div class="panel ficha-contrato">
      <div class="panel-cabecera">
        <div>
          <h1>${escapeHtml(c.numero)} ${badgeContrato(c.estado)}</h1>
          <p class="muted">${escapeHtml(c.moduloNombre)} · ${escapeHtml(c.categoria)}${c.diasRestantes !== null ? ` · ${textoDias(c.diasRestantes)}` : ''}</p>
        </div>
        <div class="doc-actions">
          ${cerrado
            ? '<button type="button" class="btn secondary" id="reabrirBtn">Reabrir</button>'
            : `<button type="button" class="btn secondary" id="editarContratoBtn">Editar</button>
               <button type="button" class="btn secondary" id="finalizarBtn">Finalizar</button>`}
          <button type="button" class="btn danger" id="eliminarContratoBtn">Eliminar</button>
        </div>
      </div>

      <div class="detail-grid">
        ${campoFicha('Empresa / contraparte', escapeHtml(c.contraparteNombre))}
        ${campoFicha('RUC', escapeHtml(c.contraparteRuc || '—'))}
        ${campoFicha('Responsable interno', escapeHtml(c.responsable))}
        ${campoFicha('Importe', textoImporte(c.importe, c.moneda))}
        ${campoFicha('Fecha de suscripción', c.fechaSuscripcion || 'Sin firma')}
        ${campoFicha('Inicio de vigencia', c.inicioVigencia)}
        ${campoFicha('Fin de vigencia', `${c.finEfectivo || 'Sin fecha'}${ampliado ? ` <span class="muted">(original: ${c.finVigencia || 'sin fecha'})</span>` : ''}`)}
        ${c.trabajadorId ? campoFicha('Colaborador', `<a href="/buscar-trabajador?id=${c.trabajadorId}">Ver ficha</a>`) : ''}
      </div>
      <div class="grupo-texto">
        <div class="detail-item"><div class="label">Objeto del contrato</div><div class="value texto-largo">${escapeHtml(c.objeto)}</div></div>
      </div>
      ${cerrado ? `
        <div class="grupo-texto">
          <div class="detail-item">
            <div class="label">Cierre</div>
            <div class="value texto-largo">${c.fechaCierre}${c.cerradoPor ? ` · ${escapeHtml(c.cerradoPor)}` : ''}${c.motivoCierre ? ` · ${escapeHtml(c.motivoCierre)}` : ''}</div>
          </div>
        </div>` : ''}

      <div class="estado-lista">
        <div class="estado-fila">
          <span>Contrato firmado (PDF)${c.tieneDocumento ? ` · ${escapeHtml(c.documentoNombre)}` : ' · pendiente'}</span>
          <span class="estado-acciones">
            ${c.tieneDocumento ? `<a class="btn secondary sm" href="/documentos-contrato/${c.id}" target="_blank">Ver PDF</a>` : ''}
            <label class="btn secondary sm">
              ${c.tieneDocumento ? 'Reemplazar PDF' : 'Subir PDF'}
              <input type="file" accept="application/pdf" id="contratoPdfInput" hidden>
            </label>
          </span>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-cabecera">
        <div>
          <h3>Renovaciones y adendas</h3>
          <p class="muted">Una adenda cambia la vigencia solo cuando tiene fecha de firma y PDF.</p>
        </div>
        ${cerrado ? '' : '<button type="button" class="btn" id="nuevaAdendaBtn">+ Nueva adenda</button>'}
      </div>
      ${adendas.length
        ? `<div class="seguros-lista">${adendas.map((a) => adendaFilaHtml(a, cerrado)).join('')}</div>`
        : '<div class="empty-state">Este contrato no tiene adendas.</div>'}
    </div>
  `;

  bindAccionesContrato(c, adendas, cerrado);
}

function bindAccionesContrato(c, adendas, cerrado) {
  const accion = (fn) => async () => {
    try {
      await fn();
      cargarContrato();
    } catch (err) {
      alert(err.message);
    }
  };

  document.getElementById('eliminarContratoBtn').addEventListener('click', async () => {
    if (!confirm(`¿Eliminar ${c.numero}, sus adendas y sus PDF? Esta acción no se puede deshacer.`)) return;
    const res = await fetch(`/api/contratos/${c.id}`, { method: 'DELETE' });
    if (res.ok) window.location.href = `/contratos/modulo/${c.modulo}`;
    else alert('No se pudo eliminar el contrato');
  });

  document.getElementById('contratoPdfInput').addEventListener('change', async (e) => {
    const archivo = e.target.files[0];
    if (!archivo) return;
    const error = errorDeArchivoPdf(archivo) || await subirPdf(`/api/contratos/${c.id}/documento`, archivo);
    if (error) alert(error);
    cargarContrato();
  });

  if (cerrado) {
    document.getElementById('reabrirBtn').addEventListener('click', accion(async () => {
      await enviarJson(`/api/contratos/${c.id}/reabrir`, 'POST');
    }));
    return;
  }

  document.getElementById('editarContratoBtn').addEventListener('click', () => {
    abrirFormularioContrato({ modulo: c.modulo, contrato: c, alGuardar: cargarContrato });
  });

  document.getElementById('finalizarBtn').addEventListener('click', () => {
    document.getElementById('cierreError').style.display = 'none';
    document.getElementById('cierreFecha').value = hoyIso();
    document.getElementById('cierreFecha').max = hoyIso();
    document.getElementById('cierreMotivo').value = '';
    document.getElementById('cierreModalOverlay').style.display = 'flex';
  });

  document.getElementById('nuevaAdendaBtn').addEventListener('click', () => abrirAdenda(null));

  document.querySelectorAll('[data-adenda-editar]').forEach((boton) => {
    boton.addEventListener('click', () => {
      abrirAdenda(adendas.find((a) => a.id === Number(boton.dataset.adendaEditar)));
    });
  });

  document.querySelectorAll('[data-adenda-eliminar]').forEach((boton) => {
    boton.addEventListener('click', accion(async () => {
      if (!confirm('¿Eliminar esta adenda?')) return;
      const res = await fetch(`/api/contratos/adendas/${boton.dataset.adendaEliminar}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('No se pudo eliminar la adenda');
    }));
  });

  document.querySelectorAll('[data-adenda-pdf]').forEach((input) => {
    input.addEventListener('change', accion(async () => {
      const archivo = input.files[0];
      if (!archivo) return;
      const error = errorDeArchivoPdf(archivo)
        || await subirPdf(`/api/contratos/adendas/${input.dataset.adendaPdf}/documento`, archivo);
      if (error) throw new Error(error);
    }));
  });
}

// ---------- Modal de adenda ----------

function actualizarMarcaAdenda() {
  const exige = CONTRATOS_CONFIG.tiposAdendaConFecha.includes(document.getElementById('adendaTipo').value);
  document.getElementById('adendaFinMarca').hidden = !exige;
}

function abrirAdenda(adenda) {
  adendaEditandoId = adenda ? adenda.id : null;
  document.getElementById('adendaModalTitulo').textContent = adenda ? `Editar adenda N.º ${adenda.numero}` : 'Nueva adenda';
  document.getElementById('adendaError').style.display = 'none';
  document.getElementById('adendaTipo').value = adenda ? adenda.tipo : '';
  document.getElementById('adendaDescripcion').value = adenda ? adenda.descripcion : '';
  document.getElementById('adendaNuevoFin').value = adenda ? (adenda.nuevoFin || '') : '';
  document.getElementById('adendaFirma').value = adenda ? (adenda.fechaSuscripcion || '') : '';
  document.getElementById('adendaPdf').value = '';
  actualizarMarcaAdenda();
  document.getElementById('adendaModalOverlay').style.display = 'flex';
}

(function bindModales() {
  document.getElementById('adendaTipo').innerHTML = '<option value="">Selecciona...</option>'
    + CONTRATOS_CONFIG.tiposAdenda.map((t) => `<option value="${t}">${t}</option>`).join('');
  document.getElementById('adendaTipo').addEventListener('change', actualizarMarcaAdenda);

  document.getElementById('adendaCancelarBtn').addEventListener('click', () => {
    document.getElementById('adendaModalOverlay').style.display = 'none';
  });
  document.getElementById('cierreCancelarBtn').addEventListener('click', () => {
    document.getElementById('cierreModalOverlay').style.display = 'none';
  });

  document.getElementById('adendaGuardarBtn').addEventListener('click', async () => {
    const errorMsg = document.getElementById('adendaError');
    const mostrarError = (texto) => {
      errorMsg.textContent = texto;
      errorMsg.style.display = 'block';
    };
    errorMsg.style.display = 'none';

    const datos = {
      tipo: document.getElementById('adendaTipo').value,
      descripcion: document.getElementById('adendaDescripcion').value.trim(),
      nuevoFin: document.getElementById('adendaNuevoFin').value,
      fechaSuscripcion: document.getElementById('adendaFirma').value
    };
    const archivo = document.getElementById('adendaPdf').files[0];

    if (!datos.tipo || !datos.descripcion) {
      mostrarError('El tipo y la descripción son obligatorios.');
      return;
    }
    if (CONTRATOS_CONFIG.tiposAdendaConFecha.includes(datos.tipo) && !datos.nuevoFin) {
      mostrarError('Indica el nuevo fin de vigencia.');
      return;
    }
    const problemaPdf = archivo ? errorDeArchivoPdf(archivo) : null;
    if (problemaPdf) {
      mostrarError(problemaPdf);
      return;
    }

    try {
      const data = adendaEditandoId
        ? await enviarJson(`/api/contratos/adendas/${adendaEditandoId}`, 'PUT', datos)
        : await enviarJson(`/api/contratos/${CONTRATO_ID}/adendas`, 'POST', datos);

      if (archivo) {
        const id = adendaEditandoId || data.id;
        const errorSubida = await subirPdf(`/api/contratos/adendas/${id}/documento`, archivo);
        if (errorSubida) alert(`La adenda se guardó, pero el PDF no: ${errorSubida}`);
      }

      document.getElementById('adendaModalOverlay').style.display = 'none';
      cargarContrato();
    } catch (err) {
      mostrarError(err.message);
    }
  });

  document.getElementById('cierreGuardarBtn').addEventListener('click', async () => {
    const errorMsg = document.getElementById('cierreError');
    errorMsg.style.display = 'none';

    const fechaCierre = document.getElementById('cierreFecha').value;
    if (!fechaCierre) {
      errorMsg.textContent = 'La fecha de cierre es obligatoria.';
      errorMsg.style.display = 'block';
      return;
    }

    try {
      await enviarJson(`/api/contratos/${CONTRATO_ID}/cerrar`, 'POST', {
        fechaCierre,
        motivo: document.getElementById('cierreMotivo').value.trim()
      });
      document.getElementById('cierreModalOverlay').style.display = 'none';
      cargarContrato();
    } catch (err) {
      errorMsg.textContent = err.message;
      errorMsg.style.display = 'block';
    }
  });
}());

cargarContrato();
