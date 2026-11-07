import { useState } from "react";
import MobileDialog from "../../components/ui/MobileDialog";
import { NEXUS_API_URL } from "../../shared/chronosConfig";
import { jsonRequest, useResource } from "../experience/experienceData";
import "./registrationProfile.css";

export const clientFields = [
  ["name", "Nome", "text", true], ["company_name", "Nome da empresa"], ["phone", "Telefone", "tel", true],
  ["email", "E-mail", "email"], ["fiscal_document", "CPF ou CNPJ"], ["cep", "CEP"],
  ["address_street", "Endereço", "textarea"], ["address_number", "Número"], ["address_complement", "Complemento", "textarea"],
  ["address_neighborhood", "Bairro"], ["address_city", "Cidade"], ["address_state", "UF"], ["notes", "Observações", "textarea"]
];
export function RegistrationFields({ fields = [], values = {}, onChange, enforceRequired = false }) {
  return <div className="registration-fields">{fields.map(field => <label key={field.id}>{field.label}{field.required && " *"}{field.description && <small>{field.description}</small>}{field.type === "textarea" ? <textarea rows={3} maxLength={2000} required={enforceRequired && field.required} value={values[field.id] || ""} onChange={event => onChange({ ...values, [field.id]: event.target.value })} /> : <input type={field.type || "text"} maxLength={2000} required={enforceRequired && field.required} value={values[field.id] || ""} onChange={event => onChange({ ...values, [field.id]: event.target.value })} />}</label>)}</div>;
}
export function RegistrationProfileButton({ tenant, onSaved }) {
  const [open,setOpen]=useState(false);
  return <><button type="button" onClick={()=>setOpen(true)}>Perfil de cadastro</button>{open && <ProfileEditor tenant={tenant} onClose={()=>setOpen(false)} onSaved={onSaved} />}</>;
}
function ProfileEditor({tenant,onClose,onSaved}) {
  const url=`${NEXUS_API_URL}/nexus/registration-profile?empresa_id=${encodeURIComponent(tenant)}`;
  const resource=useResource(url);
  const [edited,setEdited]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const fields=edited || resource.data?.fields || [];
  const change=(index,key,value)=>setEdited(fields.map((field,i)=>i===index?{...field,[key]:value}:field));
  async function save(event){event.preventDefault();if(busy)return;setBusy(true);setError("");try{await jsonRequest(url,"PUT",{fields});onSaved?.();onClose();}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <MobileDialog title="Perfil de cadastro" onClose={()=>{if(!busy)onClose();}}><form className="registration-fields" onSubmit={save}>
    <p>Nome, empresa, documento, telefone, e-mail e endereço completo já fazem parte do cadastro. Crie abaixo as informações adicionais que deseja pedir ao cliente.</p>
    {(error || resource.error) && <p role="alert">{error || resource.error}</p>}
    {resource.loading ? <p>Carregando...</p> : <>{fields.map((field,index)=><fieldset className="registration-fields" key={field.id}><label>Nome do campo<input required maxLength={100} value={field.label} onChange={e=>change(index,"label",e.target.value)} /></label><label>Orientação para preencher<textarea rows={2} maxLength={300} value={field.description || ""} onChange={e=>change(index,"description",e.target.value)} /></label><label>Tipo<select value={field.type} onChange={e=>change(index,"type",e.target.value)}><option value="text">Texto curto</option><option value="textarea">Texto longo</option><option value="email">E-mail</option><option value="tel">Telefone</option></select></label><label className="registration-check"><input type="checkbox" checked={field.required} onChange={e=>change(index,"required",e.target.checked)} />Obrigatório</label><button type="button" disabled={busy} onClick={()=>setEdited(fields.filter((_,i)=>i!==index))}>Remover campo</button></fieldset>)}<button type="button" disabled={busy || fields.length>=30 || !!resource.error} onClick={()=>setEdited([...fields,{id:crypto.randomUUID(),label:"",description:"",type:"text",required:false}])}>Adicionar campo</button><button disabled={busy || !!resource.error} type="submit">{busy?"Salvando...":"Salvar perfil"}</button></>}
  </form></MobileDialog>;
}
