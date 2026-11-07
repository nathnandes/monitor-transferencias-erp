

export function codigoItem(idProduto: string, idSubproduto: string | null): string {
  return idSubproduto ?? idProduto;
}

export function CodigoProduto({ idProduto, idSubproduto }: { idProduto: string; idSubproduto: string | null }) {
  const codigo = codigoItem(idProduto, idSubproduto);
  return (
    <>
      <span className="whitespace-nowrap font-semibold text-texto">{codigo}</span>
      {codigo !== idProduto && (
        <span className="whitespace-nowrap text-xs text-texto-mudo" title={`Variação da grade ${idProduto}`}>
          {" "}
          · grade {idProduto}
        </span>
      )}
    </>
  );
}
