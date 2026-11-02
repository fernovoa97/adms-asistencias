// Formulario de la ficha del contrato (modal), para crear y para editar.

let contratoFormEstado = null; // { modulo, contrato, alGuardar }

function campoContrato(id) {
  return document.getElementById(id);
}

async function cargarTrabajadoresContrato(seleccionado) {
  const select = campoContrato('cfTrabajador');
  select.innerHTML = '<option value="">Sin vincular</option>';
  try {
    const res = await fetch('/api/trabajadores/buscar?q=');
    const data = await res.json();
    (data.results || []).forEach((t) => {
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = `${t.apellidos} ${t.nombres}`;
      opt.dataset.nombre = opt.textContent;
      select.appendChild(opt);
    });
    select.value = seleccionado || '';
  } catch (err) {
    // sin lista se puede guardar igual, solo queda sin vincular
  }
}

function abrirFormularioContrato({ modulo, contrato, inicial, alGuardar }) {
  contratoFormEstado = { modulo, contrato, alGuardar };
  const valores = contrato || inicial || {};

  campoContrato('contratoModalTitulo').textContent = contrato ? `Editar ${contrato.numero}` : 'Nuevo contrato';
  campoContrato('contratoFormError').style.display = 'none';
  campoContrato('cfCategoria').innerHTML = '<option value="">Selecciona...</option>'
    + CONTRATOS_CONFIG.modulos[modulo].categorias.map((c) => `<option value="${c}">${c}</option>`).join('');

  campoContrato('cfCategoria').value = valores.categoria || '';
  campoContrato('cfContraparte').value = valores.contraparteNombre || '';
  campoContrato('cfRuc').value = valores.contraparteRuc || '';
  campoContrato('cfObjeto').value = valores.objeto || '';
  campoContrato('cfSuscripcion').value = valores.fechaSuscripcion || '';
  campoContrato('cfResponsable').value = valores.responsable || '';
  campoContrato('cfInicio').value = valores.inicioVigencia || '';
  campoContrato('cfFin').value = valores.finVigencia || '';
  campoContrato('cfImporte').value = valores.importe ?? '';
  campoContrato('cfMoneda').value = valores.moneda || 'PEN';
  campoContrato('cfPdf').value = '';
  campoContrato('cfPdfEtiqueta').textContent = contrato && contrato.tieneDocumento
    ? 'Reemplazar contrato firmado (PDF)'
    : 'Contrato firmado (PDF)';

  const esLaboral = modulo === 'laborales';
  campoContrato('cfTrabajadorCampo').hidden = !esLaboral;
  if (esLaboral) cargarTrabajadoresContrato(valores.trabajadorId);

  campoContrato('contratoModalOverlay').style.display = 'flex';
}

function validarFormularioContrato(datos, archivo) {
  if (!datos.categoria) return 'Selecciona la categoría';
  if (!datos.contraparteNombre) return 'La empresa o contraparte es obligatoria';
  if (datos.contraparteRuc && !/^\d{11}$/.test(datos.contraparteRuc)) return 'El RUC debe tener 11 dígitos';
  if (!datos.objeto) return 'El objeto del contrato es obligatorio';
  if (!datos.responsable) return 'El responsable interno es obligatorio';
  if (!datos.inicioVigencia) return 'El inicio de vigencia es obligatorio';
  if (datos.finVigencia && datos.finVigencia < datos.inicioVigencia) {
    return 'El fin de vigencia no puede ser anterior al inicio';
  }
  return archivo ? errorDeArchivoPdf(archivo) : null;
}

(function bindContratoModal() {
  const overlay = campoContrato('contratoModalOverlay');

  campoContrato('contratoCancelarBtn').addEventListener('click', () => {
    overlay.style.display = 'none';
  });

  // Al elegir colaborador, se propone su nombre como contraparte.
  campoContrato('cfTrabajador').addEventListener('change', (e) => {
    const opcion = e.target.selectedOptions[0];
    if (opcion.value && !campoContrato('cfContraparte').value.trim()) {
      campoContrato('cfContraparte').value = opcion.dataset.nombre;
    }
  });

  campoContrato('contratoGuardarBtn').addEventListener('click', async () => {
    const { modulo, contrato, alGuardar } = contratoFormEstado;
    const errorMsg = campoContrato('contratoFormError');
    const mostrarError = (texto) => {
      errorMsg.textContent = texto;
      errorMsg.style.display = 'block';
    };
    errorMsg.style.display = 'none';

    const datos = {
      modulo,
      categoria: campoContrato('cfCategoria').value,
      trabajadorId: modulo === 'laborales' ? campoContrato('cfTrabajador').value : null,
      contraparteNombre: campoContrato('cfContraparte').value.trim(),
      contraparteRuc: campoContrato('cfRuc').value.trim(),
      objeto: campoContrato('cfObjeto').value.trim(),
      fechaSuscripcion: campoContrato('cfSuscripcion').value,
      responsable: campoContrato('cfResponsable').value.trim(),
      inicioVigencia: campoContrato('cfInicio').value,
      finVigencia: campoContrato('cfFin').value,
      importe: campoContrato('cfImporte').value,
      moneda: campoContrato('cfMoneda').value
    };
    const archivo = campoContrato('cfPdf').files[0];

    const problema = validarFormularioContrato(datos, archivo);
    if (problema) {
      mostrarError(problema);
      return;
    }

    const btn = campoContrato('contratoGuardarBtn');
    btn.disabled = true;
    btn.textContent = 'Guardando...';

    try {
      const data = contrato
        ? await enviarJson(`/api/contratos/${contrato.id}`, 'PUT', datos)
        : await enviarJson('/api/contratos', 'POST', datos);

      // El contrato ya quedo guardado: si falla el PDF se puede subir luego
      // desde su ficha, sin duplicar el registro.
      if (archivo) {
        const errorSubida = await subirPdf(`/api/contratos/${data.id}/documento`, archivo);
        if (errorSubida) alert(`El contrato se guardó, pero el PDF no: ${errorSubida}`);
      }

      overlay.style.display = 'none';
      alGuardar(data.id);
    } catch (err) {
      mostrarError(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Guardar contrato';
    }
  });
}());
