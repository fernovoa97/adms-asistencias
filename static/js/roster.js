// Roster de mina: pintar dias con un codigo (clic o arrastrar), deshacer,
// editar los datos de mina de cada fila, agregar trabajadores y administrar
// minas y codigos.

const DATOS = JSON.parse(document.getElementById('rosterDatos').textContent);
const CODIGOS = new Map(DATOS.codigos.map((c) => [String(c.id), c]));
const POR_LETRA = new Map(DATOS.codigos.map((c) => [c.codigo, c]));
const ID_FE = POR_LETRA.get('FE') ? String(POR_LETRA.get('FE').id) : '';
const CATEGORIAS_HORAS = ['trabajado', 'pago_doble'];
const CLAVE_SCROLL = 'roster-scroll';

let pincel = DATOS.codigos.length ? String(DATOS.codigos[0].id) : '';
let pintando = false;
let lote = new Map();
const historial = [];

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function mostrarError(id, texto) {
  const caja = document.getElementById(id);
  if (!caja) return;
  caja.textContent = texto || '';
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

// Recarga conservando la posicion del scroll de la grilla y de la pagina.
function recargar() {
  const grid = document.getElementById('rosterGrid');
  try {
    sessionStorage.setItem(CLAVE_SCROLL, JSON.stringify({
      x: grid ? grid.scrollLeft : 0, y: grid ? grid.scrollTop : 0, pagina: window.scrollY
    }));
  } catch (e) { /* sin almacenamiento: no pasa nada */ }
  window.location.reload();
}

function restaurarScroll() {
  let pos = null;
  try {
    pos = JSON.parse(sessionStorage.getItem(CLAVE_SCROLL) || 'null');
    sessionStorage.removeItem(CLAVE_SCROLL);
  } catch (e) { pos = null; }
  if (!pos) return;
  const grid = document.getElementById('rosterGrid');
  if (grid) { grid.scrollLeft = pos.x; grid.scrollTop = pos.y; }
  window.scrollTo(0, pos.pagina || 0);
}

// ---------------------------------------------------------------------------
// Celdas
// ---------------------------------------------------------------------------

// Mismo orden que resolver_dia() en roster.py.
function efectivoDe(celda) {
  const g = celda.dataset.g;
  const manual = celda.dataset.m === '1';
  const auto = celda.dataset.a;
  const feriado = celda.dataset.fe === '1' ? ID_FE : '';
  if (g && manual) return { id: g, auto: false };
  if (auto) return { id: auto, auto: true };
  if (g) return { id: g, auto: false };
  return { id: feriado, auto: Boolean(feriado) };
}

function pintarCelda(celda) {
  const { id, auto } = efectivoDe(celda);
  const codigo = CODIGOS.get(id);
  celda.textContent = codigo ? codigo.codigo : '';
  celda.style.background = codigo ? codigo.color : '';
  celda.style.color = codigo ? codigo.color_texto : '';
  celda.classList.toggle('auto', Boolean(codigo) && auto);
  celda.dataset.efectivo = id || '';
}

function recalcularFila(tr) {
  const totales = {};
  DATOS.totales.forEach((clave) => { totales[clave] = 0; });
  tr.querySelectorAll('.r-celda').forEach((celda) => {
    const codigo = CODIGOS.get(celda.dataset.efectivo || efectivoDe(celda).id);
    if (codigo && codigo.categoria in totales) totales[codigo.categoria] += 1;
  });
  tr.querySelectorAll('.r-total[data-cat]').forEach((td) => {
    td.textContent = totales[td.dataset.cat];
  });
  const horasGuardia = parseFloat(tr.dataset.horasGuardia) || 0;
  const dias = CATEGORIAS_HORAS.reduce((suma, c) => suma + (totales[c] || 0), 0);
  const horas = Math.round(dias * horasGuardia * 10) / 10;
  tr.querySelector('.r-horas').textContent = String(horas);
}

function estadoGuardado(texto) {
  const el = document.getElementById('estadoGuardado');
  if (el) el.textContent = texto;
}

function aplicarPincel(celda) {
  const clave = `${celda.closest('tr').dataset.trabajador}|${celda.dataset.f}`;
  if (lote.has(clave)) return;
  const antes = { g: celda.dataset.g, m: celda.dataset.m };
  const despues = pincel ? { g: pincel, m: '1' } : { g: '', m: '0' };
  if (antes.g === despues.g && (antes.m === despues.m || !despues.g)) return;
  lote.set(clave, { celda, antes, despues });
  celda.dataset.g = despues.g;
  celda.dataset.m = despues.m;
  pintarCelda(celda);
  celda.classList.add('pendiente');
}

function cambioDe(celda, estado) {
  return {
    trabajador_id: Number(celda.closest('tr').dataset.trabajador),
    fecha: celda.dataset.f,
    codigo_id: estado.g ? Number(estado.g) : null,
    manual: estado.m === '1'
  };
}

function aplicarEstados(items, campo) {
  const filas = new Set();
  items.forEach((item) => {
    item.celda.dataset.g = item[campo].g;
    item.celda.dataset.m = item[campo].m;
    pintarCelda(item.celda);
    filas.add(item.celda.closest('tr'));
  });
  filas.forEach(recalcularFila);
}

async function guardarLote() {
  if (lote.size === 0) return;
  const items = [...lote.values()];
  lote = new Map();
  const filas = new Set(items.map((i) => i.celda.closest('tr')));
  filas.forEach(recalcularFila);
  estadoGuardado('Guardando...');
  try {
    await enviar('/api/roster/dias', 'POST', { cambios: items.map((i) => cambioDe(i.celda, i.despues)) });
    historial.push(items);
    document.getElementById('deshacerBtn').disabled = false;
    estadoGuardado('Guardado');
    mostrarError('rosterError', '');
  } catch (err) {
    aplicarEstados(items, 'antes');
    estadoGuardado('');
    mostrarError('rosterError', err.message);
  } finally {
    items.forEach((i) => i.celda.classList.remove('pendiente'));
  }
}

async function deshacer() {
  const items = historial.pop();
  document.getElementById('deshacerBtn').disabled = historial.length === 0;
  if (!items) return;
  aplicarEstados(items, 'antes');
  estadoGuardado('Deshaciendo...');
  try {
    await enviar('/api/roster/dias', 'POST', { cambios: items.map((i) => cambioDe(i.celda, i.antes)) });
    estadoGuardado('Cambio deshecho');
  } catch (err) {
    aplicarEstados(items, 'despues');
    historial.push(items);
    document.getElementById('deshacerBtn').disabled = false;
    estadoGuardado('');
    mostrarError('rosterError', err.message);
  }
}

function elegirPincel(id) {
  pincel = id;
  document.querySelectorAll('.roster-pincel').forEach((b) => {
    const activo = b.dataset.codigoId === id;
    b.classList.toggle('activo', activo);
    b.setAttribute('aria-pressed', activo ? 'true' : 'false');
  });
  const codigo = CODIGOS.get(id);
  document.getElementById('pincelNombre').textContent = codigo ? codigo.nombre : 'Quita el código puesto (vuelve a lo automático)';
}

function iniciarGrilla() {
  const grid = document.getElementById('rosterGrid');
  if (!grid) return;

  document.querySelectorAll('.r-celda').forEach((celda) => {
    celda.dataset.efectivo = efectivoDe(celda).id || '';
    celda.title = tituloCelda(celda);
  });

  document.getElementById('pinceles').addEventListener('click', (e) => {
    const boton = e.target.closest('.roster-pincel');
    if (boton) elegirPincel(boton.dataset.codigoId);
  });

  grid.addEventListener('pointerdown', (e) => {
    const celda = e.target.closest('.r-celda');
    if (!celda || e.button !== 0) return;
    e.preventDefault();
    if (celda.hasPointerCapture && celda.hasPointerCapture(e.pointerId)) {
      celda.releasePointerCapture(e.pointerId);
    }
    pintando = true;
    aplicarPincel(celda);
  });

  document.addEventListener('pointermove', (e) => {
    if (!pintando) return;
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const celda = el && el.closest('.r-celda');
    if (celda && grid.contains(celda)) aplicarPincel(celda);
  });

  const terminar = () => {
    if (!pintando) return;
    pintando = false;
    guardarLote();
  };
  document.addEventListener('pointerup', terminar);
  document.addEventListener('pointercancel', terminar);

  // Teclado: Enter/Espacio pone el codigo; flechas mueven entre dias.
  grid.addEventListener('click', (e) => {
    const celda = e.target.closest('.r-celda');
    if (celda && e.detail === 0) {
      aplicarPincel(celda);
      guardarLote();
    }
  });
  grid.addEventListener('keydown', (e) => {
    const celda = e.target.closest('.r-celda');
    if (!celda) return;
    const td = celda.closest('td');
    let destino = null;
    if (e.key === 'ArrowRight') destino = td.nextElementSibling;
    if (e.key === 'ArrowLeft') destino = td.previousElementSibling;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      const tr = e.key === 'ArrowDown' ? td.parentElement.nextElementSibling : td.parentElement.previousElementSibling;
      if (tr) destino = tr.children[td.cellIndex];
    }
    const boton = destino && destino.querySelector('.r-celda');
    if (boton) { e.preventDefault(); boton.focus(); }
  });

  // Escribir la letra de un codigo lo elige como pincel (ej. "DL", "9A").
  let tecleado = '';
  let temporizador = null;
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.target.closest('input, textarea, select')) {
      e.preventDefault();
      deshacer();
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1) return;
    if (e.target.closest('input, textarea, select, .modal-overlay:not([hidden])')) return;
    clearTimeout(temporizador);
    const hayPrefijo = (texto) => DATOS.codigos.some((c) => c.codigo.startsWith(texto) && c.codigo !== texto);
    tecleado = (tecleado + e.key).toUpperCase();
    if (!POR_LETRA.has(tecleado) && !hayPrefijo(tecleado)) tecleado = e.key.toUpperCase();
    const exacto = POR_LETRA.get(tecleado);
    if (exacto) elegirPincel(String(exacto.id));
    if (!hayPrefijo(tecleado)) tecleado = '';
    temporizador = setTimeout(() => { tecleado = ''; }, 800);
  });

  document.getElementById('deshacerBtn').addEventListener('click', deshacer);
  grid.addEventListener('mouseover', (e) => {
    const celda = e.target.closest('.r-celda');
    if (celda) celda.title = tituloCelda(celda);
  });
}

