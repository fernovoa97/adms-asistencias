// Formulario de orden de compra (nueva o edicion). Los totales y el monto
// en letras los calcula el servidor (montos.py) para que la vista previa
// sea identica a lo que se guarda e imprime.

const itemsBody = document.getElementById('itemsBody');
const campoNumero = document.getElementById('numeroOC');
const campoFecha = document.getElementById('fechaOC');
const campoMoneda = document.getElementById('monedaOC');
const campoRuc = document.getElementById('rucOC');
const errorMsg = document.getElementById('errorMsg');

let anioActual = Number(ORDEN.anio);
let temporizadorCalculo = null;
let ultimoCalculo = 0;

function formatearMonto(valor) {
  return Number(valor).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function simboloMoneda() {
  return MONEDAS[campoMoneda.value].simbolo;
}

// ---------- Items ----------

function renumerarItems() {
  itemsBody.querySelectorAll('tr').forEach((tr, i) => {
    tr.querySelector('.oc-num').textContent = i + 1;
  });
}

function agregarFila(item = {}) {
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td class="oc-col-item oc-num"></td>
    <td class="oc-col-cant"><input type="text" inputmode="decimal" class="it-cantidad" placeholder="0"></td>
    <td><textarea rows="1" class="it-descripcion" placeholder="Descripción del producto o servicio"></textarea></td>
    <td class="oc-col-monto"><input type="text" inputmode="decimal" class="it-valor num" placeholder="0.00"></td>
    <td class="oc-col-monto num it-total">0.00</td>
    <td class="oc-col-quitar"><button type="button" class="btn danger sm" title="Quitar ítem">✕</button></td>
  `;
  tr.querySelector('.it-cantidad').value = item.cantidad || '';
  tr.querySelector('.it-descripcion').value = item.descripcion || '';
  tr.querySelector('.it-valor').value = item.valor_unitario || '';

  const descripcion = tr.querySelector('.it-descripcion');
  const ajustarAlto = () => {
    descripcion.style.height = 'auto';
    descripcion.style.height = `${descripcion.scrollHeight + 2}px`;
  };
  descripcion.addEventListener('input', ajustarAlto);

  tr.querySelectorAll('.it-cantidad, .it-valor').forEach((input) => {
    input.addEventListener('input', programarCalculo);
  });
  tr.querySelector('.btn.danger').addEventListener('click', () => {
    tr.remove();
    if (!itemsBody.querySelector('tr')) agregarFila();
    renumerarItems();
    programarCalculo();
  });

  itemsBody.appendChild(tr);
  requestAnimationFrame(ajustarAlto);
  renumerarItems();
  return tr;
}

function leerItems() {
  return Array.from(itemsBody.querySelectorAll('tr')).map((tr) => ({
    cantidad: tr.querySelector('.it-cantidad').value.trim(),
    descripcion: tr.querySelector('.it-descripcion').value.trim(),
    valor_unitario: tr.querySelector('.it-valor').value.trim()
  }));
}

document.getElementById('agregarItem').addEventListener('click', () => {
  agregarFila().querySelector('.it-cantidad').focus();
});

// ---------- Totales ----------

function programarCalculo() {
  clearTimeout(temporizadorCalculo);
  temporizadorCalculo = setTimeout(calcular, 150);
}

async function calcular() {
  const idCalculo = ++ultimoCalculo;
  try {
    const res = await fetch('/api/ordenes-compra/calcular', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ moneda: campoMoneda.value, items: leerItems() })
    });
    const data = await res.json();
    if (idCalculo !== ultimoCalculo || !res.ok) return;

    const simbolo = simboloMoneda();
    itemsBody.querySelectorAll('tr').forEach((tr, i) => {
      tr.querySelector('.it-total').textContent = `${simbolo} ${formatearMonto(data.lineas[i] || 0)}`;
    });
    document.getElementById('valorVenta').textContent = `${simbolo} ${formatearMonto(data.valor_venta)}`;
    document.getElementById('igv').textContent = `${simbolo} ${formatearMonto(data.igv)}`;
    document.getElementById('total').textContent = `${simbolo} ${formatearMonto(data.total)}`;
    document.getElementById('etiquetaTotal').textContent = MONEDAS[campoMoneda.value].etiqueta_total;
    document.getElementById('totalLetras').textContent = data.total_letras;
  } catch (err) {
    // Sin conexion: se vuelve a calcular con el siguiente cambio.
  }
}

campoMoneda.addEventListener('change', calcular);

// ---------- Correlativo ----------

async function actualizarCorrelativoPorAnio() {
  const anio = Number((campoFecha.value || '').slice(0, 4));
  if (!anio || anio === anioActual) return;
  anioActual = anio;
  document.getElementById('prefijoOC').textContent = `ADM-${anio}-C`;

  // Al editar, si se vuelve al anio original se recupera el numero original.
  if (ORDEN.id && anio === Number(ORDEN.anio)) {
    campoNumero.value = ORDEN.numero;
    return;
  }
  try {
    const res = await fetch(`/api/ordenes-compra/siguiente?anio=${anio}`);
    const data = await res.json();
    if (res.ok && anio === anioActual) campoNumero.value = data.numero;
  } catch (err) {
    // Se deja el numero actual; el servidor avisa si esta repetido.
  }
}

campoFecha.addEventListener('change', actualizarCorrelativoPorAnio);

// ---------- Proveedor: buscador y autocompletar por RUC ----------

const campoBuscar = document.getElementById('buscarProveedor');
const cajaSugerencias = document.getElementById('sugerenciasProveedor');
const ayudaRuc = document.getElementById('ayudaRuc');
let temporizadorProveedor = null;
let sugerencias = [];
let sugerenciaActiva = -1;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function usarProveedor(p) {
  campoRuc.value = p.ruc;
  document.getElementById('proveedorOC').value = p.nombre;
  document.getElementById('direccionOC').value = p.direccion;
  ayudaRuc.textContent = 'Proveedor registrado: datos completados.';
  campoBuscar.value = '';
  cerrarSugerencias();
}

function cerrarSugerencias() {
  cajaSugerencias.hidden = true;
  cajaSugerencias.innerHTML = '';
  sugerencias = [];
  sugerenciaActiva = -1;
}

function marcarSugerencia(indice) {
  sugerenciaActiva = indice;
  cajaSugerencias.querySelectorAll('button').forEach((b, i) => b.classList.toggle('activa', i === indice));
}

async function buscarProveedores() {
  const q = campoBuscar.value.trim();
  if (q.length < 2) { cerrarSugerencias(); return; }
  try {
    const res = await fetch(`/api/proveedores?limite=8&q=${encodeURIComponent(q)}`);
    const data = await res.json();
    if (campoBuscar.value.trim() !== q) return;
    sugerencias = data.proveedores || [];
    sugerenciaActiva = -1;
    if (sugerencias.length === 0) {
      cajaSugerencias.innerHTML = '<div class="oc-sugerencia-vacia">Sin resultados: llénalo abajo y se registrará al guardar.</div>';
    } else {
      cajaSugerencias.innerHTML = sugerencias.map((p, i) => `
        <button type="button" data-i="${i}">
          <strong>${escapeHtml(p.nombre)}</strong>
          <span>RUC ${escapeHtml(p.ruc)}${p.direccion ? ' · ' + escapeHtml(p.direccion) : ''}</span>
        </button>`).join('');
    }
    cajaSugerencias.hidden = false;
  } catch (err) {
    cerrarSugerencias();
  }
}

campoBuscar.addEventListener('input', () => {
  clearTimeout(temporizadorProveedor);
  temporizadorProveedor = setTimeout(buscarProveedores, 200);
});

campoBuscar.addEventListener('keydown', (e) => {
  if (cajaSugerencias.hidden || sugerencias.length === 0) {
    if (e.key === 'Enter') e.preventDefault();
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    marcarSugerencia((sugerenciaActiva + 1) % sugerencias.length);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    marcarSugerencia((sugerenciaActiva - 1 + sugerencias.length) % sugerencias.length);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    usarProveedor(sugerencias[Math.max(sugerenciaActiva, 0)]);
  } else if (e.key === 'Escape') {
    cerrarSugerencias();
  }
});

// mousedown para elegir antes de que el blur cierre la lista
cajaSugerencias.addEventListener('mousedown', (e) => {
  const boton = e.target.closest('button[data-i]');
  if (!boton) return;
  e.preventDefault();
  usarProveedor(sugerencias[Number(boton.dataset.i)]);
});

campoBuscar.addEventListener('blur', () => setTimeout(cerrarSugerencias, 100));

campoRuc.addEventListener('input', async () => {
  campoRuc.value = campoRuc.value.replace(/\D/g, '').slice(0, 11);
  ayudaRuc.textContent = '';
  if (campoRuc.value.length !== 11) return;
  const ruc = campoRuc.value;

  try {
    const res = await fetch(`/api/proveedores/ruc/${ruc}`);
    const data = await res.json();
    if (campoRuc.value !== ruc) return;
    if (data.proveedor) {
      document.getElementById('proveedorOC').value = data.proveedor.nombre;
      document.getElementById('direccionOC').value = data.proveedor.direccion;
      ayudaRuc.textContent = 'Proveedor registrado: datos completados.';
    } else {
      ayudaRuc.textContent = 'RUC nuevo: se registrará al guardar la orden.';
    }
  } catch (err) {
    // Sin autocompletado; se llena a mano.
  }
});

// ---------- Guardar ----------

function mostrarError(texto) {
  errorMsg.textContent = texto;
  errorMsg.style.display = 'block';
  errorMsg.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

document.getElementById('ordenForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  errorMsg.style.display = 'none';

  const datos = {
    numero: campoNumero.value.trim(),
    fecha: campoFecha.value,
    moneda: campoMoneda.value,
    proveedor_ruc: campoRuc.value.trim(),
    proveedor_nombre: document.getElementById('proveedorOC').value.trim(),
    proveedor_direccion: document.getElementById('direccionOC').value.trim(),
    items: leerItems(),
    forma_pago: document.getElementById('formaPagoOC').value.trim(),
    autorizado_por: document.getElementById('autorizadoOC').value.trim(),
    nota: document.getElementById('notaOC').value.trim(),
    entrega: document.getElementById('entregaOC').value.trim(),
    atencion: document.getElementById('atencionOC').value.trim(),
    observaciones: document.getElementById('observacionesOC').value.trim()
  };

  const boton = document.getElementById('guardarBtn');
  boton.disabled = true;
  try {
    const res = await fetch(ORDEN.id ? `/api/ordenes-compra/${ORDEN.id}` : '/api/ordenes-compra', {
      method: ORDEN.id ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(datos)
    });
    const data = await res.json();
    if (!res.ok) {
      mostrarError(data.error || 'No se pudo guardar la orden de compra');
      return;
    }
    window.location.href = `/ordenes-compra/${data.id}`;
  } catch (err) {
    mostrarError('Error de conexión con el servidor');
  } finally {
    boton.disabled = false;
  }
});

// ---------- Inicio ----------

if (ORDEN.items && ORDEN.items.length) {
  ORDEN.items.forEach((item) => agregarFila(item));
} else {
  agregarFila();
}
calcular();
