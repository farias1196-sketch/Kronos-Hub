# Segurança

Relate vulnerabilidades em privado ao mantenedor. Enquanto a distribuição estiver em revisão local, use o canal privado já estabelecido com ele. Se o repositório vier a usar GitHub Private Vulnerability Reporting, utilize esse canal. Informe a versão, o fluxo afetado e uma reprodução com contas fictícias.

Não coloque em issues, PRs ou capturas tokens, senhas, bancos, conversas, identificadores de clientes ou detalhes de infraestrutura. Use apenas dados inventados, mantenha as APIs em loopback e confira `git ls-files` antes de compartilhar arquivos. `git check-ignore -v .env` mostra a regra de exclusão.

O arquivo privado guarda apenas valores desta instalação. A troca de chaves administrativas ou SSO invalida sessões emitidas com elas. Mudar as senhas iniciais no arquivo não redefine senhas de contas já criadas. Uma credencial comercial já gravada em commits deve ser tratada separadamente pelo responsável pelo ambiente.