function tituloCelda(celda) {
  const { id, auto } = efectivoDe(celda);
  const codigo = CODIGOS.get(id);
  const fecha = celda.dataset.f.split('-').reverse().join('/');
  if (!codigo) return `${fecha}: sin código`;
  let origen = 'puesto a mano';
  if (auto) {
    origen = celda.dataset.a ? 'registrado en el sistema' : 'feriado';
  } else if (celda.dataset.m !== '1') {
    origen = 'generado por el régimen';
  }
  return `${fecha}: ${codigo.codigo} · ${codigo.nombre} (${origen})`;
}

// ---------------------------------------------------------------------------
// Modales
// ---------------------------------------------------------------------------

function abrirModal(id) {
  const overlay = document.getElementById(id);
  overlay.hidden = false;
  const primero = overlay.querySelector('input:not([type=hidden]), select, button');
  if (primero) primero.focus();
}

function cerrarModal(id) {
  document.getElementById(id).hidden = true;
}

document.querySelectorAll('.modal-overlay').forEach((overlay) => {
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.hidden = true; });
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') document.querySelectorAll('.modal-overlay').forEach((o) => { o.hidden = true; });
});

// --- Editar fila ---
let filaActual = null;

document.addEventListener('click', (e) => {
  const boton = e.target.closest('.r-editar');
  if (!boton) return;
  filaActual = JSON.parse(boton.dataset.fila);
  document.getElementById('filaTitulo').textContent = filaActual.nombre;
  document.getElementById('filaSubtitulo').textContent =
    [filaActual.dni && `DNI ${filaActual.dni}`, filaActual.cargo].filter(Boolean).join(' · ');
  document.getElementById('filaMina').value = filaActual.mina_id || '';
  document.getElementById('filaGuardia').value = filaActual.guardia || '';
  document.getElementById('filaRegTrabajo').value = filaActual.regimen_trabajo || '';
  document.getElementById('filaRegDescanso').value = filaActual.regimen_descanso || '';
  document.getElementById('filaInicio').value = filaActual.inicio_ciclo || '';
  document.getElementById('filaHoras').value = filaActual.horas_guardia || 12;
  document.getElementById('filaCondicion').value = filaActual.condicion || '';
  document.getElementById('filaSexo').value = filaActual.sexo || '';
  document.getElementById('filaResidencia').value = filaActual.residencia || filaActual.residencia_ficha || '';
  document.getElementById('filaConduce').checked = filaActual.conduce_mina;
  mostrarError('filaError', '');
  abrirModal('filaOverlay');
});

