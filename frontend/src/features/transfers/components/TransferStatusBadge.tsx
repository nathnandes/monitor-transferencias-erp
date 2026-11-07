import { StatusBadge } from "../../../components/ui/StatusBadge";
import { normalizarStatus, tomDoStatus } from "../../../lib/status";


export function TransferStatusBadge({ status }: { status: string | null | undefined }) {
  return <StatusBadge tom={tomDoStatus(status)}>{normalizarStatus(status)}</StatusBadge>;
}
