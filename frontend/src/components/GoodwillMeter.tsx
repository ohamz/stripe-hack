import type { ClientCard } from "../types";

export default function GoodwillMeter({ card }: { card: ClientCard }) {
  const allowance = card.favour_allowance;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-medium text-slate-700">Favours this month</p>
        <p className="text-sm text-slate-600">
          {allowance == null ? `${card.favours_used} used` : `${card.favours_used} of ${allowance}`}
        </p>
      </div>
      {allowance != null ? (
        <div className="mt-2 flex gap-1.5">
          {Array.from({ length: allowance }).map((_, i) => (
            <div key={i} className={`h-2.5 flex-1 rounded-full ${i < card.favours_used ? "bg-emerald-600" : "bg-slate-200"}`} />
          ))}
        </div>
      ) : (
        <p className="mt-1 text-xs text-slate-500">No favour allowance understood yet (goodwill rules not parsed).</p>
      )}
      {card.favours_free_kind > 0 && (
        <p className="mt-2 text-xs text-emerald-700">
          +{card.favours_free_kind} typo fix{card.favours_free_kind > 1 ? "es" : ""}, always free
        </p>
      )}
    </div>
  );
}
