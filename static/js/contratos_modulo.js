// Listado de un modulo de contratos, o de los finalizados (MODULO_ACTUAL null).

let contratosCache = [];
let filtroEstado = '';

async function cargarContratos() {
  const cuerpo = document.getElementById('tablaContratos');
  try {
    const url = MODULO_ACTUAL ? `/api/contratos?modulo=${MODULO_ACTUAL}` : '/api/contratos';
    const res = await fetch(url);
    const data = await res.json();
    contratosCache = MODULO_ACTUAL
      ? data.contratos
      : data.contratos.filter((c) => c.estado === 'finalizado');
    renderContratos();
  } catch (err) {
    cuerpo.innerHTML = '<tr><td colspan="8" class="empty-state">Error al cargar</td></tr>';
  }
}

function coincideBusqueda(c, texto) {
  return [c.numero, c.contraparteNombre, c.contraparteRuc, c.objeto]
    .some((valor) => (valor || '').toLowerCase().includes(texto));
}

function filaContrato(c) {
  const fin = c.finEfectivo
    ? `${c.finEfectivo}<div class="muted">${textoDias(c.diasRestantes)}</div>`
    : '<span class="muted">Sin fecha</span>';

  return `
    <tr>
      <td><a href="/contratos/${c.id}">${escapeHtml(c.numero)}</a></td>
      <td>${escapeHtml(c.contraparteNombre)}${c.contraparteRuc ? `<div class="muted">RUC ${escapeHtml(c.contraparteRuc)}</div>` : ''}</td>
      <td>${escapeHtml(c.categoria)}</td>
      <td class="celda-texto">${escapeHtml(c.objeto)}</td>
      <td>${fin}</td>
      <td>${textoImporte(c.importe, c.moneda)}</td>
      <td>${escapeHtml(c.responsable)}</td>
      <td>${badgeContrato(c.estado)}</td>
    </tr>
  `;
}

function renderContratos() {
  const cuerpo = document.getElementById('tablaContratos');
  const texto = document.getElementById('buscarContrato').value.trim().toLowerCase();

  const visibles = contratosCache.filter((c) => (!filtroEstado || c.estado === filtroEstado)
    && (!texto || coincideBusqueda(c, texto)));

  cuerpo.innerHTML = visibles.length
    ? visibles.map(filaContrato).join('')
    : '<tr><td colspan="8" class="empty-state">No hay contratos para mostrar.</td></tr>';
}

async function cargarLaboralesSinFicha() {
  const panel = document.getElementById('laboralesSinFicha');
  const res = await fetch('/api/contratos/laborales-sin-ficha');
  const data = await res.json();

  panel.hidden = data.trabajadores.length === 0;
  const lista = document.getElementById('laboralesSinFichaLista');
  lista.innerHTML = '';

  data.trabajadores.forEach((t) => {
    const item = document.createElement('div');
    item.className = 'doc-item';
    item.innerHTML = `
      <div>
        <div class="doc-name">${escapeHtml(t.nombre)}</div>
        <div class="muted">${escapeHtml(t.tipoContrato || 'Sin tipo de contrato')} · Fin: ${t.fechaFin || '—'}</div>
      </div>
      <button type="button" class="btn secondary sm">Crear ficha</button>
    `;
    item.querySelector('button').addEventListener('click', () => {
      abrirNuevoContrato({
        trabajadorId: t.id,
        contraparteNombre: t.nombre,
        objeto: t.cargo ? `Contrato de trabajo: ${t.cargo}` : 'Contrato de trabajo',
        inicioVigencia: t.fechaRenovacion || t.fechaIngreso,
        finVigencia: t.fechaFin
      });
    });
    lista.appendChild(item);
  });
}

function abrirNuevoContrato(inicial) {
  abrirFormularioContrato({
    modulo: MODULO_ACTUAL,
    inicial,
    alGuardar: (id) => { window.location.href = `/contratos/${id}`; }
  });
}

document.getElementById('buscarContrato').addEventListener('input', renderContratos);

if (MODULO_ACTUAL) {
  document.getElementById('nuevoContratoBtn').addEventListener('click', () => abrirNuevoContrato());

  document.querySelectorAll('#filtroEstado a').forEach((tab) => {
    tab.addEventListener('click', (e) => {
      e.preventDefault();
      filtroEstado = tab.dataset.estado;
      document.querySelectorAll('#filtroEstado a').forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      renderContratos();
    });
  });
}

if (MODULO_ACTUAL === 'laborales') cargarLaboralesSinFicha();
cargarContratos();