document.getElementById('filaCancelarBtn').addEventListener('click', () => cerrarModal('filaOverlay'));

document.getElementById('filaForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const boton = document.getElementById('filaGuardarBtn');
  const residencia = document.getElementById('filaResidencia').value.trim();
  boton.disabled = true;
  try {
    await enviar(`/api/roster/filas/${filaActual.id}`, 'PUT', {
      mina_id: Number(document.getElementById('filaMina').value) || null,
      guardia: document.getElementById('filaGuardia').value,
      regimen_trabajo: document.getElementById('filaRegTrabajo').value,
      regimen_descanso: document.getElementById('filaRegDescanso').value,
      inicio_ciclo: document.getElementById('filaInicio').value,
      horas_guardia: document.getElementById('filaHoras').value,
      condicion: document.getElementById('filaCondicion').value,
      sexo: document.getElementById('filaSexo').value,
      // Si coincide con la ficha no se guarda aparte: asi sigue a la ficha.
      residencia: residencia === filaActual.residencia_ficha ? '' : residencia,
      conduce_mina: document.getElementById('filaConduce').checked
    });
    recargar();
  } catch (err) {
    mostrarError('filaError', err.message);
    boton.disabled = false;
  }
});

document.getElementById('filaQuitarBtn').addEventListener('click', async () => {
  if (!confirm(`¿Quitar a ${filaActual.nombre} del roster de este mes? Se borran sus días de este mes.`)) return;
  try {
    await enviar(`/api/roster/filas/${filaActual.id}`, 'DELETE');
    recargar();
  } catch (err) {
    mostrarError('filaError', err.message);
  }
});

