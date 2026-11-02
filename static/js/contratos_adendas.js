let adendasCache = [];
let filtroAdenda = '';

function renderAdendas() {
  const cuerpo = document.getElementById('tablaAdendas');
  const visibles = adendasCache.filter((a) => !filtroAdenda
    || (filtroAdenda === 'formalizada') === a.formalizada);

  cuerpo.innerHTML = visibles.length
    ? visibles.map((a) => `
      <tr>
        <td><a href="/contratos/${a.contratoId}">${escapeHtml(a.contratoNumero)}</a><div class="muted">${escapeHtml(a.moduloNombre)}</div></td>
        <td>${escapeHtml(a.tipo)} N.º ${a.numero}</td>
        <td>${escapeHtml(a.contraparte)}</td>
        <td class="celda-texto">${escapeHtml(a.descripcion)}</td>
        <td>${a.nuevoFin || '—'}</td>
        <td>${a.fechaSuscripcion || '—'}</td>
        <td>${badgeAdenda(a.formalizada)}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="7" class="empty-state">No hay adendas para mostrar.</td></tr>';
}

document.querySelectorAll('#filtroAdendas a').forEach((tab) => {
  tab.addEventListener('click', (e) => {
    e.preventDefault();
    filtroAdenda = tab.dataset.filtro;
    document.querySelectorAll('#filtroAdendas a').forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    renderAdendas();
  });
});

(async function cargarAdendas() {
  try {
    const res = await fetch('/api/contratos/adendas');
    const data = await res.json();
    adendasCache = data.adendas;
    renderAdendas();
  } catch (err) {
    document.getElementById('tablaAdendas').innerHTML =
      '<tr><td colspan="7" class="empty-state">Error al cargar</td></tr>';
  }
}());
