# Configurar o Replai (primeira vez)

Cinco passos. Em cada um: uma linha dizendo o que você está fazendo, a ação, e o próximo passo. Nada de
JSON nem de explicação que não muda o que quem opera faz.

**Só para conta nova.** Se o `checar` já mostra a conta, não refaça as perguntas: vá ao passo do que o
`falta` aponta (login: 3; voz: 4; lista: o comando `lista`). PC novo de quem já usava o Replai: peça o
zip de `Documentos\Replai\_copias` do PC antigo e rode `restaurar --arquivo "<zip>"`; depois, só o
login (passo 3).

## 1. Perguntas, numa mensagem só

Não pergunte o que já veio no pedido. O idioma é o da pessoa: não pergunte.

1. O seu nome.
2. De quem é a conta (nome e sobrenome) e em quais redes: LinkedIn, X ou as duas.
3. O link do perfil dessa conta no LinkedIn e o @ dela no X.
4. As pessoas que a conta vai comentar: um Excel/CSV, os links colados na conversa, ou o link de uma
   planilha do Google (compartilhada como "qualquer pessoa com o link pode ver"). Sem nada disso, a lista
   começa vazia e vai sendo preenchida depois. Se existir uma Lista do X (`https://x.com/i/lists/...`),
   o link dela também.
5. Os nomes que a conta nunca cita: a própria empresa, clientes, parceiros que ela não quer associar
   em público. Pode ficar vazio.

## 2. Montar tudo num comando

`checar`. Faltou Python, bibliotecas, navegador ou Claude Code: rode o instalador
(`$PY "$HOME/.claude/skills/replai/scripts/instalar.py"`) e `checar` de novo. Depois:

    configurar --nome "<Nome Sobrenome>" --operador "<seu nome>" --idioma <pt|en> --redes linkedin,x
               --perfil-linkedin "<link do perfil>" --perfil-x "<@>"
               [--lista "<Excel, CSV ou link do Google>"] [--x-lista "<link da Lista do X>"]
               [--nunca-citar "<Nome>"]... [--pode-citar "<Nome>"]...

Sem link do Google, a lista vira o arquivo `lista.csv` da conta (abre no Excel). Links colados na
conversa: um `perfil --adicionar` por pessoa, depois do `configurar`. Diga numa linha: "142 pessoas no
LinkedIn, 37 no X" (`perfis_por_rede`). `avisos`: mostre. Se o X
ficou desligado por falta de lista, peça o link da Lista do X e rode
`lista --rede x --nome Principal --x-lista "<link>"` e `conta --rede x --ativa sim`. Erro de
compartilhamento: peça para deixar a planilha como "qualquer pessoa com o link pode ver".

## 3. Login, uma janela só

Rode `login` (segundo plano) e diga só isto:

> Vai abrir uma janela do navegador, com uma aba do LinkedIn e uma do X. Entre na conta de <Nome> em
> cada aba (se pedir código, <Nome> recebe no celular). Quando as duas estiverem no feed, me avise.

Quando a pessoa avisar que logou, rode `login --fechar`: ele fecha a janela com delicadeza (o Chrome
grava os cookies) e o `login` em segundo plano confere cada rede com a porta do robô e diz qual ficou
logada. (No Windows o arquivo de cookies fica travado enquanto o Chrome está aberto, então a janela
**não** fecha sozinha — quem fecha é o `login --fechar`. No Mac ela pode fechar sozinha antes; aí o
`--fechar` é só um "nada a fazer".) A rede que não ficou logada: `login` de novo (sempre as duas redes juntas, nunca `--rede`; a que já está logada só confere).

É uma vez só neste PC: depois o Replai roda escondido, nessa sessão. Se a campanha de DM já roda neste
PC, o LinkedIn já vem logado: diga que falta só o X.

## 4. Conferir e montar a voz

1. Mande as 5 perguntas da voz numa mensagem só (`referencias/voz.md`, "Criar").
2. Enquanto quem opera responde, rode em segundo plano, um depois do outro: `testar` e `voz-amostra`.
3. No `testar`: ✗ resolva antes de seguir (`referencias/problemas.md`). Item "conta aprendida agora"
   (só quando o passo 2 ficou sem o perfil): pergunte "A conta logada é a <vanity ou @>?"; se não for,
   pare e refaça o login com a conta certa.
4. Monte a voz e peça o ok (`voz.md`, "Criar", passos 3 e 4).

## 5. Primeira rodada, depois o vigia

1. **Primeira rodada, com aprovação.** `coletar` (segundo plano), escritor, `revisao`, `aprovar`, como
   em "A rodada" da skill. Depois `postar --so primeiro` (segundo plano): sai um comentário por rede.
   Mande os links e peça: "Abra e confira: post certo, texto inteiro." Ok: `postar` (segundo plano)
   solta o resto. Algo errado: pare (`referencias/problemas.md`).
   - Sem posts ("nenhum candidato" ou "fora do horário"): diga "Ninguém da lista postou nas últimas
     horas. O vigia vai juntar os próximos para você aprovar." e siga para o item 2.
2. **Login do Claude para o vigia (uma vez).** O vigia escreve pelo Claude Code de linha de comando.
   Pegue o caminho em `claude_code_caminho` do `checar` (vazio: rode o instalador e `checar` de novo).
   Rode `"<caminho>" auth login` em segundo plano e diga: "Vai abrir uma página do Claude no navegador:
   entre com a sua conta e clique em Autorizar." Confira com `"<caminho>" -p "ok" --max-turns 1
   --tools ""`: se a resposta falar em "login", repita.
3. **Vigia ligado, em revisão.** `vigia --ligar`; se o LinkedIn estiver ligado, `sininho` (segundo
   plano); e `vigiar --agora` (segundo plano). Mostre o resumo numa linha. O vigia escreve e guarda para
   a revisão; quem opera aprova com `/replai aprovar`.
4. **Automático só depois.** Depois de 3 rodadas revisadas seguidas sem correção (até 10% editados ou
   tirados), o `status` e o `aprovar` trazem `propor_sozinho`: aí, e só com o ok, `conta --rede <rede>
   --modo sozinho`. O script recusa antes disso.

Fim: mostre o cartão de ajuda (`referencias/comandos.md`) e diga, numa linha cada:
- "O vigia precisa do computador ligado e da sua sessão aberta (pode bloquear a tela)."
- "A conta de <Nome> roda só neste PC."
