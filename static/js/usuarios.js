// Gestion de usuarios y roles (solo Administracion).

let rolesDisponibles = {};

const linkCompras = document.getElementById('linkCompras');
linkCompras.textContent = `${window.location.origin}${linkCompras.getAttribute('href')}`;

document.getElementById('copiarLink').addEventListener('click', async (e) => {
  try {
    await navigator.clipboard.writeText(linkCompras.textContent);
    e.target.textContent = 'Copiado';
    setTimeout(() => { e.target.textContent = 'Copiar link'; }, 1500);
  } catch (err) {
    window.getSelection().selectAllChildren(linkCompras);
  }
});

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function mostrarError(id, texto) {
  const caja = document.getElementById(id);
  caja.textContent = texto;
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

async function cargarUsuarios() {
  const body = document.getElementById('usuariosBody');
  try {
    const res = await fetch('/api/usuarios');
    const data = await res.json();
    rolesDisponibles = data.roles || {};
    renderUsuarios(data.usuarios || []);
  } catch (err) {
    body.innerHTML = '<tr><td colspan="4" class="empty-state">Error al cargar los usuarios</td></tr>';
  }
}

function renderUsuarios(usuarios) {
  const body = document.getElementById('usuariosBody');
  body.innerHTML = '';
  usuarios.forEach((u) => {
    const opciones = Object.entries(rolesDisponibles)
      .map(([codigo, nombre]) => `<option value="${codigo}" ${codigo === u.rol ? 'selected' : ''}>${escapeHtml(nombre)}</option>`)
      .join('');
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="celda-nombre"><strong>${escapeHtml(u.username)}</strong>${u.esYo ? ' <span class="tag tag-info">tú</span>' : ''}</td>
      <td><select class="usuarios-rol">${opciones}</select></td>
      <td>
        <div class="campo-con-boton">
          <input type="password" class="usuarios-clave" placeholder="Dejar vacío para no cambiar" autocomplete="new-password">
          <button type="button" class="btn secondary sm btn-clave">Cambiar</button>
        </div>
      </td>
      <td style="text-align:right;">
        ${u.esYo ? '' : '<button type="button" class="btn danger sm btn-eliminar">Eliminar</button>'}
      </td>
    `;

    const selectRol = tr.querySelector('.usuarios-rol');
    selectRol.addEventListener('change', async () => {
      mostrarError('errorLista', '');
      try {
        await enviar(`/api/usuarios/${u.id}`, 'PUT', { rol: selectRol.value });
        u.rol = selectRol.value;
        if (u.esYo && selectRol.value !== 'admin') {
          window.location.href = '/ordenes-compra';
        }
      } catch (err) {
        selectRol.value = u.rol;
        mostrarError('errorLista', err.message);
      }
    });

    const campoClave = tr.querySelector('.usuarios-clave');
    tr.querySelector('.btn-clave').addEventListener('click', async (e) => {
      mostrarError('errorLista', '');
      if (!campoClave.value) {
        mostrarError('errorLista', `Escribe la nueva contraseña de ${u.username}`);
        return;
      }
      try {
        await enviar(`/api/usuarios/${u.id}`, 'PUT', { password: campoClave.value });
        campoClave.value = '';
        e.target.textContent = 'Guardada';
        setTimeout(() => { e.target.textContent = 'Cambiar'; }, 1500);
      } catch (err) {
        mostrarError('errorLista', err.message);
      }
    });

    const botonEliminar = tr.querySelector('.btn-eliminar');
    if (botonEliminar) {
      botonEliminar.addEventListener('click', async () => {
        if (!confirm(`¿Eliminar el usuario ${u.username}? Ya no podrá iniciar sesión.`)) return;
        mostrarError('errorLista', '');
        try {
          await enviar(`/api/usuarios/${u.id}`, 'DELETE');
          cargarUsuarios();
        } catch (err) {
          mostrarError('errorLista', err.message);
        }
      });
    }

    body.appendChild(tr);
  });
}

document.getElementById('nuevoUsuarioForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  mostrarError('errorNuevo', '');
  try {
    await enviar('/api/usuarios', 'POST', {
      username: document.getElementById('nuevoUsername').value.trim(),
      password: document.getElementById('nuevoPassword').value,
      rol: document.getElementById('nuevoRol').value
    });
    e.target.reset();
    document.getElementById('nuevoRol').value = 'logistica';
    cargarUsuarios();
  } catch (err) {
    mostrarError('errorNuevo', err.message);
  }
});

cargarUsuarios();
