import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ScanSearch, ImageUp, Siren, TriangleAlert } from "lucide-react";
import { postForm } from "@/lib/api";
import { fmtScore } from "@/lib/format";
import type { AnalysisFace, AnalysisResult } from "@/lib/types";
import { Badge, Button, Card, ErrorNote, PageHeader } from "@/components/ui";

const RESULT: Record<AnalysisFace["result"], { label: string; tone: "red" | "green" | "amber" | "slate"; border: string }> = {
  posible_no_autorizada: { label: "Posible coincidencia con una persona no autorizada", tone: "red", border: "border-alert-400" },
  autorizada: { label: "Coincidencia con una persona autorizada", tone: "green", border: "border-ok-400" },
  desconocida: { label: "Persona desconocida", tone: "slate", border: "border-ink-200" },
  calidad_insuficiente: { label: "Calidad de imagen insuficiente", tone: "amber", border: "border-warn-400" },
};

export default function AnalysisPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const analyze = useMutation({
    mutationFn: () => {
      const f = new FormData();
      f.set("photo", file!);
      return postForm<AnalysisResult>("/api/analysis/photo", f);
    },
  });

  const pick = (next: File | undefined) => {
    if (!next) return;
    setFile(next);
    setPreview(URL.createObjectURL(next));
    analyze.reset();
  };

  const result = analyze.data;
  return (
    <>
      <PageHeader title="Analizar fotografía" icon={ScanSearch}
        subtitle="Compara los rostros de una imagen con las personas registradas. La fotografía no se guarda ni registra a nadie." />
      <div className="grid gap-4 xl:grid-cols-5">
        <Card title="Fotografía" icon={ImageUp} className="xl:col-span-3" bodyClass="p-3">
          <label className="grid min-h-[280px] cursor-pointer place-items-center overflow-hidden rounded-lg border-2 border-dashed border-ink-600 bg-ink-900 transition hover:border-volt-500/60">
            {preview ? (
              <span className="relative inline-block max-w-full">
                <img src={preview} alt="Fotografía seleccionada" className="block max-h-[520px] max-w-full" />
                {result?.faces.map((face, i) => (
                  <span key={i} className={`absolute border-2 ${RESULT[face.result].border}`} style={{
                    left: `${(face.box[0] / result.image.width) * 100}%`, top: `${(face.box[1] / result.image.height) * 100}%`,
                    width: `${(face.box[2] / result.image.width) * 100}%`, height: `${(face.box[3] / result.image.height) * 100}%`,
                  }}>
                    <span className="absolute -top-5 left-0 rounded bg-ink-900 px-1 font-mono text-[11px] text-white">{i + 1}</span>
                  </span>
                ))}
              </span>
            ) : (
              <span className="p-6 text-center text-sm text-ink-300">
                <ImageUp className="mx-auto mb-2 h-8 w-8 text-ink-400" />Seleccionar fotografía<br />
                <span className="text-xs text-ink-400">JPG o PNG · máx. 6 MB</span>
              </span>
            )}
            <input type="file" accept="image/jpeg,image/png" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          </label>
          <div className="mt-3 flex justify-end">
            <Button variant="primary" icon={ScanSearch} disabled={!file} loading={analyze.isPending} onClick={() => analyze.mutate()}>Analizar rostros</Button>
          </div>
          <ErrorNote error={analyze.error} />
        </Card>
        <Card title="Resultados" icon={Siren} className="xl:col-span-2">
          {!result && <p className="text-sm text-ink-300">Seleccione una fotografía y pulse Analizar rostros.</p>}
          {result && result.faces.length === 0 && <p className="text-sm text-ink-200">No se detectó ningún rostro en la imagen.</p>}
          <div className="space-y-3">
            {result?.faces.map((face, i) => <FaceCard key={i} index={i + 1} face={face} />)}
          </div>
          {result && <p className="mt-3 text-[11px] text-ink-400">Umbral de similitud: {fmtScore(result.threshold)}. La similitud no es una probabilidad. Toda coincidencia requiere revisión humana.</p>}
        </Card>
      </div>
    </>
  );
}

function FaceCard({ index, face }: { index: number; face: AnalysisFace }) {
  const info = RESULT[face.result];
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 p-3 text-sm">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="font-mono text-xs text-ink-300">Rostro {index}</span>
        <Badge tone={info.tone} dot>{info.label}</Badge>
      </div>
      {face.match && <p className="text-ink-100">{face.match.name} <span className="font-mono text-xs text-ink-400">{face.match.uid} · similitud {fmtScore(face.score)}</span></p>}
      {face.quality_issues.map((issue) => <p key={issue} className="text-xs text-warn-400">{issue}</p>)}
      {face.ambiguous && <p className="mt-1 flex items-center gap-1.5 text-xs text-warn-400"><TriangleAlert className="h-3.5 w-3.5" />Resultado ambiguo: se parece a más de una persona.</p>}
      {face.alternatives.map((m) => <p key={m.uid} className="text-xs text-ink-300">También se parece a {m.name} ({fmtScore(m.score)})</p>)}
      {face.alert && <Link to={`/alertas?id=${face.alert.id}`} className="mt-1 inline-block text-xs font-medium text-volt-400 hover:text-volt-300">Revisar alerta {face.alert.uid} →</Link>}
    </div>
  );
}
