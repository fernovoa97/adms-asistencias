// Reglas de los campos del contrato, compartidas por "Nuevo trabajador" y por
// la tarjeta "Actualizar contrato" de la ficha.
//   campos = { tipo, tiempo, meses, mesesCampo, fechaFin, raiz }
// "raiz" es el contenedor donde estan los asteriscos [data-obligatorio].

const CONTRATO_INDETERMINADO = 'Indeterminado';
const TIEMPO_OTRO = 'Otro';
const MAXIMO_MESES_RENOVACION = 120;

function contratoExigeFechas(tipo) {
  return Boolean(tipo) && tipo !== CONTRATO_INDETERMINADO;
}

// Devuelve una funcion para volver a aplicar las reglas (ej. tras un reset).
function enlazarCamposContrato(campos) {
  const actualizar = () => {
    const exige = contratoExigeFechas(campos.tipo.value);
    const esOtro = campos.tiempo.value === TIEMPO_OTRO;

    campos.tiempo.required = exige;
    campos.fechaFin.required = exige;
    campos.raiz.querySelectorAll('[data-obligatorio]').forEach((marca) => {
      marca.hidden = !exige;
    });

    campos.mesesCampo.hidden = !esOtro;
    campos.meses.required = esOtro;
  };

  campos.tipo.addEventListener('change', actualizar);
  campos.tiempo.addEventListener('change', actualizar);
  actualizar();
  return actualizar;
}

function errorDeContrato(campos, tipoObligatorio) {
  const tipo = campos.tipo.value;

  if (tipoObligatorio && !tipo) return 'Selecciona el tipo de contrato';
  if (contratoExigeFechas(tipo)) {
    if (!campos.tiempo.value) return 'Selecciona el tiempo de renovación';
    if (!campos.fechaFin.value) return 'La fecha de fin de contrato es obligatoria';
  }
  if (campos.tiempo.value === TIEMPO_OTRO) {
    const meses = Number(campos.meses.value);
    if (!Number.isInteger(meses) || meses < 1 || meses > MAXIMO_MESES_RENOVACION) {
      return `Indica la cantidad de meses (de 1 a ${MAXIMO_MESES_RENOVACION})`;
    }
  }
  return null;
}
