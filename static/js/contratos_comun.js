// Utilidades compartidas por las pantallas del modulo de contratos.

const ESTADOS_CONTRATO = {
  vigente: { texto: 'Vigente', clase: 'doc-vigente' },
  por_vencer: { texto: 'Por vencer', clase: 'doc-por-vencer' },
  vencido: { texto: 'Vencido', clase: 'doc-vencido' },
  finalizado: { texto: 'Finalizado', clase: 'doc-reemplazado' }
};

const TAMANO_MAXIMO_PDF_CONTRATO = 25 * 1024 * 1024;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function badgeContrato(estado) {
  const info = ESTADOS_CONTRATO[estado];
  return `<span class="badge ${info.clase}">${info.texto}</span>`;
}

function badgeAdenda(formalizada) {
  return formalizada
    ? '<span class="badge doc-vigente">Formalizada</span>'
    : '<span class="badge doc-por-vencer">Pendiente</span>';
}

function textoImporte(importe, moneda) {
  if (importe === null) return '—';
  const simbolo = moneda === 'USD' ? 'US$' : 'S/';
  return `${simbolo} ${importe.toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function textoDias(dias) {
  if (dias === null) return '';
  if (dias < 0) return `venció hace ${Math.abs(dias)} día(s)`;
  return dias === 0 ? 'vence hoy' : `vence en ${dias} día(s)`;
}

function hoyIso() {
  return new Date().toLocaleDateString('en-CA');
}

function errorDeArchivoPdf(archivo) {
  if (!archivo.name.toLowerCase().endsWith('.pdf')) return 'El archivo debe ser un PDF';
  if (archivo.size > TAMANO_MAXIMO_PDF_CONTRATO) return 'El archivo supera los 25MB';
  return null;
}

// Devuelve null si salio bien, o el mensaje de error.
async function subirPdf(url, archivo) {
  const formData = new FormData();
  formData.append('archivo', archivo);
  try {
    const res = await fetch(url, { method: 'POST', body: formData });
    const data = await res.json();
    return res.ok ? null : (data.error || 'No se pudo subir el PDF');
  } catch (err) {
    return 'Error de conexión con el servidor';
  }
}

async function enviarJson(url, metodo, cuerpo) {
  const res = await fetch(url, {
    method: metodo,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cuerpo || {})
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'No se pudo completar la operación');
  return data;
}
