import { companyStage, stages } from "../../shared/implantation";
export default function CompanyExperiencePreference({ tenant }) {
  const stage = companyStage(tenant);
  return <section style={{ padding: 12, border: "1px solid var(--chronos-border)", borderRadius: 12 }}><strong>{stages[stage].title}</strong><p>Etapa única da empresa. Alterações pelo ADM geral.</p></section>;
}
