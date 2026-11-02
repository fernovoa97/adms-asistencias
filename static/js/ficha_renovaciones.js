// Tarjetas de renovacion de la ficha: EMO, activos y EPPs. Las tres comparten
// diseno y logica; lo que cambia esta en TARJETAS_RENOVACION.

const TARJETAS_RENOVACION = [
  {
    tipo: 'EMO',
    titulo: 'Actualizar renovación de EMO',
    descripcion: 'Examen Médico Ocupacional. Cada renovación queda guardada en el historial.',
    etiquetaFecha: 'Fecha de renovación del EMO',
    etiquetaProxima: 'Fecha de vencimiento del próximo EMO',
    conPdf: true
  },
  {
    tipo: 'ACTIVO',
    titulo: 'Actualizar renovación de activos',
    descripcion: 'Registra la entrega o renovación de un activo asignado.',
    etiquetaFecha: 'Fecha de renovación / entrega',
    etiquetaProxima: 'Fecha de próxima renovación',
    conActivo: true
  },
  {
    tipo: 'EPP',
    titulo: 'Actualizar renovación de EPPs',
    descripcion: 'Equipos de Protección Personal. Cada entrega queda guardada en el historial.',
    etiquetaFecha: 'Fecha de renovación / entrega',
    etiquetaProxima: 'Fecha de próxima renovación'
  }
];

const DIAS_ALERTA_RENOVACION = 30;
const TAMANO_MAXIMO_PDF_RENOVACION = 25 * 1024 * 1024;
const MS_POR_DIA_RENOVACION = 24 * 60 * 60 * 1000;

function hoyLocalIso() {
  return new Date().toLocaleDateString('en-CA');
}

function badgeVencimiento(fecha) {
  const dias = Math.round((Date.parse(fecha) - Date.parse(hoyLocalIso())) / MS_POR_DIA_RENOVACION);
  if (dias < 0) return '<span class="badge doc-vencido">Vencido</span>';
  if (dias <= DIAS_ALERTA_RENOVACION) return '<span class="badge doc-por-vencer">Por vencer</span>';
  return '<span class="badge doc-vigente">Vigente</span>';
}

// La lista viene de la mas reciente a la mas antigua, asi que la primera de
// cada activo (o la primera de todas, en EMO y EPP) es la vigente.
function renovacionesVigentes(registros) {
  const vistos = new Set();
  return registros.filter((r) => {
    const clave = r.activo || '';
    if (vistos.has(clave)) return false;
    vistos.add(clave);
    return true;
  });
}

// El mismo control sirve en la fila vigente y en el historial: abre el PDF si
// ya esta subido, o permite subirlo si falta.
function pdfRenovacionHtml(r) {
  if (r.documento_id) {
    return `<a class="btn secondary sm" href="/documentos/${r.documento_id}" target="_blank">Ver PDF</a>`;
  }
  return `
    <label class="btn secondary sm">
      Subir PDF
      <input type="file" accept="application/pdf" data-renovacion-pdf="${r.id}" hidden>
    </label>
  `;
}

function errorDePdf(archivo) {
  if (!archivo.name.toLowerCase().endsWith('.pdf')) return 'El archivo debe ser un PDF';
  if (archivo.size > TAMANO_MAXIMO_PDF_RENOVACION) return 'El archivo supera los 25MB';
  return null;
}

async function subirPdfRenovacion(renovacionId, archivo) {
  const formData = new FormData();
  formData.append('archivo', archivo);
  try {
    const res = await fetch(`/api/renovaciones/${renovacionId}/documento`, { method: 'POST', body: formData });
    const data = await res.json();
    return res.ok ? null : (data.error || 'No se pudo subir el PDF');
  } catch (err) {
    return 'Error de conexión con el servidor';
  }
}

