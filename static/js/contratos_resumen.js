function enlaceContrato(c) {
  return `<a href="/contratos/${c.id}">${escapeHtml(c.numero)}</a>`;
}

function grupoAlertaHtml(titulo, filas) {
  if (filas.length === 0) return '';
  return `
    <section class="panel">
      <h3>${titulo} (${filas.length})</h3>
      <div class="alerta-filas">${filas.join('')}</div>
    </section>
  `;
}

function filaVencimiento(c) {
  return `
    <div class="estado-fila">
      <span>${enlaceContrato(c)} · ${escapeHtml(c.contraparteNombre)} <span class="muted">· ${escapeHtml(c.categoria)} · ${c.finEfectivo}</span></span>
      <span class="estado-acciones"><span class="muted">${textoDias(c.diasRestantes)}</span>${badgeContrato(c.estado)}</span>
    </div>
  `;
}

function renderAlertas({ proximos, polizas, documentacion, adendas, vencidos }) {
  const grupos = [
    grupoAlertaHtml('Vencidos por regularizar', vencidos.map(filaVencimiento)),
    grupoAlertaHtml('Vencen en 30 días o menos', proximos['30'].map(filaVencimiento)),
    grupoAlertaHtml('Vencen en 31 a 60 días', proximos['60'].map(filaVencimiento)),
    grupoAlertaHtml('Vencen en 61 a 90 días', proximos['90'].map(filaVencimiento)),
    grupoAlertaHtml('Pólizas próximas a renovación', polizas.map(filaVencimiento)),
    grupoAlertaHtml('Sin firma o con documentación pendiente', documentacion.map((c) => `
      <div class="estado-fila">
        <span>${enlaceContrato(c)} · ${escapeHtml(c.contraparteNombre)}</span>
        <span class="badge doc-por-vencer">${c.pendiente.join(' y ')}</span>
      </div>
    `)),
    grupoAlertaHtml('Adendas pendientes de formalización', adendas.map((a) => `
      <div class="estado-fila">
        <span><a href="/contratos/${a.contratoId}">${escapeHtml(a.contratoNumero)}</a> · ${escapeHtml(a.tipo)} N.º ${a.numero} · ${escapeHtml(a.contraparte)}</span>
        <span class="badge doc-por-vencer">falta ${a.falta.join(' y ')}</span>
      </div>
    `))
  ].join('');

  document.getElementById('alertasContratos').innerHTML = grupos
    || '<div class="panel empty-state">No hay alertas pendientes.</div>';
}

function renderModulos(porModulo) {
  document.getElementById('tablaModulos').innerHTML = CONTRATOS_CONFIG.ordenModulos
    .map((clave) => {
      const info = CONTRATOS_CONFIG.modulos[clave];
      const c = porModulo[clave];
      return `
        <tr>
          <td><a href="/contratos/modulo/${clave}">${info.nombre}</a></td>
          <td>${info.area}</td>
          <td>${c.vigente}</td>
          <td>${c.por_vencer}</td>
          <td>${c.vencido}</td>
          <td>${c.finalizado}</td>
        </tr>
      `;
    }).join('');
}

(async function cargarResumen() {
  try {
    const res = await fetch('/api/contratos/resumen');
    const data = await res.json();
    document.getElementById('totalVigentes').textContent = data.totales.vigente;
    document.getElementById('totalPorVencer').textContent = data.totales.por_vencer;
    document.getElementById('totalVencidos').textContent = data.totales.vencido;
    document.getElementById('totalFinalizados').textContent = data.totales.finalizado;
    renderModulos(data.porModulo);
    renderAlertas(data.alertas);
  } catch (err) {
    document.getElementById('alertasContratos').innerHTML = '<div class="empty-state">Error al cargar</div>';
  }
}());
