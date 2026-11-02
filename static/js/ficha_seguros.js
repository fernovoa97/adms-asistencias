// Seccion "Seguros" de la ficha: uno o varios seguros por colaborador, cada
// uno con sus personas adicionales. Un mismo modal sirve para crear y editar.

const TIPOS_SEGURO = ['SCTR', 'FOLA', 'Vida Ley', 'EPS'];
const PARENTESCOS = ['Cónyuge', 'Hijo/a'];

let seguroTrabajadorId = null;
let seguroEditandoId = null;

function calcularEdad(fechaNacimiento) {
  if (!fechaNacimiento) return null;
  const [anio, mes, dia] = fechaNacimiento.split('-').map(Number);
  const [anioHoy, mesHoy, diaHoy] = hoyLocalIso().split('-').map(Number);
  const aunNoCumple = mesHoy < mes || (mesHoy === mes && diaHoy < dia);
  return anioHoy - anio - (aunNoCumple ? 1 : 0);
}

function textoEdad(edad) {
  if (edad === null || edad < 0) return '—';
  return `${edad} ${edad === 1 ? 'año' : 'años'}`;
}

function seguroItemHtml(seguro) {
  const dependientes = seguro.dependientes.length === 0
    ? '<p class="muted">Sin personas adicionales.</p>'
    : `
      <div class="tabla-scroll">
        <table>
          <thead>
            <tr><th>Parentesco</th><th>Nombre completo</th><th>Nacimiento</th><th>Edad</th></tr>
          </thead>
          <tbody>
            ${seguro.dependientes.map((d) => `
              <tr>
                <td>${escapeHtml(d.parentesco)}</td>
                <td>${escapeHtml(d.nombre_completo)}</td>
                <td>${d.fecha_nacimiento}</td>
                <td>${textoEdad(d.edad)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;

  return `
    <div class="seguro-item">
      <div class="seguro-cabecera">
        <div>
          <div class="seguro-tipo">${escapeHtml(seguro.tipo)}</div>
          <div class="muted">Afiliación: ${seguro.fecha_afiliacion} · ${seguro.dependientes.length} persona(s) adicional(es)</div>
        </div>
        <div class="doc-actions">
          <button type="button" class="btn secondary sm" data-seguro-editar="${seguro.id}">Editar</button>
          <button type="button" class="btn danger sm" data-seguro-eliminar="${seguro.id}">Eliminar</button>
        </div>
      </div>
      ${dependientes}
    </div>
  `;
}

function segurosSeccionHtml(w) {
  const seguros = w.seguros || [];
  return `
    <div class="panel">
      <div class="panel-cabecera">
        <div>
          <h3>Seguros</h3>
          <p class="muted">SCTR, FOLA, Vida Ley y EPS del colaborador, con sus personas adicionales.</p>
        </div>
        <button type="button" class="btn" id="nuevoSeguroBtn">+ Registrar seguro</button>
      </div>
      ${seguros.length === 0
        ? '<div class="empty-state">Todavía no se registró ningún seguro.</div>'
        : `<div class="seguros-lista">${seguros.map(seguroItemHtml).join('')}</div>`}
    </div>
  `;
}

function bindSeguros(w) {
  seguroTrabajadorId = w.id;
  const seguros = w.seguros || [];

  document.getElementById('nuevoSeguroBtn').addEventListener('click', () => abrirModalSeguro(null));

  document.querySelectorAll('[data-seguro-editar]').forEach((boton) => {
    boton.addEventListener('click', () => {
      abrirModalSeguro(seguros.find((s) => s.id === Number(boton.dataset.seguroEditar)));
    });
  });

  document.querySelectorAll('[data-seguro-eliminar]').forEach((boton) => {
    boton.addEventListener('click', async () => {
      if (!confirm('¿Eliminar este seguro y sus personas adicionales?')) return;
      try {
        const res = await fetch(`/api/seguros/${boton.dataset.seguroEliminar}`, { method: 'DELETE' });
        if (!res.ok) {
          alert('No se pudo eliminar el seguro');
          return;
        }
        loadDetail(w.id, false);
      } catch (err) {
        alert('Error de conexión con el servidor');
      }
    });
  });
}

// ---------- Modal de seguro ----------

function agregarFilaDependiente(dependiente) {
  const fila = document.createElement('div');
  fila.className = 'dependiente-fila';
  fila.innerHTML = `
    <select class="dep-parentesco" aria-label="Parentesco">
      <option value="">Parentesco...</option>
      ${PARENTESCOS.map((p) => `<option value="${p}">${p}</option>`).join('')}
    </select>
    <input type="text" class="dep-nombre" placeholder="Nombre completo" aria-label="Nombre completo">
    <input type="date" class="dep-fecha" max="${hoyLocalIso()}" aria-label="Fecha de nacimiento">
    <span class="dep-edad" title="Calculada automáticamente">—</span>
    <button type="button" class="btn danger sm">Quitar</button>
  `;

  const fecha = fila.querySelector('.dep-fecha');
  const edad = fila.querySelector('.dep-edad');
  const actualizarEdad = () => {
    edad.textContent = textoEdad(calcularEdad(fecha.value));
  };

  if (dependiente) {
    fila.querySelector('.dep-parentesco').value = dependiente.parentesco;
    fila.querySelector('.dep-nombre').value = dependiente.nombre_completo;
    fecha.value = dependiente.fecha_nacimiento;
    actualizarEdad();
  }

  fecha.addEventListener('input', actualizarEdad);
  fila.querySelector('button').addEventListener('click', () => fila.remove());
  document.getElementById('dependientesFilas').appendChild(fila);
}

function abrirModalSeguro(seguro) {
  seguroEditandoId = seguro ? seguro.id : null;

  document.getElementById('seguroModalTitulo').textContent = seguro ? 'Editar seguro' : 'Registrar seguro';
  document.getElementById('seguroErrorMsg').style.display = 'none';
  document.getElementById('seguroTipo').value = seguro ? seguro.tipo : '';
  document.getElementById('seguroFechaAfiliacion').value = seguro ? seguro.fecha_afiliacion : '';
  document.getElementById('dependientesFilas').innerHTML = '';
  (seguro ? seguro.dependientes : []).forEach(agregarFilaDependiente);

  document.getElementById('seguroModalOverlay').style.display = 'flex';
}

// Una fila totalmente vacia se ignora; una a medio llenar es un error.
function leerDependientes() {
  const dependientes = [];
  let error = null;

  document.querySelectorAll('#dependientesFilas .dependiente-fila').forEach((fila) => {
    const parentesco = fila.querySelector('.dep-parentesco').value;
    const nombreCompleto = fila.querySelector('.dep-nombre').value.trim();
    const fechaNacimiento = fila.querySelector('.dep-fecha').value;

    if (!parentesco && !nombreCompleto && !fechaNacimiento) return;
    if (!parentesco || !nombreCompleto || !fechaNacimiento) {
      error = error || 'Completa parentesco, nombre y fecha de nacimiento de cada persona.';
      return;
    }
    if (fechaNacimiento > hoyLocalIso()) {
      error = error || `La fecha de nacimiento de ${nombreCompleto} no puede ser futura.`;
      return;
    }
    dependientes.push({ parentesco, nombreCompleto, fechaNacimiento });
  });

  return { dependientes, error };
}

(function bindSeguroModal() {
  const overlay = document.getElementById('seguroModalOverlay');
  const select = document.getElementById('seguroTipo');

  select.innerHTML = '<option value="">Selecciona...</option>'
    + TIPOS_SEGURO.map((t) => `<option value="${t}">${t}</option>`).join('');

  document.getElementById('agregarDependienteBtn').addEventListener('click', () => agregarFilaDependiente(null));

  document.getElementById('seguroCancelarBtn').addEventListener('click', () => {
    overlay.style.display = 'none';
  });

  document.getElementById('seguroGuardarBtn').addEventListener('click', async () => {
    const errorMsg = document.getElementById('seguroErrorMsg');
    const mostrarError = (texto) => {
      errorMsg.textContent = texto;
      errorMsg.style.display = 'block';
    };
    errorMsg.style.display = 'none';

    const tipo = select.value;
    const fechaAfiliacion = document.getElementById('seguroFechaAfiliacion').value;
    if (!tipo || !fechaAfiliacion) {
      mostrarError('El tipo de seguro y la fecha de afiliación son obligatorios.');
      return;
    }

    const { dependientes, error } = leerDependientes();
    if (error) {
      mostrarError(error);
      return;
    }

    const url = seguroEditandoId
      ? `/api/seguros/${seguroEditandoId}`
      : `/api/trabajadores/${seguroTrabajadorId}/seguros`;

    try {
      const res = await fetch(url, {
        method: seguroEditandoId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo, fechaAfiliacion, dependientes })
      });
      const data = await res.json();

      if (!res.ok) {
        mostrarError(data.error || 'No se pudo guardar el seguro');
        return;
      }

      overlay.style.display = 'none';
      loadDetail(seguroTrabajadorId, false);
    } catch (err) {
      mostrarError('Error de conexión con el servidor');
    }
  });
}());
