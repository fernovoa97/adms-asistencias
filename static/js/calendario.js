const modalOverlay = document.getElementById('eventoModalOverlay');
const eventoForm = document.getElementById('eventoForm');
const eventoModalTitulo = document.getElementById('eventoModalTitulo');
const eventoIdInput = document.getElementById('eventoId');
const eventoTituloInput = document.getElementById('eventoTitulo');
const eventoFechaInput = document.getElementById('eventoFecha');
const eventoHoraInput = document.getElementById('eventoHora');
const eventoDescripcionInput = document.getElementById('eventoDescripcion');
const eventoColorInput = document.getElementById('eventoColor');
const eventoEliminarBtn = document.getElementById('eventoEliminarBtn');
const eventoErrorMsg = document.getElementById('eventoErrorMsg');

function seleccionarColor(color) {
  eventoColorInput.value = color;
  document.querySelectorAll('.color-swatch').forEach((btn) => {
    btn.classList.toggle('selected', btn.dataset.color === color);
  });
}

function abrirModalNuevo(fecha) {
  eventoForm.reset();
  eventoIdInput.value = '';
  eventoModalTitulo.textContent = 'Nuevo evento';
  eventoEliminarBtn.style.display = 'none';
  eventoErrorMsg.style.display = 'none';
  eventoFechaInput.value = fecha || '';
  seleccionarColor(document.querySelector('.color-swatch').dataset.color);
  modalOverlay.style.display = 'flex';
  eventoTituloInput.focus();
}

function abrirModalEditar(datos) {
  eventoForm.reset();
  eventoIdInput.value = datos.id;
  eventoModalTitulo.textContent = 'Editar evento';
  eventoEliminarBtn.style.display = 'inline-block';
  eventoErrorMsg.style.display = 'none';
  eventoTituloInput.value = datos.titulo;
  eventoFechaInput.value = datos.fecha;
  eventoHoraInput.value = datos.hora || '';
  eventoDescripcionInput.value = datos.descripcion || '';
  seleccionarColor(datos.color);
  modalOverlay.style.display = 'flex';
}

function cerrarModal() {
  modalOverlay.style.display = 'none';
}

document.querySelectorAll('.color-swatch').forEach((btn) => {
  btn.addEventListener('click', () => seleccionarColor(btn.dataset.color));
});

document.getElementById('btnNuevoEvento').addEventListener('click', () => abrirModalNuevo());

document.querySelectorAll('.dia-add-btn').forEach((btn) => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const celda = btn.closest('[data-fecha]');
    abrirModalNuevo(celda.dataset.fecha);
  });
});

document.querySelectorAll('.evento-chip').forEach((chip) => {
  chip.addEventListener('click', (e) => {
    e.stopPropagation();
    abrirModalEditar({
      id: chip.dataset.id,
      titulo: chip.dataset.titulo,
      descripcion: chip.dataset.descripcion,
      fecha: chip.dataset.fecha,
      hora: chip.dataset.hora,
      color: chip.dataset.color
    });
  });
});

document.getElementById('eventoCancelarBtn').addEventListener('click', cerrarModal);

modalOverlay.addEventListener('click', (e) => {
  if (e.target === modalOverlay) cerrarModal();
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && modalOverlay.style.display === 'flex') cerrarModal();
});

eventoForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  eventoErrorMsg.style.display = 'none';

  const payload = {
    titulo: eventoTituloInput.value.trim(),
    fecha: eventoFechaInput.value,
    hora: eventoHoraInput.value,
    color: eventoColorInput.value,
    descripcion: eventoDescripcionInput.value.trim()
  };

  const id = eventoIdInput.value;
  const url = id ? `/api/eventos/${id}` : '/api/eventos';
  const method = id ? 'PUT' : 'POST';

  const submitBtn = eventoForm.querySelector('button[type="submit"]');
  submitBtn.disabled = true;

  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      eventoErrorMsg.textContent = data.error || 'No se pudo guardar el evento';
      eventoErrorMsg.style.display = 'block';
      return;
    }

    window.location.reload();
  } catch (err) {
    eventoErrorMsg.textContent = 'Error de conexión con el servidor';
    eventoErrorMsg.style.display = 'block';
  } finally {
    submitBtn.disabled = false;
  }
});

eventoEliminarBtn.addEventListener('click', async () => {
  const id = eventoIdInput.value;
  if (!id) return;
  if (!confirm('¿Eliminar este evento? Esta acción no se puede deshacer.')) return;

  try {
    const res = await fetch(`/api/eventos/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('No se pudo eliminar el evento');
      return;
    }
    window.location.reload();
  } catch (err) {
    alert('Error de conexión con el servidor');
  }
});
