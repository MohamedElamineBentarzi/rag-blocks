import { useStudio } from "../graph/store";

// Live structural feedback, floating over the canvas. Type mismatches are
// already prevented at connect time; this catches the rest (duplicate stages,
// an unwired index, cycles) so nothing is a surprise at export.
export function Problems() {
  const problems = useStudio((s) => s.problems);
  const hasNodes = useStudio((s) => s.nodes.length > 0);
  if (!hasNodes) return null;

  if (!problems.length) {
    return (
      <div className="problems">
        <span className="ok">✓ Pipeline is valid — ready to export.</span>
      </div>
    );
  }
  return (
    <div className="problems">
      {problems.map((p, i) => (
        <div key={i} className={`row ${p.level}`}>
          <span className="tag">{p.level}</span>
          <span>{p.message}</span>
        </div>
      ))}
    </div>
  );
}
