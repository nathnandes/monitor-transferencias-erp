

const DATA_ISO = /^\d{4}-\d{2}-\d{2}$/;


export function ehDataValida(valor: string): boolean {
  if (!DATA_ISO.test(valor)) return false;
  const data = new Date(`${valor}T00:00:00Z`);
  return !Number.isNaN(data.getTime()) && data.toISOString().slice(0, 10) === valor;
}


export function validarIntervalo(dataInicial: string, dataFinal: string): string | null {
  if (dataInicial && !ehDataValida(dataInicial)) return "Data inicial inválida.";
  if (dataFinal && !ehDataValida(dataFinal)) return "Data final inválida.";
  if (dataInicial && dataFinal && dataInicial > dataFinal) {
    return "A data inicial não pode ser posterior à data final.";
  }
  return null;
}
