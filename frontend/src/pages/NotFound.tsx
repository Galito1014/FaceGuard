import { Link } from "react-router-dom";
import { Ban, Compass } from "lucide-react";
import { EmptyState } from "@/components/ui";

export default function NotFoundPage({ forbidden }: { forbidden?: boolean }) {
  return (
    <div className="panel mx-auto mt-10 max-w-lg p-6">
      <EmptyState
        icon={forbidden ? Ban : Compass}
        title={forbidden ? "Acceso restringido" : "Página no encontrada"}
        text={forbidden ? "Su rol no tiene permisos para ver esta sección." : "La dirección solicitada no existe."}
      />
      <div className="text-center">
        <Link to="/" className="text-sm font-medium text-volt-400 hover:text-volt-300">Volver al dashboard</Link>
      </div>
    </div>
  );
}