// --- Agregar trabajadores ---
let candidatos = [];
const elegidos = new Set();

function renderCandidatos() {
  const lista = document.getElementById('agregarLista');
  const q = document.getElementById('agregarBuscar').value.trim().toLowerCase();
  const visibles = candidatos.filter((t) =>
    !q || [t.nombre, t.dni, t.cargo, t.sede].some((v) => (v || '').toLowerCase().includes(q)));
  if (visibles.length === 0) {
    lista.innerHTML = `<li class="muted">${candidatos.length ? 'Nadie coincide con la búsqueda.' : 'Todos los trabajadores activos ya están en este mes.'}</li>`;
  } else {
    lista.innerHTML = visibles.map((t) => `
      <li><label>
        <input type="checkbox" value="${t.id}" ${elegidos.has(t.id) ? 'checked' : ''}>
        <span class="roster-candidato-nombre">${escapeHtml(t.nombre)}</span>
        <span class="muted">${escapeHtml([t.dni, t.cargo, t.sede].filter(Boolean).join(' · '))}</span>
      </label></li>`).join('');
  }
  const boton = document.getElementById('agregarGuardarBtn');
  boton.disabled = elegidos.size === 0;
  boton.textContent = elegidos.size ? `Agregar (${elegidos.size})` : 'Agregar';
}

