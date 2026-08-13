let rowCount = 0;

function createUploadRow() {
  rowCount += 1;
  const rowId = `row_${rowCount}`;

  const wrapper = document.createElement('div');
  wrapper.className = 'upload-row';
  wrapper.dataset.rowId = rowId;

  wrapper.innerHTML = `
    <input type="text" placeholder="Nombre del documento (ej. DNI, Contrato)" class="doc-label-input">
    <label class="btn secondary" style="cursor:pointer;">
      Elegir PDF
      <input type="file" accept="application/pdf" class="doc-file-input" style="display:none;">
    </label>
    <span class="file-name">Ningún archivo seleccionado</span>
    <button type="button" class="btn secondary preview-btn" style="display:none;">Vista previa</button>
    <button type="button" class="btn danger remove-row-btn">Quitar</button>
  `;

  const fileInput = wrapper.querySelector('.doc-file-input');
  const fileNameSpan = wrapper.querySelector('.file-name');
  const previewBtn = wrapper.querySelector('.preview-btn');
  const removeBtn = wrapper.querySelector('.remove-row-btn');
  const labelInput = wrapper.querySelector('.doc-label-input');

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) {
      fileNameSpan.textContent = file.name;
      previewBtn.style.display = 'inline-block';
      if (!labelInput.value.trim()) {
        labelInput.value = file.name.replace(/\.pdf$/i, '');
      }
    } else {
      fileNameSpan.textContent = 'Ningún archivo seleccionado';
      previewBtn.style.display = 'none';
    }
    clearPreview(rowId);
  });

  previewBtn.addEventListener('click', () => {
    const file = fileInput.files[0];
    if (!file) return;
    togglePreview(rowId, file);
  });

  removeBtn.addEventListener('click', () => {
    clearPreview(rowId);
    wrapper.remove();
  });

  document.getElementById('uploadRows').appendChild(wrapper);
}

function togglePreview(rowId, file) {
  const previewArea = document.getElementById('previewArea');
  const existing = document.getElementById(`preview_${rowId}`);
  if (existing) {
    existing.remove();
    return;
  }
  const url = URL.createObjectURL(file);
  const div = document.createElement('div');
  div.className = 'pdf-preview-wrap';
  div.id = `preview_${rowId}`;
  div.innerHTML = `<iframe src="${url}"></iframe>`;
  previewArea.appendChild(div);
}

function clearPreview(rowId) {
  const existing = document.getElementById(`preview_${rowId}`);
  if (existing) existing.remove();
}

document.getElementById('addFileBtn').addEventListener('click', createUploadRow);
createUploadRow();

// Vista previa de la foto de perfil al elegirla
document.getElementById('foto').addEventListener('change', (e) => {
  const file = e.target.files[0];
  const preview = document.getElementById('avatarPreview');
  if (!file) return;
  const url = URL.createObjectURL(file);
  preview.innerHTML = `<img src="${url}" alt="Vista previa">`;
});

// Mientras no se elija foto, mostrar las iniciales del nombre que se va escribiendo
function actualizarIniciales() {
  const preview = document.getElementById('avatarPreview');
  if (preview.querySelector('img')) return; // ya hay foto elegida, no pisar
  const nombres = document.getElementById('nombres').value.trim();
  const inicial = nombres ? nombres[0].toUpperCase() : '?';
  preview.innerHTML = `<span id="avatarPreviewIniciales">${inicial}</span>`;
}
document.getElementById('nombres').addEventListener('input', actualizarIniciales);

document.getElementById('workerForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const errorMsg = document.getElementById('errorMsg');
  const successMsg = document.getElementById('successMsg');
  errorMsg.style.display = 'none';
  successMsg.style.display = 'none';

  const formData = new FormData();
  formData.append('nombres', document.getElementById('nombres').value.trim());
  formData.append('apellidos', document.getElementById('apellidos').value.trim());
  formData.append('dni', document.getElementById('dni').value.trim());
  formData.append('telefono', document.getElementById('telefono').value.trim());
  formData.append('email', document.getElementById('email').value.trim());
  const fotoInput = document.getElementById('foto');
  if (fotoInput.files[0]) {
    formData.append('foto', fotoInput.files[0]);
  }
  formData.append('emailCorporativo', document.getElementById('emailCorporativo').value.trim());
  formData.append('fechaIngreso', document.getElementById('fechaIngreso').value);
  formData.append('fechaNacimiento', document.getElementById('fechaNacimiento').value);
  formData.append('fechaFinContrato', document.getElementById('fechaFinContrato').value);
  formData.append('fechaRenovacion', document.getElementById('fechaRenovacion').value);
  formData.append('cargo', document.getElementById('cargo').value.trim());
  formData.append('area', document.getElementById('area').value.trim());
  formData.append('supervisor', document.getElementById('supervisor').value.trim());
  formData.append('sueldoNeto', document.getElementById('sueldoNeto').value);
  formData.append('direccion', document.getElementById('direccion').value.trim());
  formData.append('observaciones', document.getElementById('observaciones').value.trim());

  const rows = document.querySelectorAll('#uploadRows .upload-row');
  const docNombres = [];
  rows.forEach((row) => {
    const fileInput = row.querySelector('.doc-file-input');
    const labelInput = row.querySelector('.doc-label-input');
    const file = fileInput.files[0];
    if (file) {
      formData.append('documentos', file);
      docNombres.push(labelInput.value.trim() || file.name);
    }
  });
  formData.append('documentosNombres', JSON.stringify(docNombres));

  const submitBtn = document.getElementById('submitBtn');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Guardando...';

  try {
    const res = await fetch('/api/trabajadores', { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || 'No se pudo guardar el trabajador';
      errorMsg.style.display = 'block';
      return;
    }

    successMsg.textContent = `Trabajador "${data.worker.nombres} ${data.worker.apellidos}" guardado correctamente.`;
    successMsg.style.display = 'block';
    document.getElementById('workerForm').reset();
    document.getElementById('uploadRows').innerHTML = '';
    document.getElementById('previewArea').innerHTML = '';
    document.getElementById('avatarPreview').innerHTML = '<span id="avatarPreviewIniciales">?</span>';
    createUploadRow();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } catch (err) {
    errorMsg.textContent = 'Error de conexión con el servidor';
    errorMsg.style.display = 'block';
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Guardar trabajador';
  }
});