function vigentesHtml(tarjeta, registros) {
  if (registros.length === 0) {
    return '<p class="muted">Todavía no hay ninguna renovación registrada.</p>';
  }
  return `
    <div class="estado-lista">
      ${renovacionesVigentes(registros).map((r) => `
        <div class="estado-fila">
          <span>${r.activo ? `<strong>${escapeHtml(r.activo)}</strong> · ` : ''}Próxima: ${r.fecha_proxima}</span>
          <span class="estado-acciones">
            ${tarjeta.conPdf ? pdfRenovacionHtml(r) : ''}
            ${badgeVencimiento(r.fecha_proxima)}
          </span>
        </div>
      `).join('')}
    </div>
  `;
}

function historialRenovacionHtml(tarjeta, registros) {
  if (registros.length === 0) return '';
  return `
    <details class="historial">
      <summary>Historial (${registros.length})</summary>
      <div class="tabla-scroll">
        <table>
          <thead>
            <tr>
              ${tarjeta.conPdf ? '<th>PDF</th>' : ''}
              ${tarjeta.conActivo ? '<th>Activo</th>' : ''}
              <th>Renovación</th>
              <th>Próxima</th>
              <th>Registrado</th>
            </tr>
          </thead>
          <tbody>
            ${registros.map((r) => `
              <tr>
                ${tarjeta.conPdf ? `<td>${pdfRenovacionHtml(r)}</td>` : ''}
                ${tarjeta.conActivo ? `<td>${escapeHtml(r.activo || '—')}</td>` : ''}
                <td>${r.fecha_renovacion}</td>
                <td>${r.fecha_proxima}</td>
                <td>${escapeHtml(r.creado_en)} · ${escapeHtml(r.creado_por || 'admin')}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </details>
  `;
}

function tarjetaRenovacionHtml(tarjeta, renovaciones) {
  const { tipo } = tarjeta;
  const registros = renovaciones.filter((r) => r.tipo === tipo);

  return `
    <div class="panel">
      <h3>${tarjeta.titulo}</h3>
      <p class="muted">${tarjeta.descripcion}</p>
      ${vigentesHtml(tarjeta, registros)}
      <div class="error-msg" id="renovacionError${tipo}"></div>
      <form data-renovacion="${tipo}">
        ${tarjeta.conActivo ? `
          <div class="field">
            <label for="renovacionActivo">Activo *</label>
            <div class="campo-con-boton">
              <select id="renovacionActivo" required>
                <option value="">Selecciona un activo...</option>
              </select>
              <button type="button" class="btn secondary" id="nuevoActivoBtn">+ Nuevo</button>
            </div>
          </div>
        ` : ''}
        <div class="grid-2">
          <div class="field">
            <label for="renovacionFecha${tipo}">${tarjeta.etiquetaFecha} *</label>
            <input type="date" id="renovacionFecha${tipo}" required>
          </div>
          <div class="field">
            <label for="renovacionProxima${tipo}">${tarjeta.etiquetaProxima} *</label>
            <input type="date" id="renovacionProxima${tipo}" required>
          </div>
        </div>
        ${tarjeta.conPdf ? `
          <div class="field">
            <label for="renovacionPdf${tipo}">Documento del examen (PDF, opcional)</label>
            <input type="file" id="renovacionPdf${tipo}" accept="application/pdf">
          </div>
        ` : ''}
        <button type="submit" class="btn">Guardar renovación</button>
      </form>
      ${historialRenovacionHtml(tarjeta, registros)}
    </div>
  `;
}

function tarjetasRenovacionHtml(w) {
  return TARJETAS_RENOVACION
    .map((tarjeta) => tarjetaRenovacionHtml(tarjeta, w.renovaciones || []))
    .join('');
}

function bindRenovaciones(w) {
  cargarCatalogoActivos();

  document.getElementById('nuevoActivoBtn').addEventListener('click', () => {
    document.getElementById('nuevoActivoErrorMsg').style.display = 'none';
    document.getElementById('nuevoActivoNombre').value = '';
    document.getElementById('nuevoActivoModalOverlay').style.display = 'flex';
  });

  document.querySelectorAll('form[data-renovacion]').forEach((form) => {
    const tipo = form.dataset.renovacion;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const errorMsg = document.getElementById(`renovacionError${tipo}`);
      errorMsg.style.display = 'none';

      const fechaRenovacion = document.getElementById(`renovacionFecha${tipo}`).value;
      const fechaProxima = document.getElementById(`renovacionProxima${tipo}`).value;
      const activo = tipo === 'ACTIVO' ? document.getElementById('renovacionActivo').value : '';

      if (fechaProxima < fechaRenovacion) {
        errorMsg.textContent = 'La próxima fecha no puede ser anterior a la de renovación.';
        errorMsg.style.display = 'block';
        return;
      }

      const inputPdf = document.getElementById(`renovacionPdf${tipo}`);
      const archivoPdf = inputPdf ? inputPdf.files[0] : null;
      const problemaPdf = archivoPdf ? errorDePdf(archivoPdf) : null;
      if (problemaPdf) {
        errorMsg.textContent = problemaPdf;
        errorMsg.style.display = 'block';
        return;
      }

      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      btn.textContent = 'Guardando...';

      try {
        const res = await fetch(`/api/trabajadores/${w.id}/renovaciones`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tipo, activo, fechaRenovacion, fechaProxima })
        });
        const data = await res.json();

        if (!res.ok) {
          errorMsg.textContent = data.error || 'No se pudo guardar la renovación';
          errorMsg.style.display = 'block';
          return;
        }

        // La renovacion ya quedo guardada: si el PDF falla, se avisa y se
        // puede reintentar con "Subir PDF" sin duplicar el registro.
        if (archivoPdf) {
          const errorSubida = await subirPdfRenovacion(data.id, archivoPdf);
          if (errorSubida) alert(`La renovación se guardó, pero el PDF no: ${errorSubida}`);
        }

        loadDetail(w.id, false);
      } catch (err) {
        errorMsg.textContent = 'Error de conexión con el servidor';
        errorMsg.style.display = 'block';
      } finally {
        btn.disabled = false;
        btn.textContent = 'Guardar renovación';
      }
    });
  });

  document.querySelectorAll('[data-renovacion-pdf]').forEach((input) => {
    input.addEventListener('change', async () => {
      const archivo = input.files[0];
      if (!archivo) return;

      const error = errorDePdf(archivo) || await subirPdfRenovacion(input.dataset.renovacionPdf, archivo);
      if (error) {
        alert(error);
        input.value = '';
        return;
      }
      loadDetail(w.id, false);
    });
  });
}

// ---------- Catalogo de activos (combo administrable) ----------

async function cargarCatalogoActivos(seleccionar) {
  const select = document.getElementById('renovacionActivo');
  if (!select) return;
  try {
    const res = await fetch('/api/activos-catalogo');
    const data = await res.json();
    select.innerHTML = '<option value="">Selecciona un activo...</option>';
    (data.activos || []).forEach((a) => {
      const opt = document.createElement('option');
      opt.value = a.nombre;
      opt.textContent = a.nombre;
      select.appendChild(opt);
    });
    if (seleccionar) select.value = seleccionar;
  } catch (err) {
    // si falla, se queda solo la opcion por defecto
  }
}

(function bindNuevoActivoModal() {
  const overlay = document.getElementById('nuevoActivoModalOverlay');

  document.getElementById('nuevoActivoCancelarBtn').addEventListener('click', () => {
    overlay.style.display = 'none';
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.style.display = 'none';
  });

  document.getElementById('nuevoActivoGuardarBtn').addEventListener('click', async () => {
    const errorMsg = document.getElementById('nuevoActivoErrorMsg');
    errorMsg.style.display = 'none';

    const nombre = document.getElementById('nuevoActivoNombre').value.trim();
    if (!nombre) {
      errorMsg.textContent = 'Escribe el nombre del activo.';
      errorMsg.style.display = 'block';
      return;
    }

    try {
      const res = await fetch('/api/activos-catalogo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre })
      });
      const data = await res.json();

      if (!res.ok) {
        errorMsg.textContent = data.error || 'No se pudo crear el activo';
        errorMsg.style.display = 'block';
        return;
      }

      await cargarCatalogoActivos(data.nombre);
      overlay.style.display = 'none';
    } catch (err) {
      errorMsg.textContent = 'Error de conexión con el servidor';
      errorMsg.style.display = 'block';
    }
  });
}());