document.getElementById('agregarBtn').addEventListener('click', async () => {
  elegidos.clear();
  document.getElementById('agregarBuscar').value = '';
  mostrarError('agregarError', '');
  abrirModal('agregarOverlay');
  document.getElementById('agregarBuscar').focus();
  try {
    const res = await fetch(`/api/roster/candidatos?anio=${DATOS.anio}&mes=${DATOS.mes}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'No se pudo cargar la lista');
    candidatos = data.trabajadores;
    renderCandidatos();
  } catch (err) {
    mostrarError('agregarError', err.message);
  }
});

document.getElementById('agregarBuscar').addEventListener('input', renderCandidatos);
document.getElementById('agregarLista').addEventListener('change', (e) => {
  if (e.target.type !== 'checkbox') return;
  const id = Number(e.target.value);
  if (e.target.checked) elegidos.add(id); else elegidos.delete(id);
  renderCandidatos();
});
document.getElementById('agregarCancelarBtn').addEventListener('click', () => cerrarModal('agregarOverlay'));
document.getElementById('agregarGuardarBtn').addEventListener('click', async () => {
  const boton = document.getElementById('agregarGuardarBtn');
  boton.disabled = true;
  try {
    await enviar('/api/roster/filas', 'POST', {
      anio: DATOS.anio, mes: DATOS.mes, trabajador_ids: [...elegidos],
      mina_id: Number(document.getElementById('agregarMina').value) || null
    });
    recargar();
  } catch (err) {
    mostrarError('agregarError', err.message);
    boton.disabled = false;
  }
});

// --- Barra superior ---
document.getElementById('filtroMina').addEventListener('change', (e) => {
  const params = new URLSearchParams({ anio: DATOS.anio, mes: DATOS.mes });
  if (e.target.value) params.set('mina', e.target.value);
  window.location.href = `/roster?${params}`;
});

const generarBtn = document.getElementById('generarBtn');
if (generarBtn) {
  generarBtn.addEventListener('click', async () => {
    if (!confirm('Se vuelven a generar los días T y DL de cada trabajador según su régimen y fecha de subida. Lo que pusiste a mano no cambia. ¿Continuar?')) return;
    generarBtn.disabled = true;
    try {
      const data = await enviar('/api/roster/generar', 'POST', { anio: DATOS.anio, mes: DATOS.mes, mina_id: DATOS.mina_id });
      if (data.sin_regimen) {
        alert(`${data.sin_regimen} trabajador(es) no tienen régimen o fecha de subida: sus días no se generaron.`);
      }
      recargar();
    } catch (err) {
      mostrarError('rosterError', err.message);
      generarBtn.disabled = false;
    }
  });
}

const copiarBtn = document.getElementById('copiarBtn');
if (copiarBtn) {
  copiarBtn.addEventListener('click', async () => {
    copiarBtn.disabled = true;
    try {
      await enviar('/api/roster/copiar', 'POST', { anio: DATOS.anio, mes: DATOS.mes });
      recargar();
    } catch (err) {
      mostrarError('rosterError', err.message);
      copiarBtn.disabled = false;
    }
  });
}

// ---------------------------------------------------------------------------
// Minas y codigos
// ---------------------------------------------------------------------------

function abrirConfigAlRecargar() {
  try { sessionStorage.setItem('roster-config', '1'); } catch (e) { /* nada */ }
  recargar();
}

document.getElementById('nuevaMinaForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    await enviar('/api/roster/minas', 'POST', { nombre: document.getElementById('nuevaMina').value });
    abrirConfigAlRecargar();
  } catch (err) {
    mostrarError('minasError', err.message);
  }
});

document.querySelectorAll('tr[data-mina-id]').forEach((tr) => {
  const id = tr.dataset.minaId;
  tr.querySelector('.mina-guardar').addEventListener('click', async () => {
    try {
      await enviar(`/api/roster/minas/${id}`, 'PUT', { nombre: tr.querySelector('.mina-nombre').value });
      abrirConfigAlRecargar();
    } catch (err) {
      mostrarError('minasError', err.message);
    }
  });
  tr.querySelector('.mina-eliminar').addEventListener('click', async () => {
    const nombre = tr.querySelector('.mina-nombre').value;
    if (!confirm(`¿Eliminar la mina ${nombre}? Los trabajadores que la tenían quedan sin mina.`)) return;
    try {
      await enviar(`/api/roster/minas/${id}`, 'DELETE');
      abrirConfigAlRecargar();
    } catch (err) {
      mostrarError('minasError', err.message);
    }
  });
});

function datosCodigo(tr) {
  return {
    codigo: tr.querySelector('.cod-codigo').value,
    nombre: tr.querySelector('.cod-nombre').value,
    color: tr.querySelector('.cod-color').value,
    color_texto: tr.querySelector('.cod-texto').value,
    categoria: tr.querySelector('.cod-categoria').value
  };
}

document.querySelectorAll('.roster-config-tabla tr[data-codigo-id], .roster-config-tabla tr.cod-nuevo').forEach((tr) => {
  const vista = tr.querySelector('.roster-chip');
  const actualizarVista = () => {
    vista.style.background = tr.querySelector('.cod-color').value;
    vista.style.color = tr.querySelector('.cod-texto').value;
    vista.textContent = tr.querySelector('.cod-codigo').value.toUpperCase() || '—';
  };
  tr.querySelectorAll('input').forEach((i) => i.addEventListener('input', actualizarVista));

  const guardar = tr.querySelector('.cod-guardar');
  if (guardar) {
    guardar.addEventListener('click', async () => {
      try {
        await enviar(`/api/roster/codigos/${tr.dataset.codigoId}`, 'PUT', datosCodigo(tr));
        abrirConfigAlRecargar();
      } catch (err) {
        mostrarError('codigosError', err.message);
      }
    });
  }
  const eliminar = tr.querySelector('.cod-eliminar');
  if (eliminar) {
    eliminar.addEventListener('click', async () => {
      if (!confirm(`¿Eliminar el código ${tr.querySelector('.cod-codigo').value}?`)) return;
      try {
        await enviar(`/api/roster/codigos/${tr.dataset.codigoId}`, 'DELETE');
        abrirConfigAlRecargar();
      } catch (err) {
        mostrarError('codigosError', err.message);
      }
    });
  }
  const agregar = tr.querySelector('.cod-agregar');
  if (agregar) {
    agregar.addEventListener('click', async () => {
      try {
        await enviar('/api/roster/codigos', 'POST', datosCodigo(tr));
        abrirConfigAlRecargar();
      } catch (err) {
        mostrarError('codigosError', err.message);
      }
    });
  }
});

try {
  if (sessionStorage.getItem('roster-config')) {
    sessionStorage.removeItem('roster-config');
    document.getElementById('configuracion').open = true;
  }
} catch (e) { /* nada */ }

iniciarGrilla();
restaurarScroll();
